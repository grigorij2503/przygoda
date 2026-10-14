(() => {
  'use strict';
  const features = window.TTRPG_FEATURES = window.TTRPG_FEATURES || {};
  features.market = {
    get marketMerchant() {
      return this.session?.market?.merchant || null;
    },

    get marketMerchantPortraitUrl() {
      const themeId = this.session?.world_pack?.theme_id;
      return /^[a-z][a-z0-9_]*$/.test(themeId || '')
        ? `/static/img/merchants/${themeId}.png?v=1`
        : '';
    },

    get marketBanned() {
      return (this.session?.market?.banned || []).includes(this.selectedCharacterId);
    },

    get marketCraftItems() {
      const allowed = new Set(['weapon', 'shield', 'armor', 'helmet', 'boots', 'accessory', 'misc']);
      return (this.currentCharacter?.inventory || []).filter(item =>
        !item.is_equipped && item.quantity > 0 && allowed.has(item.item_type)
      );
    },

    marketPrice(offer) {
      const discount = this.session?.market?.discounts?.[String(this.selectedCharacterId)];
      return discount?.offer_id === offer.id
        ? Math.max(1, Math.ceil(offer.price * (100 - discount.percent) / 100))
        : offer.price;
    },

    marketSellPrice(item) {
      return this.session?.market?.sell_prices?.[String(item.id)] || 0;
    },

    async marketTransaction(operation, offer = null, item = null) {
      if (this.marketBusy || !this.selectedCharacterId) return;
      if (operation === 'sell' && !window.confirm(`Sprzedać 1 × ${item.name} za ${this.marketSellPrice(item)} ${this.currencyLabel}?`)) return;
      this.marketBusy = true;
      this.marketError = '';
      this.marketFeedback = '';
      try {
        const res = await fetch('/api/market/transaction', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            character_id: this.selectedCharacterId,
            operation,
            offer_id: offer?.id || null,
            item_id: item?.id || null
          })
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || 'Nie udało się przeprowadzić transakcji.');
        if (operation === 'haggle') {
          this.marketFeedback = data.success
            ? `Negocjacje udane (${data.total} przeciw DC ${data.dc}). Rabat 15% na ${offer.name}.`
            : `Kupiec nie zgodził się na rabat (${data.total} przeciw DC ${data.dc}).`;
        } else {
          this.marketFeedback = `${operation === 'buy' ? 'Kupiono' : 'Sprzedano'}: ${data.item_name}. ${data.coins_delta > 0 ? '+' : ''}${data.coins_delta} ${this.currencyLabel}.`;
        }
        await this.fetchSession('market');
      } catch (error) {
        this.marketError = error.message;
      } finally {
        this.marketBusy = false;
      }
    },

    async marketInteract() {
      if (this.marketBusy || !this.marketInteractionText.trim()) return;
      this.marketBusy = true;
      this.marketError = '';
      this.marketFeedback = '';
      try {
        const res = await fetch('/api/market/interact', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ character_id: this.selectedCharacterId, text: this.marketInteractionText.trim() })
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || 'Handlarz nie zrozumiał działania.');
        this.marketFeedback = data.message;
        this.marketInteractionText = '';
        await this.fetchSession('market');
      } catch (error) {
        this.marketError = error.message;
      } finally {
        this.marketBusy = false;
      }
    },

    toggleMarketCraftItem(item) {
      const selected = this.marketCraftItemIds;
      if (selected.includes(item.id)) {
        this.marketCraftItemIds = selected.filter(id => id !== item.id);
      } else if (selected.length < 3) {
        const first = this.marketCraftItems.find(candidate => candidate.id === selected[0]);
        if (first && first.item_type !== item.item_type) {
          this.marketError = 'Wybierz trzy przedmioty tego samego typu.';
          return;
        }
        this.marketCraftItemIds = [...selected, item.id];
      }
      this.marketError = '';
    },

    prepareMarketCraft() {
      const items = this.marketCraftItemIds.map(id => this.marketCraftItems.find(item => item.id === id));
      if (items.length !== 3 || items.some(item => !item) || new Set(items.map(item => item.item_type)).size !== 1) {
        this.marketError = 'Wybierz trzy różne przedmioty tego samego typu.';
        return;
      }
      this.actionText = `Scalam trzy przedmioty w warsztacie: ${items.map(item => item.name).join(', ')}.`;
      this.actionIntent = 'interact';
      this.actionTestedStat = 'intellect';
      this.actionTargetRef = null;
      this.magicAbilityId = null;
      this.namedAttackId = null;
      this.actionInterpretation = null;
      this.mobileActionPanelCollapsed = false;
      this.marketError = '';
      this.marketFeedback = 'Przygotowano akcję craftingu. Zatwierdź ją w panelu akcji; wynik rozstrzygnie rzut d20.';
      this.$nextTick(() => document.getElementById('action-description')?.scrollIntoView({ behavior: 'smooth', block: 'center' }));
    },

    async openMarketAsGm() {
      if (this.marketBusy) return;
      this.marketBusy = true;
      this.marketError = '';
      try {
        const res = await fetch(`/api/market/open?room_code=${encodeURIComponent(this.roomCode)}`, { method: 'POST' });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || 'Nie udało się otworzyć postoju.');
        this.showIntroModal = false;
        this.marketFeedback = `${data.merchant.name} rozkłada towary. Postój jest otwarty.`;
        await this.fetchSession('market');
      } catch (error) {
        this.marketError = error.message;
        this.addToast(error.message, 'error');
      } finally {
        this.marketBusy = false;
      }
    }
  };
})();
