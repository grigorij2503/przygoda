(() => {
  'use strict';
  const features = window.TTRPG_FEATURES = window.TTRPG_FEATURES || {};
  features.sessionCharacter = {
    // --- Pobieranie Stanu Sesji ---
    async fetchSession() {
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
        this.isResolvingTurn = Boolean(data.is_turn_resolving);
        if (previousTurnNumber !== undefined && previousTurnNumber !== data.current_turn_number) {
          this.actionText = '';
          this.actionIntent = null;
          this.actionTestedStat = null;
          this.actionTargetRef = null;
          this.magicAbilityId = null;
          this.actionInterpretation = null;
          this.showActionInterpretationControls = false;
          this.isEditingSubmittedAction = false;
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
          if (newlyFoundItems.length) {
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
        if (unspentStatPoints > 0 && (
          previousUnspentStatPoints === undefined ||
          unspentStatPoints > previousUnspentStatPoints
        )) {
          this.showLevelUpModal = true;
        } else if (unspentStatPoints === 0) {
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
      this.actionInterpretation = null;
      this.showActionInterpretationControls = false;
      this.actionError = '';
      this.newInventoryItemIds = [];
      this.inventoryFilter = 'all';
      localStorage.setItem('rpg_selected_char', charId);
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
            localStorage.removeItem('rpg_selected_char');
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

    get magicBook() {
      return this.currentCharacter?.magic_book || null;
    },

    get selectedMagicAbility() {
      return this.magicBook?.abilities?.find(ability => ability.id === this.magicAbilityId) || null;
    },

    get quickActions() {
      const className = (this.currentCharacter?.character_class || '')
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLowerCase();
      const presets = {
        wojownik: [
          { id: 'warrior-strike', icon: '⚔️', label: 'Potężne uderzenie', text: 'Nacieram z pełną siłą i uderzam przeciwnika w najsłabiej chronione miejsce.', intent: 'attack', targetRef: 'boss' },
          { id: 'warrior-guard', icon: '🛡️', label: 'Twarda obrona', text: 'Przyjmuję twardą postawę obronną i skupiam na sobie uwagę przeciwnika.', intent: 'defend' },
          { id: 'warrior-help', icon: '🤝', label: 'Osłoń sojusznika', text: 'Wkraczam między przeciwnika a sojusznika, dając rannemu czas na odzyskanie sił.', intent: 'support' },
          { id: 'warrior-tactics', icon: '👁️', label: 'Oceń pole walki', text: 'Oceniam ustawienie wrogów i szukam słabego punktu ich szyku.', intent: 'other' }
        ],
        lotrzyk: [
          { id: 'rogue-strike', icon: '🗡️', label: 'Precyzyjny atak', text: 'Wykorzystuję lukę w obronie przeciwnika i uderzam w odsłonięty słaby punkt.', intent: 'attack', targetRef: 'boss' },
          { id: 'rogue-flank', icon: '🥷', label: 'Skradanie i flanka', text: 'Znikam w cieniu, obchodzę zagrożenie i zajmuję dogodną pozycję na flance.', intent: 'other' },
          { id: 'rogue-traps', icon: '🪤', label: 'Pułapki i mechanizmy', text: 'Uważnie sprawdzam otoczenie pod kątem pułapek, zamków i ukrytych mechanizmów.', intent: 'interact' },
          { id: 'rogue-distract', icon: '🤝', label: 'Odwróć uwagę', text: 'Odwracam uwagę przeciwnika, aby sojusznik mógł bezpiecznie odzyskać siły.', intent: 'support' }
        ],
        czarodziej: [
          { id: 'wizard-knowledge', icon: '🔍', label: 'Wiedza tajemna', text: 'Analizuję znaki, runy i ślady, aby odkryć naturę zagrożenia.', intent: 'interact' },
          { id: 'wizard-retreat', icon: '🛡️', label: 'Taktyczny odwrót', text: 'Cofam się na bezpieczniejszą pozycję i obserwuję zamiary przeciwnika.', intent: 'defend' },
          { id: 'wizard-guidance', icon: '🤝', label: 'Wskaż rozwiązanie', text: 'Dzielę się swoją wiedzą z sojusznikiem i pomagam mu wykorzystać słabość zagrożenia.', intent: 'support' }
        ],
        kleryk: [
          { id: 'cleric-strike', icon: '🔨', label: 'Stanowczy atak', text: 'Staję naprzeciw zagrożenia i wyprowadzam zdecydowany cios.', intent: 'attack', targetRef: 'boss' },
          { id: 'cleric-guard', icon: '🛡️', label: 'Obrona drużyny', text: 'Zajmuję pozycję między zagrożeniem a drużyną i przygotowuję się do obrony.', intent: 'defend' },
          { id: 'cleric-aid', icon: '🤝', label: 'Pomoc rannemu', text: 'Pomagam rannemu sojusznikowi, opatrując jego obrażenia i przywracając go do walki.', intent: 'support' }
        ]
      };
      const classPresets = presets[className] || [
        { id: 'generic-attack', icon: '⚔️', label: 'Atak', text: 'Atakuję przeciwnika, wykorzystując jego chwilę nieuwagi.', intent: 'attack', targetRef: 'boss' },
        { id: 'generic-defend', icon: '🛡️', label: 'Obrona', text: 'Przyjmuję pozycję obronną i obserwuję ruchy przeciwnika.', intent: 'defend' },
        { id: 'generic-scout', icon: '🔍', label: 'Rozpoznanie', text: 'Ostrożnie badam otoczenie w poszukiwaniu zagrożeń i możliwych dróg działania.', intent: 'other' }
      ];
      const magicPresets = (this.magicBook?.abilities || [])
        .filter(ability => ability.unlocked)
        .slice(0, 3)
        .map(ability => ({
          id: `magic-${ability.id}`,
          icon: ability.icon,
          label: ability.name,
          text: ability.action_text,
          intent: ability.intent,
          targetRef: ability.target_ref,
          magicAbilityId: ability.id
        }));
      return [...classPresets, ...magicPresets];
    },

    get supportTargets() {
      const resurrection = this.magicAbilityId === 'resurrection';
      return (this.session?.characters || []).filter(character =>
        character.id !== this.selectedCharacterId
          && (resurrection ? character.death_state === 'dead' : character.death_state !== 'dead')
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
        ...this.activeItems
      ].filter(Boolean);

      return items.filter((item, index) =>
        items.findIndex(candidate => candidate.id === item.id) === index
      );
    },

    equipmentStatBonus(stat) {
      return this.equippedStatItems.reduce((total, item) => {
        if (item.target_stat !== stat && item.target_stat !== 'all') return total;
        return total + Number(item.stat_bonus || 0);
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
      if (item.stat_bonus <= 0) return damage;
      if (item.target_stat === 'hp_max') return `+${item.stat_bonus} maks. PW`;
      if (item.target_stat === 'all') return `+${item.stat_bonus} wszystkie testy`;
      if (item.target_stat === 'none') return damage;
      const stat = `+${item.stat_bonus} ${this.statAbbreviation(item.target_stat)}`;
      return damage ? `${stat} • ${damage}` : stat;
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
      return {
        strength: 'STR',
        agility: 'AGI',
        intellect: 'INT',
        charisma: 'CHA',
        perception: 'PER'
      }[stat] || String(stat || '').toUpperCase();
    },

  };
})();
