(() => {
  'use strict';
  const features = window.TTRPG_FEATURES = window.TTRPG_FEATURES || {};
  features.sessionCharacter = {
    // --- Pobieranie Stanu Sesji ---
    async fetchSession(arrivalKind = 'loot') {
      const previousWorldKey = this.session?.world_pack?.key;
      const previousTurnNumber = this.session?.current_turn_number;
      const previousUnspentStatPoints = this.currentCharacter?.unspent_stat_points;
      const previousCharacterId = this.currentCharacter?.id;
      const previousInventoryItemIds = previousCharacterId
        ? new Set(this.currentCharacter.inventory.map(item => item.id))
        : null;
      this.isLoadingSession = true;
      try {
        const res = await fetch(`/api/session?room_code=${this.roomCode}`, { cache: 'no-store' });
        if (!res.ok) throw new Error('Błąd ładowania sesji.');
        const data = await res.json();
        this.session = data;
        window.TTRPG_THEME?.applyPackTheme(data.world_pack?.theme, data.world_pack?.key);
        if (previousWorldKey !== data.world_pack?.key) {
          this.selectedWorldKey = data.world_pack?.key || '';
          this.scenarioChoice = data.scenario_type || data.world_pack?.scenario_options?.[0] || '';
          this.scenarioTone = data.setting_theme || data.world_pack?.setting_theme || '';
        }
        if (!this.worldClasses.some(item => item.id === this.newChar.class_id)) {
          this.newChar.class_id = this.worldClasses[0]?.id || '';
        }
        this.isResolvingTurn = Boolean(data.is_turn_resolving);
        if (previousTurnNumber !== undefined && previousTurnNumber !== data.current_turn_number) {
          this.actionText = '';
          this.actionIntent = null;
          this.actionTestedStat = null;
          this.actionTargetRef = null;
          this.magicAbilityId = null;
          this.namedAttackId = null;
          this.actionInterpretation = null;
          this.showActionInterpretationControls = false;
          this.isEditingSubmittedAction = false;
          this.marketCraftItemIds = [];
          this.marketInteractionText = '';
          this.marketFeedback = '';
          this.marketError = '';
          this.marketTab = 'buy';
          this.turnError = '';
        }
        const serverNow = Date.parse(data.server_time);
        this.proxyClockOffset = Number.isFinite(serverNow) ? serverNow - Date.now() : 0;
        this.proxyNow = Date.now() + this.proxyClockOffset;
        if (this.proxyTargetCharacterId && (
          !this.proxyTargetCharacter ||
          this.proxyTargetCharacter.has_submitted_action ||
          (this.proxyDecision && this.proxyDecision.status !== 'open')
        )) {
          this.showProxyActionModal = false;
          this.proxyTargetCharacterId = null;
        }
        if (this.showMapModal) {
          this.selectedMapNodeId = this.campaignMap?.current_node_id || null;
          this.scheduleMapRender();
        }

        if (previousCharacterId === this.selectedCharacterId && previousInventoryItemIds) {
          const currentItems = this.currentCharacter?.inventory || [];
          const currentItemIds = new Set(currentItems.map(item => item.id));
          const newlyFoundItems = currentItems.filter(item => !previousInventoryItemIds.has(item.id));
          this.newInventoryItemIds = [
            ...new Set([
              ...this.newInventoryItemIds.filter(itemId => currentItemIds.has(itemId)),
              ...newlyFoundItems.map(item => item.id)
            ])
          ];
          if (newlyFoundItems.length && arrivalKind === 'loot') {
            const lootLabel = newlyFoundItems.length === 1
              ? newlyFoundItems[0].name
              : `${newlyFoundItems.length} nowe przedmioty`;
            this.addToast(`🎒 Nowy łup: ${lootLabel}. Zajrzyj do plecaka!`, 'success');
          }
        }

        // Sprawdź czy jest aktywne zadanie nazywania
        if (data.pending_naming) {
          this.pendingNaming = data.pending_naming;
          if (this.pendingNaming.character_id === this.selectedCharacterId) {
            this.showNamingModal = true;
          }
        } else {
          this.pendingNaming = null;
        }

        // Auto-wybór postaci
        if (this.selectedCharacterId) {
          const exists = this.session.characters.find(c => c.id === this.selectedCharacterId);
          if (!exists) this.selectedCharacterId = null;
        }

        const unspentStatPoints = this.currentCharacter?.unspent_stat_points || 0;
        const characterOnBreak = this.currentCharacter?.participation_status === 'on_break';
        if (!characterOnBreak && unspentStatPoints > 0 && (
          previousUnspentStatPoints === undefined ||
          unspentStatPoints > previousUnspentStatPoints
        )) {
          this.showLevelUpModal = true;
        } else if (characterOnBreak || unspentStatPoints === 0) {
          this.showLevelUpModal = false;
        }

        if (this.session.characters.length === 0 && this.isAuthenticated) {
          this.showCharModal = true;
        }
        return true;
      } catch (err) {
        this.addToast(err.message, 'error');
        return false;
      } finally {
        this.isLoadingSession = false;
      }
    },

    selectCharacter(charId) {
      this.selectedCharacterId = charId;
      this.actionText = '';
      this.actionIntent = null;
      this.actionTestedStat = null;
      this.actionTargetRef = null;
      this.magicAbilityId = null;
      this.namedAttackId = null;
      this.actionInterpretation = null;
      this.showActionInterpretationControls = false;
      this.actionError = '';
      this.newInventoryItemIds = [];
      this.inventoryFilter = 'all';
      this.transferItemId = null;
      localStorage.setItem(`rpg_selected_char:${this.roomCode}`, charId);
      this.initWebSocket();
      this.syncPushSubscription();
      this.addToast(`Wybrano postać: ${this.currentCharacter?.name}`, 'success');
      if ((this.currentCharacter?.unspent_stat_points || 0) > 0) {
        this.showLevelUpModal = true;
      }
    },

    async deleteCharacter(charId, charName) {
      if (!confirm(`Czy na pewno chcesz usunąć postać "${charName}"? Ta operacja jest nieodwracalna!`)) return;
      try {
        const res = await fetch(`/api/characters/${charId}`, { method: 'DELETE' });
        const data = await res.json();
        if (res.ok) {
          // Jeśli usunięto aktualnie wybraną postać, odznacz ją
          if (this.selectedCharacterId === charId) {
            this.selectedCharacterId = null;
            localStorage.removeItem(`rpg_selected_char:${this.roomCode}`);
          }
          // Odśwież sesję
          await this.loadSession();
          this.addToast(`Postać "${charName}" została usunięta`, 'info');
        } else {
          this.addToast(data.detail || 'Nie udało się usunąć postaci', 'error');
        }
      } catch (e) {
        this.addToast('Błąd połączenia przy usuwaniu postaci', 'error');
      }
    },

    get currentCharacter() {
      if (!this.session || !this.selectedCharacterId) return null;
      return this.session.characters.find(c => c.id === this.selectedCharacterId);
    },

    get worldClasses() {
      return this.session?.world_pack?.classes || [];
    },

    get worldAttributes() {
      return this.session?.world_pack?.attributes || [];
    },

    get selectedNewClass() {
      return this.worldClasses.find(item => item.id === this.newChar.class_id) || null;
    },

    classDefinition(classId) {
      return this.worldClasses.find(item => item.id === classId) || null;
    },

    classIcon(character) {
      return this.classDefinition(character?.class_id)?.icon || '👤';
    },

    narrativeFormLabel(value) {
      return {
        masculine: 'narrator: on',
        feminine: 'narrator: ona',
        neutral: 'narrator: bez rodzaju'
      }[value] || 'narrator: bez rodzaju';
    },

    attributeDefinition(stat) {
      return this.worldAttributes.find(item => item.id === stat)
        || { id: stat, label: stat, abbreviation: String(stat || '').toUpperCase() };
    },

    get enemyProfile() {
      return this.session?.world_pack?.enemy_profile || {};
    },

    get lootSearchAction() {
      return this.session?.world_pack?.loot_search_action || null;
    },

    get activeEnemy() {
      return this.session?.active_enemy || this.session?.active_boss || null;
    },

    get abilityBook() {
      return this.currentCharacter?.ability_book || this.currentCharacter?.magic_book || null;
    },

    get magicBook() {
      return this.abilityBook;
    },

    get selectedMagicAbility() {
      return this.abilityBook?.abilities?.find(ability => ability.id === this.magicAbilityId) || null;
    },

    get selectedNamedAttack() {
      return (this.currentCharacter?.learned_attacks || [])
        .find(attack => attack.id === this.namedAttackId) || null;
    },

    get quickActions() {
      const classPresets = (this.currentCharacter?.quick_actions || []).map(action => ({
        ...action,
        targetRef: action.target_ref ?? null
      }));
      const abilityPresets = (this.abilityBook?.abilities || [])
        .filter(ability => ability.unlocked)
        .slice(0, 3)
        .map(ability => ({
          id: `ability-${ability.id}`,
          icon: ability.icon,
          label: ability.name,
          text: ability.action_text,
          intent: ability.intent,
          targetRef: ability.target_ref,
          magicAbilityId: ability.id
        }));
      return [...classPresets, ...abilityPresets];
    },

    get supportTargets() {
      const resurrection = this.selectedMagicAbility?.mechanic_key === 'revive';
      return (this.session?.characters || []).filter(character =>
        resurrection ? character.death_state === 'dead' && character.id !== this.selectedCharacterId
          : character.death_state !== 'dead'
      );
    },

    get handItems() {
      return (this.currentCharacter?.inventory || [])
        .filter(item => item.is_equipped && ['weapon', 'shield'].includes(item.item_type))
        .sort((a, b) => {
          if (a.item_type !== b.item_type) return a.item_type === 'shield' ? 1 : -1;
          return a.id - b.id;
        });
    },

    get mainHandItem() {
      return this.handItems.find(item => item.item_type === 'weapon') || null;
    },

    get offHandItem() {
      if (this.mainHandItem?.hands_required === 2) return null;
      return this.handItems.find(item => item.id !== this.mainHandItem?.id) || null;
    },

    get offHandBlockedByTwoHandedWeapon() {
      return this.mainHandItem?.hands_required === 2;
    },

    get equippedArmor() {
      return this.latestEquippedItem(['armor']);
    },

    get equippedHelmet() {
      return this.latestEquippedItem(['helmet']);
    },

    get equippedBoots() {
      return this.latestEquippedItem(['boots']);
    },

    get activeItems() {
      return (this.currentCharacter?.inventory || [])
        .filter(item => item.is_equipped && ['accessory', 'misc'].includes(item.item_type))
        .sort((a, b) => b.id - a.id)
        .slice(0, 5);
    },

    get activeItemSlots() {
      return Array.from({ length: 5 }, (_, index) => this.activeItems[index] || null);
    },

    get equippedStatItems() {
      const items = [
        this.mainHandItem,
        this.offHandItem,
        this.equippedArmor,
        this.equippedHelmet,
        this.equippedBoots,
        ...this.activeItems
      ].filter(Boolean);

      return items.filter((item, index) =>
        items.findIndex(candidate => candidate.id === item.id) === index
      );
    },

    equipmentStatBonus(stat) {
      return this.equippedStatItems.reduce((total, item) => {
        const bonus = item.target_stat === stat || item.target_stat === 'all'
          ? Number(item.stat_bonus || 0) : 0;
        const curse = item.curse_stat === stat ? Number(item.curse_penalty || 0) : 0;
        return total + bonus + curse;
      }, 0);
    },

    totalCharacterStat(stat) {
      return Number(this.currentCharacter?.[stat] || 0) + this.equipmentStatBonus(stat);
    },

    formatSignedStat(value) {
      const numericValue = Number(value || 0);
      return `${numericValue >= 0 ? '+' : ''}${numericValue}`;
    },

    get backpackItems() {
      const equippedItemIds = new Set([
        ...this.handItems.map(item => item.id),
        this.equippedArmor?.id,
        this.equippedHelmet?.id,
        this.equippedBoots?.id,
        ...this.activeItems.map(item => item.id)
      ].filter(Boolean));

      return (this.currentCharacter?.inventory || [])
        .filter(item => !equippedItemIds.has(item.id))
        .sort((a, b) => {
          const newItemDifference = Number(this.isNewInventoryItem(b.id)) - Number(this.isNewInventoryItem(a.id));
          return newItemDifference || b.id - a.id;
        });
    },

    get visibleBackpackItems() {
      const allowedTypes = {
        main_hand: ['weapon'],
        off_hand: ['weapon', 'shield'],
        armor: ['armor'],
        helmet: ['helmet'],
        boots: ['boots'],
        active: ['accessory', 'misc']
      }[this.inventoryFilter];
      if (!allowedTypes) return this.backpackItems;
      return this.backpackItems.filter(item => allowedTypes.includes(item.item_type));
    },

    get inventoryFilterLabel() {
      return {
        main_hand: 'broń',
        off_hand: 'broń lub tarcze',
        armor: 'pancerze',
        helmet: 'hełmy',
        boots: 'buty',
        active: 'aktywne przedmioty'
      }[this.inventoryFilter] || 'wszystkie przedmioty';
    },

    showItemsForSlot(slot) {
      this.inventoryFilter = slot;
      this.$nextTick(() => this.$refs.inventoryBackpack?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }));
    },

    latestEquippedItem(itemTypes) {
      return (this.currentCharacter?.inventory || [])
        .filter(item => item.is_equipped && itemTypes.includes(item.item_type))
        .sort((a, b) => b.id - a.id)[0] || null;
    },

    itemIcon(item) {
      return {
        weapon: '⚔️',
        shield: '🔰',
        armor: '🛡️',
        helmet: '🪖',
        boots: '🥾',
        accessory: '💍',
        consumable: '🧪',
        misc: '🔮'
      }[item?.item_type] || '📦';
    },

    itemTypeLabel(item) {
      return {
        weapon: item?.hands_required === 2 ? 'Broń dwuręczna' : 'Broń jednoręczna',
        shield: 'Tarcza',
        armor: 'Zbroja',
        helmet: 'Hełm',
        boots: 'Buty',
        accessory: 'Aktywny',
        consumable: 'Zużywalny',
        misc: 'Aktywny'
      }[item?.item_type] || 'Przedmiot';
    },

    itemBonusLabel(item) {
      if (!item || item.item_type === 'consumable') return '';
      const damage = item.item_type === 'weapon' && item.damage_power > 0
        ? `obrażenia ${item.damage_power}+k6`
        : '';
      const effects = [];
      if (item.stat_bonus > 0 && item.target_stat === 'hp_max') effects.push(`+${item.stat_bonus} maks. PW`);
      else if (item.stat_bonus > 0 && item.target_stat === 'all') effects.push(`+${item.stat_bonus} wszystkie testy`);
      else if (item.stat_bonus > 0 && item.target_stat !== 'none') effects.push(`+${item.stat_bonus} ${this.statAbbreviation(item.target_stat)}`);
      if (item.curse_stat && item.curse_penalty < 0) {
        effects.push(`${item.curse_penalty} ${this.statAbbreviation(item.curse_stat)} (klątwa)`);
      }
      if (damage) effects.push(damage);
      return effects.join(' • ');
    },

    get transferTargets() {
      return (this.session?.characters || []).filter(character =>
        character.id !== this.selectedCharacterId &&
        character.is_alive &&
        character.participation_status !== 'on_break'
      );
    },

    get currencyLabel() {
      const theme = this.session?.world_pack?.theme;
      if (theme?.id === 'neo_katowice') return 'kredyty';
      return theme?.icon_set_id === 'classic' ? 'monety' : 'środki';
    },

    isNewInventoryItem(itemId) {
      return this.newInventoryItemIds.includes(itemId);
    },

    markInventoryItemSeen(itemId) {
      this.newInventoryItemIds = this.newInventoryItemIds.filter(id => id !== itemId);
    },

    get isPersonalNoteDirty() {
      return this.personalNote !== this.savedPersonalNote;
    },

    async openPersonalNote() {
      if (!this.selectedCharacterId) return;

      this.showPersonalNoteModal = true;
      this.personalNoteError = '';
      this.isLoadingPersonalNote = true;
      try {
        const res = await fetch(`/api/characters/${this.selectedCharacterId}/personal-note`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Nie udało się wczytać notatki.');
        this.personalNote = data.content || '';
        this.savedPersonalNote = this.personalNote;
        this.$nextTick(() => this.$refs.personalNoteTextarea?.focus());
      } catch (err) {
        this.personalNoteError = err.message;
      } finally {
        this.isLoadingPersonalNote = false;
      }
    },

    closePersonalNote() {
      if (this.isPersonalNoteDirty && !confirm('Zamknąć notes bez zapisania zmian?')) return;
      this.showPersonalNoteModal = false;
      this.personalNoteError = '';
    },

    async savePersonalNote() {
      if (!this.selectedCharacterId || this.isSavingPersonalNote || this.personalNote.length > 20000) return;

      this.personalNoteError = '';
      this.isSavingPersonalNote = true;
      try {
        const res = await fetch(`/api/characters/${this.selectedCharacterId}/personal-note`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: this.personalNote })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Nie udało się zapisać notatki.');
        this.savedPersonalNote = data.content || '';
        this.personalNote = this.savedPersonalNote;
        this.addToast('Notatka została zapisana.', 'success');
      } catch (err) {
        this.personalNoteError = err.message;
      } finally {
        this.isSavingPersonalNote = false;
      }
    },

    statAbbreviation(stat) {
      return this.attributeDefinition(stat).abbreviation;
    },

  };
})();
