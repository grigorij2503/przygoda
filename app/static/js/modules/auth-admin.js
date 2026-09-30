(() => {
  'use strict';
  const features = window.TTRPG_FEATURES = window.TTRPG_FEATURES || {};
  features.authAdmin = {
    // --- Logowanie do Pokoju ---
    async login(isAuto = false) {
      this.authError = '';
      this.isLoggingIn = true;
      try {
        const res = await fetch('/api/verify-password', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ room_code: this.roomCode.trim().toLowerCase(), password: this.roomPassword })
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          throw new Error(data.detail || 'Niepoprawny kod pokoju lub hasło.');
        }
        this.roomCode = data.room_code;
        this.isAuthenticated = true;
        localStorage.setItem('rpg_room_code', this.roomCode);
        window.history.replaceState({}, '', `/?room=${encodeURIComponent(this.roomCode)}`);
        const savedCharacter = localStorage.getItem(`rpg_selected_char:${this.roomCode}`);
        this.selectedCharacterId = savedCharacter ? parseInt(savedCharacter, 10) : null;
        await this.fetchSession();
        this.initWebSocket();
        this.roomPassword = '';
      } catch (err) {
        if (!isAuto) this.authError = err.message;
        this.isAuthenticated = false;
      } finally {
        this.isLoggingIn = false;
      }
    },

    async restoreRoomAccess() {
      try {
        const res = await fetch(`/api/room-access?room_code=${encodeURIComponent(this.roomCode)}`, { cache: 'no-store' });
        if (!res.ok) return;
        this.isAuthenticated = true;
        await this.fetchSession();
        this.initWebSocket();
      } catch (error) {
        logger('Nie udało się przywrócić dostępu do pokoju', error);
      }
    },

    async createRoom() {
      this.roomCreationError = '';
      this.isCreatingRoom = true;
      try {
        const selectedWorld = this.newRoomWorldSummary;
        if (!selectedWorld || !this.newRoom.scenario_type) {
          throw new Error('Wybierz świat i scenariusz nowej kampanii.');
        }
        const res = await fetch('/api/rooms', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            room_code: this.newRoom.room_code,
            password: this.newRoom.password,
            title: this.newRoom.title,
            gm_pin: this.newRoom.gm_pin,
            world_pack_id: selectedWorld.id,
            world_pack_version: selectedWorld.version,
            scenario_type: this.newRoom.scenario_type,
            tone: this.newRoom.tone
          })
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || 'Nie udało się utworzyć pokoju.');
        this.roomCode = data.room_code;
        this.roomPassword = this.newRoom.password;
        this.newRoom = {
          room_code: '', password: '', title: '', gm_pin: '',
          world_key: '', scenario_type: '', tone: ''
        };
        this.showRoomCreation = false;
        await this.login();
      } catch (error) {
        this.roomCreationError = error.message;
      } finally {
        this.isCreatingRoom = false;
      }
    },

    async toggleRoomCreation() {
      this.showRoomCreation = !this.showRoomCreation;
      this.roomCreationError = '';
      if (!this.showRoomCreation) return;
      if (!this.worldCatalog.length) await this.loadWorldCatalog();
      if (!this.newRoom.world_key) {
        this.newRoom.world_key = this.selectedWorldKey || this.worldCatalog[0]?.key || '';
      }
      this.selectRoomWorld();
    },

    get newRoomWorldSummary() {
      return this.worldCatalog.find(world => world.key === this.newRoom.world_key) || null;
    },

    get newRoomScenarioOptions() {
      return this.newRoomWorldSummary?.scenario_options || [];
    },

    selectRoomWorld() {
      const selected = this.newRoomWorldSummary;
      if (!selected) return;
      this.newRoom.scenario_type = selected.scenario_options?.[0] || '';
      this.newRoom.tone = selected.setting_theme || '';
    },

    async logout() {
      await this.disablePushNotifications(true);
      await fetch('/api/admin/lock', { method: 'POST' }).catch(() => {});
      await fetch('/api/logout', { method: 'POST' }).catch(() => {});
      this.clearNotifications();
      this.isAuthenticated = false;
      this.session = null;
      this.isGmAuthenticated = false;
      this.showGmAuthModal = false;
      this.showIntroModal = false;
      this.gmPin = '';
      this.gmAuthError = '';
      this.resetConfirmation = '';
      this.clearCampaignEndingDraft();
      this.selectedCharacterId = null;
      localStorage.removeItem(`rpg_selected_char:${this.roomCode}`);
      this.closeWebSocket();
      this.chatMessages = [];
      this.chatSessionId = null;
      this.showStoryArchive = false;
      this.expandedStoryTurnIds = [];
      this.hasUnreadTurn = false;
      this.showProxyActionModal = false;
      this.proxyTargetCharacterId = null;
      this.newInventoryItemIds = [];
      this.inventoryFilter = 'all';
      this.transferItemId = null;
      window.TTRPG_THEME?.clearWorldPreview();
    },

    // --- Narzędzia Mistrza Gry ---
    async openGmTools() {
      this.gmAuthError = '';
      try {
        const res = await fetch('/api/admin/status');
        if (!res.ok) throw new Error('Nie udało się sprawdzić dostępu MG.');
        const data = await res.json();
        this.isGmAuthenticated = data.authenticated === true;
        if (this.isGmAuthenticated) {
          this.resetConfirmation = '';
          this.prepareGmStatEditor();
          await this.loadWorldCatalog();
          this.showIntroModal = true;
        } else {
          this.gmPin = '';
          this.showGmAuthModal = true;
        }
      } catch (err) {
        this.addToast(err.message, 'error');
      }
    },

    async authenticateGm() {
      this.gmAuthError = '';
      this.isAuthenticatingGm = true;
      try {
        const res = await fetch('/api/admin/unlock', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pin: this.gmPin })
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || 'Nie udało się odblokować Narzędzi MG.');
        this.isGmAuthenticated = true;
        this.showGmAuthModal = false;
        this.gmPin = '';
        this.resetConfirmation = '';
        this.prepareGmStatEditor();
        await this.loadWorldCatalog();
        this.showIntroModal = true;
      } catch (err) {
        this.gmAuthError = err.message;
      } finally {
        this.isAuthenticatingGm = false;
      }
    },

    async lockGmTools() {
      try {
        await fetch('/api/admin/lock', { method: 'POST' });
      } finally {
        this.isGmAuthenticated = false;
        this.showIntroModal = false;
        this.showGmAuthModal = false;
        this.gmPin = '';
        this.resetConfirmation = '';
        this.gmStatCharacterId = null;
        this.gmOriginalStats = null;
        this.gmStatError = '';
        window.TTRPG_THEME?.clearWorldPreview();
        this.addToast('Narzędzia MG zostały zablokowane.', 'info');
      }
    },

    requireGmUnlock() {
      this.isGmAuthenticated = false;
      this.showIntroModal = false;
      this.gmPin = '';
      this.gmAuthError = 'Sesja MG wygasła. Wpisz PIN ponownie.';
      this.showGmAuthModal = true;
      window.TTRPG_THEME?.clearWorldPreview();
    },

    closeGmTools() {
      this.showIntroModal = false;
      this.resetConfirmation = '';
      window.TTRPG_THEME?.clearWorldPreview();
    },

    clearCampaignEndingDraft() {
      this.gmCampaignSummary = '';
      this.gmEpilogue = '';
      this.gmEndingDraftError = '';
      this.gmEpilogueError = '';
    },

    async resolvePartyCrisis() {
      if (!(this.hasPartyCrisis || (this.activeEnemy?.hp > 0))) return;
      if (!confirm('Zakończyć bieżące starcie odwrotem? Przeciwnik nie zostanie pokonany, a drużyna nie otrzyma łupu.')) return;
      this.partyCrisisError = '';
      this.isResolvingPartyCrisis = true;
      try {
        const res = await fetch('/api/session/resolve-party-crisis', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ room_code: this.roomCode })
        });
        const data = await res.json().catch(() => ({}));
        if (res.status === 401 || res.status === 403) {
          this.requireGmUnlock();
          return;
        }
        if (!res.ok) throw new Error(data.detail || 'Nie udało się rozstrzygnąć kryzysu drużyny.');
        this.showIntroModal = false;
        await this.fetchSession();
        this.addToast(
          data.recovered_character_ids?.length
            ? 'Drużyna wycofała się awaryjnie, a obezwładnieni wrócili z 1 PW.'
            : 'Drużyna wycofała się ze starcia. Zachowano jej obecny stan PW.',
          'warning'
        );
        this.scrollToCurrentTurn(false);
      } catch (error) {
        this.partyCrisisError = error.message;
      } finally {
        this.isResolvingPartyCrisis = false;
      }
    },

    async loadWorldCatalog() {
      this.isLoadingWorldCatalog = true;
      this.worldCatalogError = '';
      try {
        const response = await fetch('/api/worlds', { cache: 'no-store' });
        if (!response.ok) throw new Error('Nie udało się pobrać katalogu światów.');
        const catalog = await response.json();
        this.worldCatalog = Array.isArray(catalog.worlds) ? catalog.worlds : [];
        if (!this.worldCatalog.some(world => world.key === this.selectedWorldKey)) {
          this.selectedWorldKey = this.session?.world_pack?.key ||
            catalog.default_world?.key || '';
        }
      } catch (error) {
        this.worldCatalogError = error.message;
        this.worldCatalog = [];
      } finally {
        this.isLoadingWorldCatalog = false;
      }
    },

    get selectedWorldSummary() {
      return this.worldCatalog.find(world => world.key === this.selectedWorldKey) || null;
    },

    get selectedWorldScenarioOptions() {
      return this.selectedWorldSummary?.scenario_options ||
        this.session?.world_pack?.scenario_options || [];
    },

    selectWorldForNextCampaign() {
      const selected = this.selectedWorldSummary;
      if (!selected) return;
      this.scenarioChoice = selected.scenario_options?.[0] || '';
      this.scenarioTone = selected.setting_theme || '';
      if (window.TTRPG_THEME?.isWorldPreview) {
        window.TTRPG_THEME.showWorldPreview(selected.theme);
      }
    },

    showNeonThemePreview() {
      window.TTRPG_THEME?.showPreview();
      this.addToast('Podgląd neonowy jest lokalny i nie zmienia świata kampanii.', 'info');
    },

    showSelectedWorldThemePreview() {
      if (!window.TTRPG_THEME?.showWorldPreview(this.selectedWorldSummary?.theme)) {
        this.addToast('Motyw wybranego świata jest niedostępny.', 'error');
        return;
      }
      this.addToast('Motyw wybranego świata jest widoczny tylko na tym urządzeniu.', 'info');
    },

    restoreCampaignTheme() {
      window.TTRPG_THEME?.clearPreview();
    },

    get gmStatCharacter() {
      return this.session?.characters?.find(
        character => character.id === Number(this.gmStatCharacterId)
      ) || null;
    },

    get gmStatTotal() {
      return ['strength', 'agility', 'intellect', 'charisma', 'perception'].reduce(
        (total, stat) => total + Number(this.gmStatForm[stat] || 0),
        0
      );
    },

    get gmOriginalStatTotal() {
      if (!this.gmOriginalStats) return 0;
      return ['strength', 'agility', 'intellect', 'charisma', 'perception'].reduce(
        (total, stat) => total + Number(this.gmOriginalStats[stat] || 0),
        0
      );
    },

    get gmStatDelta() {
      return this.gmStatTotal - this.gmOriginalStatTotal;
    },

    get gmStatsValid() {
      return ['strength', 'agility', 'intellect', 'charisma', 'perception'].every(stat => {
        const value = Number(this.gmStatForm[stat]);
        return Number.isInteger(value) && value >= 0 && value <= this.maxBaseStat;
      });
    },

    get gmStatsChanged() {
      return Boolean(this.gmOriginalStats) && ['strength', 'agility', 'intellect', 'charisma', 'perception'].some(
        stat => Number(this.gmStatForm[stat]) !== Number(this.gmOriginalStats[stat])
      );
    },

    prepareGmStatEditor() {
      const characters = this.session?.characters || [];
      if (!characters.some(character => character.id === Number(this.gmStatCharacterId))) {
        this.gmStatCharacterId = characters[0]?.id || null;
      }
      this.loadGmCharacterStats();
    },

    loadGmCharacterStats() {
      const character = this.gmStatCharacter;
      this.gmStatError = '';
      this.gmHealthError = '';
      if (!character) {
        this.gmOriginalStats = null;
        this.gmHealthValue = 0;
        return;
      }
      const stats = {
        strength: Number(character.strength || 0),
        agility: Number(character.agility || 0),
        intellect: Number(character.intellect || 0),
        charisma: Number(character.charisma || 0),
        perception: Number(character.perception || 0)
      };
      this.gmStatForm = { ...stats };
      this.gmOriginalStats = { ...stats };
      this.gmHealthValue = Number(character.current_hp || 0);
    },

    async saveGmHealth() {
      const character = this.gmStatCharacter;
      const currentHp = Number(this.gmHealthValue);
      this.gmHealthError = '';
      if (!character || !Number.isInteger(currentHp) || currentHp < 0 || currentHp > Number(character.max_hp || 0)) {
        this.gmHealthError = `PW musi być liczbą całkowitą od 0 do ${character?.max_hp || 0}.`;
        return;
      }
      this.isSavingGmHealth = true;
      try {
        const res = await fetch(`/api/admin/characters/${character.id}/health`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ room_code: this.roomCode, current_hp: currentHp })
        });
        const data = await res.json().catch(() => ({}));
        if (res.status === 403) { this.requireGmUnlock(); return; }
        if (!res.ok) throw new Error(data.detail || 'Nie udało się zmienić punktów życia.');
        await this.fetchSession();
        this.loadGmCharacterStats();
        this.addToast(`${data.character_name}: ${data.current_hp}/${data.max_hp} PW.`, 'success');
      } catch (err) {
        this.gmHealthError = err.message;
      } finally {
        this.isSavingGmHealth = false;
      }
    },

    async grantGmConsumable() {
      const character = this.gmStatCharacter;
      const quantity = Number(this.gmConsumableQuantity);
      this.gmConsumableError = '';
      if (!character || !Number.isInteger(quantity) || quantity < 1 || quantity > 20) {
        this.gmConsumableError = 'Wybierz postać i liczbę od 1 do 20.';
        return;
      }
      this.isGrantingConsumable = true;
      try {
        const res = await fetch(`/api/admin/characters/${character.id}/consumables`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ room_code: this.roomCode, quantity })
        });
        const data = await res.json().catch(() => ({}));
        if (res.status === 403) { this.requireGmUnlock(); return; }
        if (!res.ok) throw new Error(data.detail || 'Nie udało się podarować środka leczniczego.');
        await this.fetchSession('grant');
        this.addToast(`Dodano ${data.quantity} × ${data.item_name} (+${data.healing} PW).`, 'success');
      } catch (err) {
        this.gmConsumableError = err.message;
      } finally {
        this.isGrantingConsumable = false;
      }
    },

    async saveGmCharacterStats() {
      const character = this.gmStatCharacter;
      this.gmStatError = '';
      if (!character) {
        this.gmStatError = 'Wybierz postać do korekty.';
        return;
      }
      if (!this.gmStatsValid) {
        this.gmStatError = `Każdy atrybut musi być liczbą całkowitą od 0 do ${this.maxBaseStat}.`;
        return;
      }
      if (!this.gmStatsChanged) return;

      const deltaLabel = this.gmStatDelta === 0
        ? 'Łączna pula pozostanie bez zmian.'
        : `Łączna pula zmieni się o ${this.gmStatDelta > 0 ? '+' : ''}${this.gmStatDelta}.`;
      if (!confirm(
        `Awaryjnie zmienić bazowe atrybuty postaci „${character.name}”? ${deltaLabel} ` +
        'Zmiana wpłynie na kolejne rzuty, ale nie przeliczy już złożonych akcji.'
      )) return;

      this.isSavingGmStats = true;
      try {
        const res = await fetch(`/api/admin/characters/${character.id}/stats`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            room_code: this.roomCode,
            strength: Number(this.gmStatForm.strength),
            agility: Number(this.gmStatForm.agility),
            intellect: Number(this.gmStatForm.intellect),
            charisma: Number(this.gmStatForm.charisma),
            perception: Number(this.gmStatForm.perception)
          })
        });
        const data = await res.json().catch(() => ({}));
        if (res.status === 403) {
          this.requireGmUnlock();
          return;
        }
        if (!res.ok) throw new Error(data.detail || 'Nie udało się zmienić atrybutów postaci.');

        await this.fetchSession();
        this.loadGmCharacterStats();
        this.addToast(`Zmieniono bazowe atrybuty postaci ${data.character_name}.`, 'success');
      } catch (err) {
        this.gmStatError = err.message;
      } finally {
        this.isSavingGmStats = false;
      }
    },

    async setGmCharacterParticipation(participationStatus) {
      const character = this.gmStatCharacter;
      this.participationError = '';
      if (!character || this.isSavingParticipation) return;
      const isBreak = participationStatus === 'on_break';
      const question = isBreak
        ? `Wysłać postać „${character.name}” na przerwę? Zachowa poziom, XP, HP i ekwipunek, ale nie będzie uczestniczyć w turach.`
        : `Przywrócić postać „${character.name}” do gry od bieżącej tury?`;
      if (!confirm(question)) return;

      this.isSavingParticipation = true;
      try {
        const res = await fetch(`/api/admin/characters/${character.id}/participation`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            room_code: this.roomCode,
            participation_status: participationStatus
          })
        });
        const data = await res.json().catch(() => ({}));
        if (res.status === 403) { this.requireGmUnlock(); return; }
        if (!res.ok) throw new Error(data.detail || 'Nie udało się zmienić udziału postaci.');
        await this.fetchSession();
        this.loadGmCharacterStats();
        this.addToast(
          isBreak
            ? `${data.character_name} jest na przerwie od tury ${data.break_started_turn}.`
            : `${data.character_name} wraca do gry.`,
          'success'
        );
      } catch (err) {
        this.participationError = err.message;
      } finally {
        this.isSavingParticipation = false;
      }
    },

    async adjustGmCoins() {
      const character = this.gmStatCharacter;
      const amount = Number(this.gmCoinAmount);
      this.gmCoinError = '';
      if (!character || !Number.isInteger(amount) || amount === 0) {
        this.gmCoinError = 'Wybierz postać i podaj liczbę całkowitą różną od zera.';
        return;
      }
      this.isSavingGmCoins = true;
      try {
        const res = await fetch(`/api/admin/characters/${character.id}/coins`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ room_code: this.roomCode, amount })
        });
        const data = await res.json().catch(() => ({}));
        if (res.status === 403) { this.requireGmUnlock(); return; }
        if (!res.ok) throw new Error(data.detail || 'Nie udało się zmienić salda.');
        await this.fetchSession();
        this.addToast(`${character.name}: ${data.coins} ${this.currencyLabel}.`, 'success');
      } catch (err) {
        this.gmCoinError = err.message;
      } finally {
        this.isSavingGmCoins = false;
      }
    },

    async grantGmWearable() {
      const character = this.gmStatCharacter;
      this.gmWearableError = '';
      if (!character || !this.gmWearableForm.name.trim()) {
        this.gmWearableError = 'Wybierz postać i wpisz nazwę przedmiotu.';
        return;
      }
      this.isGrantingWearable = true;
      try {
        const res = await fetch(`/api/admin/characters/${character.id}/wearables`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ room_code: this.roomCode, ...this.gmWearableForm })
        });
        const data = await res.json().catch(() => ({}));
        if (res.status === 403) { this.requireGmUnlock(); return; }
        if (!res.ok) throw new Error(data.detail || 'Nie udało się dodać przedmiotu.');
        this.gmWearableForm = { item_type: 'helmet', name: '', description: '', target_stat: 'none', stat_bonus: 0 };
        await this.fetchSession();
        this.addToast(`Dodano ${data.item_name} do plecaka ${character.name}.`, 'success');
      } catch (err) {
        this.gmWearableError = err.message;
      } finally {
        this.isGrantingWearable = false;
      }
    },

    async generateCampaignEndingDraft() {
      this.gmEndingDraftError = '';
      this.gmEpilogueError = '';
      this.isGeneratingCampaignEnding = true;
      try {
        const res = await fetch('/api/session/generate-ending-draft', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ room_code: this.roomCode })
        });
        const data = await res.json().catch(() => ({}));
        if (res.status === 403) { this.requireGmUnlock(); return; }
        if (!res.ok) {
          throw new Error(data.detail || 'Nie udało się wygenerować szkicu finału kampanii.');
        }
        this.gmCampaignSummary = data.history_summary || '';
        this.gmEpilogue = data.epilogue || '';
        this.addToast('AI przygotowało podsumowanie i edytowalny szkic epilogu.', 'success');
      } catch (error) {
        this.gmEndingDraftError = error.message;
      } finally {
        this.isGeneratingCampaignEnding = false;
      }
    },

    async finishCampaign() {
      this.gmEpilogueError = '';
      const epilogue = this.gmEpilogue.trim();
      if (epilogue.length < 20) {
        this.gmEpilogueError = 'Wpisz epilog o długości co najmniej 20 znaków.';
        return;
      }
      this.isFinishingCampaign = true;
      try {
        const res = await fetch('/api/session/finish-campaign', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ room_code: this.roomCode, epilogue })
        });
        const data = await res.json().catch(() => ({}));
        if (res.status === 403) { this.requireGmUnlock(); return; }
        if (!res.ok) throw new Error(data.detail || 'Nie udało się zakończyć kampanii.');
        this.showIntroModal = false;
        this.clearCampaignEndingDraft();
        await this.fetchSession();
        this.addToast('Kampania została zakończona. Epilog zapisano w kronice.', 'success');
      } catch (error) {
        this.gmEpilogueError = error.message;
      } finally {
        this.isFinishingCampaign = false;
      }
    },

  };
})();
