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
          body: JSON.stringify({ password: this.roomPassword })
        });
        if (!res.ok) {
          throw new Error('Niepoprawne hasło do pokoju gry.');
        }
        this.isAuthenticated = true;
        localStorage.setItem('rpg_room_pw', this.roomPassword);
        await this.fetchSession();
        this.initWebSocket();
      } catch (err) {
        if (!isAuto) this.authError = err.message;
        this.isAuthenticated = false;
        localStorage.removeItem('rpg_room_pw');
      } finally {
        this.isLoggingIn = false;
      }
    },

    async logout() {
      fetch('/api/admin/lock', { method: 'POST' }).catch(() => {});
      await this.disablePushNotifications(true);
      this.clearNotifications();
      this.isAuthenticated = false;
      this.isGmAuthenticated = false;
      this.showGmAuthModal = false;
      this.showIntroModal = false;
      this.gmPin = '';
      this.gmAuthError = '';
      this.resetConfirmation = '';
      this.selectedCharacterId = null;
      localStorage.removeItem('rpg_room_pw');
      localStorage.removeItem('rpg_selected_char');
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
        this.addToast('Narzędzia MG zostały zablokowane.', 'info');
      }
    },

    requireGmUnlock() {
      this.isGmAuthenticated = false;
      this.showIntroModal = false;
      this.gmPin = '';
      this.gmAuthError = 'Sesja MG wygasła. Wpisz PIN ponownie.';
      this.showGmAuthModal = true;
    },

    get gmStatCharacter() {
      return this.session?.characters?.find(
        character => character.id === Number(this.gmStatCharacterId)
      ) || null;
    },

    get gmStatTotal() {
      return ['strength', 'agility', 'intellect', 'charisma'].reduce(
        (total, stat) => total + Number(this.gmStatForm[stat] || 0),
        0
      );
    },

    get gmOriginalStatTotal() {
      if (!this.gmOriginalStats) return 0;
      return ['strength', 'agility', 'intellect', 'charisma'].reduce(
        (total, stat) => total + Number(this.gmOriginalStats[stat] || 0),
        0
      );
    },

    get gmStatDelta() {
      return this.gmStatTotal - this.gmOriginalStatTotal;
    },

    get gmStatsValid() {
      return ['strength', 'agility', 'intellect', 'charisma'].every(stat => {
        const value = Number(this.gmStatForm[stat]);
        return Number.isInteger(value) && value >= 0 && value <= this.maxBaseStat;
      });
    },

    get gmStatsChanged() {
      return Boolean(this.gmOriginalStats) && ['strength', 'agility', 'intellect', 'charisma'].some(
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
      if (!character) {
        this.gmOriginalStats = null;
        return;
      }
      const stats = {
        strength: Number(character.strength || 0),
        agility: Number(character.agility || 0),
        intellect: Number(character.intellect || 0),
        charisma: Number(character.charisma || 0)
      };
      this.gmStatForm = { ...stats };
      this.gmOriginalStats = { ...stats };
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
            charisma: Number(this.gmStatForm.charisma)
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

  };
})();
