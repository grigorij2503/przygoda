(() => {
  'use strict';
  const features = window.TTRPG_FEATURES = window.TTRPG_FEATURES || {};
  features.equipmentImages = {
    // --- Ekwipunek ---
    startItemTransfer(item) {
      this.transferItemId = item.id;
      this.transferRecipientId = this.transferTargets[0]?.id || null;
      this.transferQuantity = 1;
      this.transferError = '';
    },

    async transferItem(item) {
      if (this.isTransferringItem || !item || !this.transferRecipientId) return;
      const quantity = Number(this.transferQuantity);
      if (!Number.isInteger(quantity) || quantity < 1 || quantity > item.quantity) {
        this.transferError = 'Podaj poprawną liczbę sztuk.';
        return;
      }
      this.isTransferringItem = true;
      this.transferError = '';
      try {
        const res = await fetch(`/api/characters/${this.selectedCharacterId}/inventory/${item.id}/transfer`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            recipient_character_id: Number(this.transferRecipientId),
            quantity
          })
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || 'Nie udało się przekazać przedmiotu.');
        const recipient = this.transferTargets.find(character => character.id === Number(this.transferRecipientId));
        this.transferItemId = null;
        await this.fetchSession();
        this.addToast(`Przekazano ${quantity} × ${item.name} do ${recipient?.name || 'wybranej postaci'}.`, 'success');
      } catch (err) {
        this.transferError = err.message;
      } finally {
        this.isTransferringItem = false;
      }
    },

    async toggleEquip(item) {
      if (!item || this.changingEquipmentItemId) return;
      this.changingEquipmentItemId = item.id;
      try {
        const res = await fetch(`/api/characters/${this.selectedCharacterId}/inventory/${item.id}/toggle-equip`, {
          method: 'POST'
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Nie udało się zmienić ekwipunku.');
        this.markInventoryItemSeen(item.id);
        await this.fetchSession();
        if (data.is_equipped) {
          const replaced = data.replaced_item_names?.length
            ? ` Zastępuje: ${data.replaced_item_names.join(', ')}.`
            : '';
          this.addToast(`Założono: ${data.item_name}.${replaced}`, 'success');
        } else {
          this.addToast(`Odłożono do plecaka: ${data.item_name}.`, 'info');
        }
      } catch (err) {
        this.addToast(err.message, 'error');
      } finally {
        this.changingEquipmentItemId = null;
      }
    },

    async useItem(itemId) {
      try {
        const res = await fetch(`/api/characters/${this.selectedCharacterId}/inventory/${itemId}/use`, {
          method: 'POST'
        });
        if (!res.ok) throw new Error('Nie udało się użyć przedmiotu.');
        const data = await res.json();
        this.markInventoryItemSeen(itemId);
        this.addToast(`Użyto przedmiotu. Odzyskano ${data.healed_by} HP! (Aktualne HP: ${data.new_hp})`, 'success');
        await this.fetchSession();
      } catch (err) {
        this.addToast(err.message, 'error');
      }
    },

    canGenerateImage() {
      const limit = this.session?.image_generation;
      if (!limit || limit.can_generate) return true;
      const nextAvailable = Date.parse(limit.next_available_at);
      return Number.isFinite(nextAvailable) && nextAvailable <= this.proxyNow;
    },

    imageGenerationAvailabilityLabel() {
      const nextAvailable = Date.parse(this.session?.image_generation?.next_available_at);
      if (!Number.isFinite(nextAvailable)) return 'Dzienny limit ilustracji został wykorzystany';
      const remainingMinutes = Math.max(1, Math.ceil((nextAvailable - this.proxyNow) / 60000));
      const hours = Math.floor(remainingMinutes / 60);
      const minutes = remainingMinutes % 60;
      if (!hours) return `Ilustracja dostępna za ${minutes} min`;
      if (!minutes) return `Ilustracja dostępna za ${hours} godz.`;
      return `Ilustracja dostępna za ${hours} godz. ${minutes} min`;
    },

    // --- Generowanie Obrazu na Żądanie (Imagen 3) ---
    async generateImage(turnId) {
      try {
        const turn = this.session.turns.find(t => t.id === turnId);
        if (turn) turn.is_generating_image = true;
        this.addToast('Zlecono generowanie ilustracji dla sceny z tury...', 'info');

        const res = await fetch('/api/generate-image', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ turn_id: turnId })
        });
        if (!res.ok) {
          const err = await res.json();
          if (res.status === 429 && err.detail?.next_available_at && this.session) {
            this.session.image_generation = {
              ...(this.session.image_generation || {}),
              can_generate: false,
              next_available_at: err.detail.next_available_at
            };
          }
          throw new Error(err.detail?.message || err.detail || 'Błąd generowania obrazu');
        }
        const data = await res.json();
        if (turn) {
          turn.image_url = data.image_url;
          turn.is_generating_image = false;
        }
        if (this.session?.image_generation && data.next_available_at) {
          this.session.image_generation.can_generate = false;
          this.session.image_generation.next_available_at = data.next_available_at;
        }
        this.addToast('Ilustracja wygenerowana!', 'success');
      } catch (err) {
        this.addToast(err.message, 'error');
        const turn = this.session.turns.find(t => t.id === turnId);
        if (turn) turn.is_generating_image = false;
      }
    },

    openLightbox(imgUrl) {
      this.lightboxImageUrl = imgUrl;
      this.showLightbox = true;
    },

    // --- Generator Wstępu do Kampanii (AI) ---
    async generateIntroAI() {
      this.isGeneratingIntro = true;
      try {
        const selectedWorld = this.selectedWorldSummary;
        const res = await fetch('/api/generate-intro', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            scenario_type: this.scenarioChoice,
            tone: this.scenarioTone,
            world_pack_id: selectedWorld?.id || null,
            world_pack_version: selectedWorld?.version || null
          })
        });
        if (res.status === 403) {
          this.requireGmUnlock();
          return;
        }
        if (!res.ok) throw new Error('Błąd generowania wstępu przez Gemini.');
        const data = await res.json();
        this.generatedIntro = data;
        this.addToast('Wygenerowano nowy zarys kampanii przez Gemini!', 'success');
      } catch (err) {
        this.addToast(err.message, 'error');
      } finally {
        this.isGeneratingIntro = false;
      }
    },

    async applyCampaignReset() {
      if (!this.generatedIntro.campaign_intro) {
        this.addToast('Wygeneruj najpierw wstęp do kampanii.', 'warning');
        return;
      }
      this.isApplyingIntro = true;
      try {
        const res = await fetch('/api/session/reset-campaign', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            room_code: this.roomCode,
            title: this.generatedIntro.title,
            setting_theme: this.generatedIntro.setting_theme,
            campaign_intro: this.generatedIntro.campaign_intro + '\n\n' + this.generatedIntro.first_challenge
          })
        });
        if (res.status === 403) {
          this.requireGmUnlock();
          return;
        }
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || 'Błąd resetowania kampanii.');
        }
        this.showIntroModal = false;
        this.addToast('Nowa kampania rozpoczęta!', 'success');
        await this.fetchSession();
      } catch (err) {
        this.addToast(err.message, 'error');
      } finally {
        this.isApplyingIntro = false;
      }
    }
  };
})();
