(() => {
  'use strict';
  const features = window.TTRPG_FEATURES = window.TTRPG_FEATURES || {};
  features.campaignActions = {
    // --- Światotwórstwo / Lore Naming ---
    async submitEntityName() {
      const name = this.namingInput.trim();
      if (!name) return;

      this.isSubmittingNaming = true;
      try {
        const res = await fetch('/api/session/name-entity', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: this.session.session_id,
            character_id: this.selectedCharacterId,
            custom_name: name,
            npc_disposition: this.pendingNaming?.category === 'npc' ? this.namingDisposition : null,
            npc_catchphrase: this.pendingNaming?.category === 'npc' ? this.namingCatchphrase.trim() : null,
            npc_goal: this.pendingNaming?.category === 'npc' ? this.namingGoal.trim() : null
          })
        });
        if (!res.ok) {
          const result = await res.json().catch(() => ({}));
          throw new Error(result.detail || 'Błąd zapisu nazwy.');
        }
        this.namingInput = '';
        this.namingDisposition = 'reserved';
        this.namingCatchphrase = '';
        this.namingGoal = '';
        this.showNamingModal = false;
        await this.fetchSession();
      } catch (err) {
        this.addToast(err.message, 'error');
      } finally {
        this.isSubmittingNaming = false;
      }
    },

    async triggerManualNaming(category, description) {
      try {
        const res = await fetch('/api/session/trigger-naming', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: this.session.session_id,
            category: category,
            description: description
          })
        });
        const data = await res.json().catch(() => ({}));
        if (res.status === 403) {
          this.requireGmUnlock();
          return;
        }
        if (!res.ok) throw new Error(data.detail || 'Błąd wywołania eventu.');
        this.showIntroModal = false;
        this.addToast(`Wylosowano gracza: ${data.chosen_character}!`, 'info');
      } catch (err) {
        this.addToast(err.message, 'error');
      }
    },

    // --- Prolog Drużyny & Lobby ---
    async startPartyPrologue() {
      this.isGeneratingPrologue = true;
      try {
        const res = await fetch('/api/session/start-prologue', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            room_code: this.roomCode,
            scenario_type: this.scenarioChoice,
            tone: this.scenarioTone
          })
        });
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || 'Nie udało się wygenerować prologu.');
        }
        await this.fetchSession();
        this.addToast('⚔️ Przygoda rozpoczęta! Prolog wygłoszony.', 'success');
      } catch (err) {
        this.addToast(err.message, 'error');
      } finally {
        this.isGeneratingPrologue = false;
      }
    },

    async toggleReady() {
      if (!this.selectedCharacterId) {
        this.addToast('Wybierz lub stwórz postać, by oznaczyć gotowość!', 'warning');
        return;
      }
      try {
        const res = await fetch(`/api/characters/${this.selectedCharacterId}/toggle-ready`, {
          method: 'POST'
        });
        if (!res.ok) throw new Error('Błąd zmiany statusu gotowości.');
        await this.fetchSession();
      } catch (err) {
        this.addToast(err.message, 'error');
      }
    },

    async setupScenarioLobby() {
      if (this.resetConfirmation !== 'RESETUJ') {
        this.addToast('Wpisz RESETUJ, aby potwierdzić restart kampanii.', 'warning');
        return;
      }
      this.isGeneratingIntro = true;
      try {
        const selectedWorld = this.selectedWorldSummary;
        if (!selectedWorld) throw new Error('Wybierz dostępny świat kampanii.');
        const res = await fetch('/api/session/setup-scenario', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            room_code: this.roomCode,
            world_pack_id: selectedWorld.id,
            world_pack_version: selectedWorld.version,
            scenario_type: this.scenarioChoice,
            tone: this.scenarioTone
          })
        });
        if (res.status === 403) {
          this.requireGmUnlock();
          return;
        }
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || 'Błąd inicjowania poczekalni.');
        }
        this.showIntroModal = false;
        this.resetConfirmation = '';
        this.clearCampaignEndingDraft();
        this.addToast('Nowe lobby kampanii jest gotowe.', 'success');
        await this.fetchSession();
      } catch (err) {
        this.addToast(err.message, 'error');
      } finally {
        this.isGeneratingIntro = false;
      }
    },

    // --- Retry Turn ---
    async retryTurn() {
      this.isRetryingTurn = true;
      this.turnError = '';
      try {
        const res = await fetch(`/api/session/retry-turn?room_code=${this.roomCode}`, {
          method: 'POST'
        });
        if (!res.ok) throw new Error('Błąd ponawiania tury.');
        this.addToast('Ponowiono rozpatrywanie tury przez Gemini!', 'info');
      } catch (err) {
        this.turnError = err.message;
        this.addToast(err.message, 'error');
      } finally {
        this.isRetryingTurn = false;
      }
    },

    // --- Tworzenie Postaci ---
    async createCharacter() {
      this.charError = '';
      if (!this.newChar.name.trim() || !this.newChar.player_name.trim()) {
        this.charError = 'Podaj swoje imię oraz imię bohatera.';
        return;
      }
      if (this.statPointsRemaining < 0) {
        this.charError = 'Wykorzystano zbyt wiele punktów atrybutów!';
        return;
      }

      this.isCreatingChar = true;
      try {
        const res = await fetch(`/api/characters?room_code=${this.roomCode}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.newChar)
        });
        if (!res.ok) {
          const errData = await res.json();
          throw new Error(errData.detail || 'Błąd tworzenia postaci.');
        }
        const data = await res.json();
        await this.fetchSession();
        this.selectCharacter(data.character_id);
        this.showCharModal = false;
        this.addToast(`Witaj w drużynie, ${this.newChar.name}!`, 'success');
      } catch (err) {
        this.charError = err.message;
      } finally {
        this.isCreatingChar = false;
      }
    },

    statLabel(stat) {
      return this.attributeDefinition(stat).label;
    },

    async spendStatPoint(stat) {
      if (!this.selectedCharacterId || this.isSpendingStatPoint) return;

      this.statPointError = '';
      this.isSpendingStatPoint = true;
      try {
        const res = await fetch(`/api/characters/${this.selectedCharacterId}/spend-stat-point`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ stat })
        });
        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || 'Nie udało się przydzielić punktu atrybutu.');
        }

        await this.fetchSession();
        this.showLevelUpModal = data.unspent_stat_points > 0;
        this.addToast(`Zwiększono atrybut ${this.statLabel(stat)} do +${data.stat_value}.`, 'success');
      } catch (err) {
        this.statPointError = err.message;
      } finally {
        this.isSpendingStatPoint = false;
      }
    },

    // --- Składanie Akcji ---
    get actionMentionOptions() {
      if (!this.actionMention || this.actionMention.text !== this.actionText) return [];
      const normalize = value => value.normalize('NFC').toLocaleLowerCase('pl-PL');
      const characters = (this.session?.characters || []).filter(character =>
        character.participation_status !== 'on_break' && character.name?.trim()
      );
      const counts = new Map();
      characters.forEach(character => {
        const name = normalize(character.name);
        counts.set(name, (counts.get(name) || 0) + 1);
      });
      const query = normalize(this.actionMention.query);
      return characters
        .filter(character => counts.get(normalize(character.name)) === 1 &&
          normalize(character.name).startsWith(query))
        .map(character => ({ id: character.id, name: character.name }))
        .sort((left, right) => left.name.localeCompare(right.name, 'pl-PL'));
    },

    updateActionMention(input) {
      const end = input.selectionStart;
      const before = input.value.slice(0, end);
      const match = before.match(/(^|[^\p{L}\p{N}\p{M}_@])@([^@\n"„“”]*)$/u);
      this.actionMention = match && input.selectionStart === input.selectionEnd
        ? { start: match.index + match[1].length, end, query: match[2], text: input.value }
        : null;
      this.actionMentionIndex = 0;
    },

    actionDialogueClosingQuoteAt(position) {
      const closingQuotes = { '"': '"', '„': '”', '“': '”' };
      let closingQuote = null;
      for (const character of this.actionText.slice(0, position)) {
        if (closingQuote) {
          if (character === closingQuote) closingQuote = null;
        } else {
          closingQuote = closingQuotes[character] || null;
        }
      }
      return closingQuote;
    },

    selectActionMention(option) {
      if (!this.actionMention || this.actionMention.text !== this.actionText || !option) return;
      const { start, end } = this.actionMention;
      const closingQuote = this.actionDialogueClosingQuoteAt(start);
      let insertion = `@${option.name} `;
      let after = this.actionText.slice(end);
      let caret = start + insertion.length;
      if (!closingQuote) {
        // Picking a recipient always inserts speech, even outside an existing quote.
        insertion = `"${insertion}"`;
        caret = start + insertion.length - 1;
      } else if (!after.includes(closingQuote)) {
        after += closingQuote;
      }
      this.actionText = this.actionText.slice(0, start) + insertion + after;
      this.actionMention = null;
      this.actionInterpretation = null;
      this.actionInterpretationRequestId += 1;
      this.marketCraftItemIds = [];
      this.$nextTick(() => {
        const input = this.$refs.actionInput;
        if (!input) return;
        input.focus();
        input.setSelectionRange(caret, caret);
      });
      this.interpretAction();
    },

    handleActionMentionKey(event) {
      if (event.isComposing) return;
      if (event.key === 'Tab' && event.shiftKey) {
        this.actionMention = null;
        return;
      }
      if (event.target.selectionStart !== event.target.selectionEnd) {
        this.actionMention = null;
        return;
      }
      if (event.key === 'Escape' && this.actionMention) {
        event.preventDefault();
        event.stopPropagation();
        this.actionMention = null;
        return;
      }
      const options = this.actionMentionOptions;
      if (!options.length) return;
      const currentIndex = Math.min(this.actionMentionIndex, options.length - 1);
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        const step = event.key === 'ArrowDown' ? 1 : -1;
        this.actionMentionIndex = (currentIndex + step + options.length) % options.length;
        this.$nextTick(() => {
          document.getElementById(`action-mention-${this.actionMentionIndex}`)
            ?.scrollIntoView({ block: 'nearest' });
        });
      } else if (event.key === 'Enter' || event.key === 'Tab') {
        event.preventDefault();
        event.stopPropagation();
        this.selectActionMention(options[currentIndex]);
      }
    },

    effectiveActionIntent() {
      return this.actionIntent || this.actionInterpretation?.intent;
    },

    async interpretAction() {
      const actionText = this.actionText.trim();
      if (!this.selectedCharacterId || !actionText) {
        this.actionInterpretationRequestId += 1;
        this.actionInterpretation = null;
        this.isInterpretingAction = false;
        return;
      }

      const requestId = ++this.actionInterpretationRequestId;
      this.isInterpretingAction = true;
      try {
        const res = await fetch('/api/actions/interpret', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            character_id: this.selectedCharacterId,
            action_text: actionText,
            magic_ability_id: this.magicAbilityId,
            ability_id: this.magicAbilityId,
            named_attack_id: this.namedAttackId,
            intent: this.actionIntent,
            tested_stat: this.actionTestedStat,
            target_ref: this.actionTargetRef,
            craft_item_ids: this.marketCraftItemIds.length === 3 ? this.marketCraftItemIds : null
          })
        });
        if (!res.ok) return;
        const interpretation = await res.json();
        if (requestId !== this.actionInterpretationRequestId) return;
        this.actionInterpretation = interpretation;
      } catch (_) {
        // Podgląd jest pomocniczy; właściwe zatwierdzenie nadal waliduje akcję na backendzie.
      } finally {
        if (requestId === this.actionInterpretationRequestId) this.isInterpretingAction = false;
      }
    },

    beginActionInterpretationCorrection() {
      if (!this.actionInterpretation || this.magicAbilityId) return;
      this.actionIntent = this.actionInterpretation.intent;
      this.actionTestedStat = this.actionInterpretation.tested_stat;
      this.showActionInterpretationControls = true;
    },

    clearActionInterpretationCorrection() {
      if (this.magicAbilityId) return;
      this.actionIntent = null;
      this.actionTestedStat = null;
      this.showActionInterpretationControls = false;
      this.interpretAction();
    },

    async submitAction() {
      if (!this.actionText.trim()) {
        this.actionError = 'Wpisz treść akcji dla swojej postaci.';
        return;
      }
      if (!this.selectedCharacterId) {
        this.actionError = 'Musisz najpierw wybrać swoją postać.';
        return;
      }
      if (this.effectiveActionIntent() === 'support' && !this.actionTargetRef) {
        this.actionError = 'Wybierz sojusznika, którego wspierasz.';
        return;
      }

      this.actionError = '';
      this.isSubmittingAction = true;
      try {
        const res = await fetch('/api/actions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            character_id: this.selectedCharacterId,
            action_text: this.actionText.trim(),
            magic_ability_id: this.magicAbilityId,
            ability_id: this.magicAbilityId,
            named_attack_id: this.namedAttackId,
            intent: this.actionIntent,
            tested_stat: this.actionTestedStat,
            target_ref: this.actionTargetRef
          })
        });
        if (!res.ok) {
          const responseText = await res.text();
          let detail = '';
          try {
            detail = JSON.parse(responseText).detail || '';
          } catch (_) {
            detail = responseText;
          }
          throw new Error(detail || 'Nie udało się złożyć akcji.');
        }
        const data = await res.json();
        this.isEditingSubmittedAction = false;
        this.mobileActionPanelCollapsed = true;
        if (data.ready_count >= data.total_players && data.total_players > 0) {
          this.addToast(`Wszyscy gracze (${data.ready_count}/${data.total_players}) zatwierdzili akcje! Możesz teraz wygenerować kolejną turę.`, 'success');
        } else {
          this.addToast(`Akcja zatwierdzona! Oczekujemy na resztę drużyny (${data.ready_count}/${data.total_players}).`, 'success');
        }
        await this.fetchSession();
      } catch (err) {
        this.actionError = err.message;
      } finally {
        this.isSubmittingAction = false;
      }
    },

    // --- Ręczne rozstrzyganie tury ---
    async triggerTurnResolution() {
      if (this.session?.is_turn_resolving || this.isResolvingTurn) return;
      this.isResolvingTurn = true;
      try {
        const res = await fetch('/api/session/resolve-turn', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ room_code: this.roomCode })
        });
        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || 'Błąd rozstrzygania tury.');
        }
        this.addToast('⚔️ Mistrz Gry rozstrzyga turę! Rzut kośćmi i generowanie fabuły w toku...', 'info');
      } catch (err) {
        this.addToast(err.message, 'error');
      } finally {
        this.isResolvingTurn = false;
      }
    },

    editCurrentAction() {
      const curTurn = this.session?.turns?.find(t => t.turn_number === this.session?.current_turn_number);
      if (curTurn) {
        const myAction = curTurn.actions?.find(a => a.character_id === this.selectedCharacterId);
        if (myAction) {
          this.actionText = myAction.action_text;
          this.magicAbilityId = myAction.ability_id || myAction.magic_ability_id || null;
          this.namedAttackId = myAction.named_attack_id || null;
          this.actionIntent = this.magicAbilityId ? (myAction.intent || null) : null;
          this.actionTestedStat = null;
          this.actionTargetRef = myAction.target_ref || null;
          this.actionInterpretation = {
            intent: myAction.intent,
            tested_stat: myAction.tested_stat,
            intent_confidence: 1,
            stat_confidence: 1,
            reason: 'interpretacja zapisana przy zgłoszeniu akcji'
          };
          this.showActionInterpretationControls = false;
        }
      }
      this.isEditingSubmittedAction = true;
      this.mobileActionPanelCollapsed = false;
      this.$nextTick(() => {
        const textarea = document.querySelector('textarea[x-model="actionText"]');
        if (textarea) {
          textarea.scrollIntoView({ behavior: 'smooth', block: 'center' });
          textarea.focus();
        }
      });
    },

    setQuickAction(text, intent = null, targetRef = null, testedStat = null) {
      this.actionText = text;
      this.marketCraftItemIds = [];
      this.magicAbilityId = null;
      this.namedAttackId = null;
      this.actionIntent = intent;
      this.actionTestedStat = testedStat;
      this.actionTargetRef = targetRef;
      this.actionInterpretation = null;
      this.showActionInterpretationControls = false;
      this.actionError = '';
      this.mobileActionPanelCollapsed = false;
      this.$nextTick(() => {
        const textarea = document.querySelector('textarea[x-model="actionText"]');
        if (textarea) {
          textarea.scrollIntoView({ behavior: 'smooth', block: 'center' });
          textarea.focus();
        }
      });
      this.interpretAction();
      this.addToast('⚡ Wybrano ścieżkę działania – możesz ją dostosować przed zatwierdzeniem!', 'info');
    },

    selectQuickAction(action) {
      if (action?.magicAbilityId) {
        const ability = this.magicBook?.abilities?.find(item => item.id === action.magicAbilityId);
        if (ability) this.selectMagicAbility(ability);
        return;
      }
      this.setQuickAction(
        action.action_text || action.text,
        action.intent || null,
        action.target_ref ?? action.targetRef ?? null,
        action.tested_stat || null
      );
    },

    get canRequestTacticalHints() {
      const character = this.currentCharacter;
      return Boolean(
        this.session?.status === 'in_progress'
        && !this.session.is_turn_resolving
        && this.currentStoryTurn?.status === 'waiting_for_actions'
        && character?.is_alive
        && (character.death_state || 'alive') === 'alive'
        && character.participation_status !== 'on_break'
      );
    },

    get tacticalHintsContextKey() {
      if (!this.canRequestTacticalHints) return '';
      const character = this.currentCharacter;
      const turn = this.currentStoryTurn;
      const party = (this.session.characters || [])
        .filter(member => member.participation_status !== 'on_break' && member.death_state !== 'dead')
        .map(member => [
          member.id, member.name, member.character_class, member.narrative_form,
          member.current_hp, member.max_hp, member.is_alive, member.death_state,
          member.status_effects
        ]);
      return JSON.stringify([
        this.session.session_id, this.session.room_code, this.session.world_pack_id,
        this.session.world_pack_version, this.session.title, this.session.setting_theme, this.session.campaign_intro,
        turn.id, turn.turn_number, turn.next_turn_prompt, turn.gm_narration,
        this.latestResolvedTurn?.gm_narration || '',
        this.activeEnemy?.name, this.activeEnemy?.title, this.activeEnemy?.hp, character.id,
        character.strength, character.agility, character.intellect,
        character.charisma, character.perception, party,
        (character.inventory || []).map(item => [
          item.id, item.name, item.description, item.item_type, item.quantity, item.is_equipped
        ])
      ]);
    },

    availableSuggestedActions(actions) {
      if (!Array.isArray(actions)) return [];
      const phrases = this.session?.world_pack?.ability_action_phrases || [];
      const normalize = value => String(value || '')
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLowerCase();
      return actions.filter(action => {
        if (typeof action !== 'string' || !action.trim()) return false;
        const normalized = normalize(action);
        return !phrases.some(phrase => {
          const marker = normalize(phrase).trim();
          return marker && normalized.includes(marker);
        });
      });
    },

    selectMagicAbility(ability) {
      if (!ability?.unlocked) return;
      this.actionText = ability.action_text;
      this.marketCraftItemIds = [];
      this.magicAbilityId = ability.id;
      this.namedAttackId = null;
      this.actionIntent = ability.intent || null;
      this.actionTestedStat = ability.tested_stat || this.abilityBook?.casting_stat || null;
      this.actionTargetRef = ability.target_ref || null;
      this.actionInterpretation = null;
      this.showActionInterpretationControls = false;
      this.mobileActionPanelCollapsed = false;
      this.actionError = '';
      this.$nextTick(() => {
        const textarea = document.querySelector('textarea[x-model="actionText"]');
        if (textarea) {
          textarea.scrollIntoView({ behavior: 'smooth', block: 'center' });
          textarea.focus();
        }
      });
      this.interpretAction();
      this.addToast(`Wybrano: ${ability.name}. Możesz dopisać cel lub sposób wykonania.`, 'info');
    },

    selectNamedAttack(attack) {
      if (!attack || !(this.activeEnemy?.hp > 0)) return;
      this.actionText = `Atakuję przeciwnika techniką ${attack.name}.`;
      this.magicAbilityId = null;
      this.namedAttackId = attack.id;
      this.actionIntent = 'attack';
      this.actionTestedStat = null;
      this.actionTargetRef = null;
      this.actionInterpretation = null;
      this.showActionInterpretationControls = false;
      this.mobileActionPanelCollapsed = false;
      this.actionError = '';
      this.$nextTick(() => {
        const textarea = document.querySelector('textarea[x-model="actionText"]');
        if (textarea) textarea.focus();
      });
      this.interpretAction();
      this.addToast(`Wybrano technikę ${attack.name}: +1 obrażenie przy trafieniu.`, 'info');
    },

    setEncounterAction(feature) {
      if (!feature || feature.state !== 'active') return;
      this.setQuickAction(
        `Wykorzystuję element areny „${feature.name}”: ${feature.description}`,
        'interact',
        feature.id
      );
    },

    statusClass(effect) {
      return {
        orange: 'status-effect--orange',
        green: 'status-effect--green',
        cyan: 'status-effect--cyan',
        yellow: 'status-effect--yellow',
        rose: 'status-effect--rose',
        blue: 'status-effect--blue'
      }[effect?.tone] || 'status-effect--neutral';
    },

    statusTooltip(effect) {
      const turns = effect?.turns_remaining ?? 0;
      const duration = turns >= 90 ? 'Efekt fazy.' : `Pozostało tur: ${turns}.`;
      return `${effect?.label || 'Efekt'}: ${effect?.description || ''} ${duration} Moc: ${effect?.potency || 1}.`;
    },

    statShortLabel(stat) {
      return this.attributeDefinition(stat).abbreviation;
    },

    intentLabel(intent) {
      return {
        attack: 'atak', defend: 'obrona', interact: 'interakcja', support: 'wsparcie', other: 'inna akcja'
      }[intent] || intent;
    },

    targetLabel(targetRef) {
      if (!targetRef) return '';
      if (targetRef === 'enemy' || targetRef === 'boss') {
        return this.activeEnemy?.name || this.enemyProfile.role_label || 'przeciwnik';
      }
      const character = (this.session?.characters || []).find(item => String(item.id) === String(targetRef));
      if (character) return character.name;
      const feature = (this.activeEnemy?.features || []).find(item => item.id === targetRef);
      return feature?.name || targetRef;
    },

    deathStateLabel(character) {
      return {
        alive: 'ŻYWY',
        downed: `AGONIA ${character?.death_failures || 0}/3`,
        stable: 'STABILNY',
        dead: 'POLEGŁY'
      }[character?.death_state || 'alive'];
    },

    deathStateClass(character) {
      return {
        alive: 'bg-emerald-950 border border-emerald-600/40 text-emerald-300',
        downed: 'bg-rose-950 border border-rose-500/70 text-rose-200',
        stable: 'bg-cyan-950 border border-cyan-600/50 text-cyan-200',
        dead: 'bg-slate-950 border border-slate-600 text-slate-300'
      }[character?.death_state || 'alive'];
    },

  };
})();
