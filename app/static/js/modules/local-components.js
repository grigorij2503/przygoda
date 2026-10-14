(() => {
  'use strict';

  const features = window.TTRPG_FEATURES = window.TTRPG_FEATURES || {};
  features.registerLocalComponents = (Alpine) => {
    Alpine.data('infoPopover', () => ({ showInfo: false }));
    Alpine.data('storyHints', (turnId) => ({
      hintTurnId: turnId,
      showHints: false,
      hints: [],
      hintsLoading: false,
      hintsError: '',
      hintsContextual: true,
      hintsContextKey: '',
      hintsRequestId: 0,

      init() {
        this.$watch('tacticalHintsContextKey', () => {
          this.hintsRequestId += 1;
          this.hints = [];
          this.hintsContextKey = '';
          this.hintsLoading = false;
          this.hintsError = '';
          if (!this.canRequestTacticalHints || this.currentStoryTurn?.id !== this.hintTurnId) {
            this.showHints = false;
            return;
          }
          if (this.showHints) this.loadHints();
        });
      },

      get visibleHints() {
        if (!this.canRequestTacticalHints || this.hintsContextKey !== this.tacticalHintsContextKey) return [];
        return this.hints;
      },

      toggleHints() {
        this.showHints = !this.showHints;
        if (this.showHints) this.loadHints();
      },

      async loadHints() {
        if (!this.canRequestTacticalHints || this.currentStoryTurn?.id !== this.hintTurnId) return;
        const key = this.tacticalHintsContextKey;
        if (this.hintsLoading || (this.hintsContextKey === key && this.hints.length)) return;
        const requestId = ++this.hintsRequestId;
        const characterId = this.selectedCharacterId;
        const turnId = this.hintTurnId;
        this.hintsLoading = true;
        this.hintsError = '';
        try {
          const response = await fetch(
            `/api/characters/${characterId}/tactical-hints?turn_id=${turnId}`,
            { cache: 'no-store' }
          );
          const data = await response.json();
          if (requestId !== this.hintsRequestId || key !== this.tacticalHintsContextKey) return;
          if (!response.ok) throw new Error(data.detail || 'Nie udało się pobrać podpowiedzi.');
          if (data.character_id !== characterId || data.turn_id !== turnId) {
            throw new Error('Zmieniła się postać lub tura. Rozwiń podpowiedzi ponownie.');
          }
          this.hints = data.suggested_actions;
          this.hintsContextual = data.contextual;
          this.hintsContextKey = key;
        } catch (error) {
          if (requestId === this.hintsRequestId && key === this.tacticalHintsContextKey) {
            this.hintsError = error.message || 'Nie udało się pobrać podpowiedzi.';
          }
        } finally {
          if (requestId === this.hintsRequestId) this.hintsLoading = false;
        }
      },

      useHint(action) {
        if (!this.visibleHints.includes(action)) return;
        this.setQuickAction(action);
      }
    }));
  };
})();
