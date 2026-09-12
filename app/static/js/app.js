document.addEventListener('alpine:init', () => {
  Alpine.data('rpgGame', () => ({
    // Auth & Room
    roomCode: 'kampania-1',
    roomPassword: '',
    isAuthenticated: false,
    authError: '',
    isLoggingIn: false,

    // Session data
    session: null,
    isLoadingSession: true,
    selectedCharacterId: null,

    // Turn Actions & Error
    actionText: '',
    actionIntent: null,
    actionTargetRef: null,
    magicAbilityId: null,
    isSubmittingAction: false,
    actionError: '',
    turnError: '',
    isRetryingTurn: false,
    isResolvingTurn: false,
    isEditingSubmittedAction: false,

    // Story log navigation
    showStoryArchive: false,
    expandedStoryTurnIds: [],
    hasUnreadTurn: false,

    // Compact sticky controls on narrow screens
    mobileHeaderCollapsed: true,
    mobileActionPanelCollapsed: true,

    // Modals
    showCharModal: false,
    showIntroModal: false,
    showGmAuthModal: false,
    showLightbox: false,
    showNamingModal: false,
    showLoreBookModal: false,
    showPersonalNoteModal: false,
    showMapModal: false,
    showLevelUpModal: false,
    showProxyActionModal: false,
    lightboxImageUrl: '',

    // Akcje zastępcze drużyny
    proxyTargetCharacterId: null,
    proxyVoteError: '',
    isSubmittingProxyVote: false,
    proxyNow: Date.now(),
    proxyClockOffset: 0,
    proxyClockTimer: null,

    // Personal Note
    personalNote: '',
    savedPersonalNote: '',
    personalNoteError: '',
    isLoadingPersonalNote: false,
    isSavingPersonalNote: false,

    // Campaign Map
    selectedMapNodeId: null,

    // Level Up
    isSpendingStatPoint: false,
    statPointError: '',
    maxBaseStat: 12,

    // Character Form
    newChar: {
      player_name: '',
      name: '',
      character_class: 'Wojownik',
      strength: 2,
      agility: 1,
      intellect: 1,
      charisma: 0
    },
    charError: '',
    isCreatingChar: false,

    // Campaign Intro & Prologue
    scenarioChoice: 'Krasnoludzka Twierdza opanowana przez demony ognia',
    scenarioTone: 'Mroczne Dark Fantasy z elementami horroru i tajemnicy',
    generatedIntro: {
      title: '',
      setting_theme: '',
      campaign_intro: '',
      first_challenge: ''
    },
    isGeneratingIntro: false,
    isApplyingIntro: false,
    isGeneratingPrologue: false,
    isGmAuthenticated: false,
    isAuthenticatingGm: false,
    gmPin: '',
    gmAuthError: '',
    resetConfirmation: '',

    // Party Chat
    chatMessages: [],
    chatInput: '',
    chatSessionId: null,
    chatMention: null,
    chatMentionIndex: 0,

    // Lore Naming System
    pendingNaming: null, // {category, description, prompt, character_id, character_name}
    namingInput: '',
    isSubmittingNaming: false,

    // WebSockets
    ws: null,
    wsConnected: false,
    wsReconnectTimer: null,
    toasts: [],
    notificationCount: 0,
    baseTitle: document.title,
    notificationSoundEnabled: localStorage.getItem('rpg_notification_sound') !== 'off',
    notificationAudio: null,
    notificationLastSound: 0,
    notificationFocusHandler: null,
    notificationUnlockHandler: null,
    pushSupported: false,
    pushConfigured: false,
    pushEnabled: false,
    pushPermission: 'default',
    pushBusy: false,
    pushPublicKey: '',
    serviceWorkerRegistration: null,

    // Inventory
    newInventoryItemIds: [],
    changingEquipmentItemId: null,
    inventoryFilter: 'all',

    // PWA & Network
    deferredInstallPrompt: null,
    canInstallPWA: false,
    isPWAInstalled: false,
    isOffline: !navigator.onLine,

    init() {
      this.notificationFocusHandler = () => {
        if (!document.hidden && document.hasFocus()) this.clearNotifications();
      };
      this.notificationUnlockHandler = () => this.unlockNotificationAudio();
      document.addEventListener('visibilitychange', this.notificationFocusHandler);
      window.addEventListener('focus', this.notificationFocusHandler);
      document.addEventListener('pointerup', this.notificationUnlockHandler);
      document.addEventListener('keydown', this.notificationUnlockHandler);
      // Rejestracja Service Workera
      this.registerServiceWorker();

      // Nasłuchiwanie zdarzeń sieciowych (Online/Offline)
      window.addEventListener('online', () => {
        this.isOffline = false;
        this.addToast('Połączenie z siecią zostało przywrócone!', 'success');
        if (this.isAuthenticated) this.fetchSession();
      });
      window.addEventListener('offline', () => {
        this.isOffline = true;
        this.addToast('Utracono połączenie z siecią. Jesteś w trybie offline.', 'warning');
      });

      this.proxyClockTimer = setInterval(() => {
        this.proxyNow = Date.now() + this.proxyClockOffset;
        if (this.isAuthenticated && this.hasOpenProxyDecision) this.fetchSession();
      }, 60000);

      // Obsługa instalacji PWA
      window.addEventListener('beforeinstallprompt', (e) => {
        e.preventDefault();
        this.deferredInstallPrompt = e;
        this.canInstallPWA = true;
      });

      window.addEventListener('appinstalled', () => {
        this.canInstallPWA = false;
        this.deferredInstallPrompt = null;
        this.isPWAInstalled = true;
        this.addToast('Aplikacja RPG została zainstalowana!', 'success');
      });

      if (window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true) {
        this.isPWAInstalled = true;
      }

      // Sprawdź zapisaną sesję w localStorage
      const savedPw = localStorage.getItem('rpg_room_pw');
      const savedChar = localStorage.getItem('rpg_selected_char');
      if (savedPw) {
        this.roomPassword = savedPw;
        this.login(true);
      }
      if (savedChar) {
        this.selectedCharacterId = parseInt(savedChar, 10);
      }
    },

    // --- Rejestracja Service Workera i Instalacja PWA ---
    async registerServiceWorker() {
      if ('serviceWorker' in navigator) {
        try {
          const registration = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
          this.serviceWorkerRegistration = registration;
          logger('Service Worker zarejestrowany, scope:', registration.scope);
          await this.refreshPushState();
        } catch (err) {
          console.warn('Rejestracja Service Workera nie powiodła się:', err);
        }
      }
    },

    get pushButtonLabel() {
      if (this.pushBusy) return '⏳ Push...';
      if (!this.pushSupported) return 'Push niedostępny';
      if (this.pushEnabled) return '📲 Push wł.';
      if (!this.pushConfigured) return 'Push nieskonfig.';
      if (this.pushPermission === 'denied') return 'Push zablokowany';
      return '📵 Push wył.';
    },

    get pushButtonTitle() {
      if (!this.pushSupported) return 'Ta przeglądarka lub połączenie nie obsługuje Web Push.';
      if (!this.pushConfigured) return 'Serwer nie ma jeszcze skonfigurowanych kluczy VAPID.';
      if (this.pushPermission === 'denied') return 'Powiadomienia są zablokowane w ustawieniach przeglądarki lub systemu.';
      return this.pushEnabled
        ? 'Wyłącz systemowe powiadomienia o wzmiankach i zakończeniu tury.'
        : 'Włącz systemowe powiadomienia o wzmiankach i zakończeniu tury.';
    },

    async refreshPushState() {
      this.pushSupported = Boolean(
        window.isSecureContext &&
        'serviceWorker' in navigator &&
        'PushManager' in window &&
        'Notification' in window
      );
      this.pushPermission = 'Notification' in window ? Notification.permission : 'denied';
      if (!this.pushSupported || !this.serviceWorkerRegistration) return;

      try {
        const res = await fetch('/api/push/config');
        if (!res.ok) throw new Error('Nie udało się pobrać konfiguracji Web Push.');
        const config = await res.json();
        this.pushConfigured = config.configured === true;
        this.pushPublicKey = config.public_key || '';
        const subscription = await this.serviceWorkerRegistration.pushManager.getSubscription();
        this.pushEnabled = Boolean(subscription);
        if (subscription && this.isAuthenticated && this.selectedCharacterId && this.pushConfigured) {
          await this.savePushSubscription(subscription);
        }
      } catch (error) {
        console.warn('Nie udało się sprawdzić Web Push:', error);
      }
    },

    urlBase64ToUint8Array(value) {
      const padding = '='.repeat((4 - value.length % 4) % 4);
      const base64 = (value + padding).replace(/-/g, '+').replace(/_/g, '/');
      const raw = window.atob(base64);
      return Uint8Array.from([...raw].map(character => character.charCodeAt(0)));
    },

    async savePushSubscription(subscription) {
      if (!this.isAuthenticated || !this.selectedCharacterId) {
        throw new Error('Wybierz postać przed włączeniem powiadomień push.');
      }
      const res = await fetch('/api/push/subscriptions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          room_code: this.roomCode,
          password: this.roomPassword,
          character_id: this.selectedCharacterId,
          subscription: subscription.toJSON()
        })
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'Nie udało się zapisać subskrypcji push.');
    },

    async syncPushSubscription() {
      if (!this.pushEnabled || !this.pushConfigured || !this.serviceWorkerRegistration || !this.selectedCharacterId) return;
      try {
        const subscription = await this.serviceWorkerRegistration.pushManager.getSubscription();
        if (subscription) await this.savePushSubscription(subscription);
      } catch (error) {
        console.warn('Nie udało się zsynchronizować subskrypcji push:', error);
      }
    },

    async enablePushNotifications() {
      if (!this.pushSupported) throw new Error('Web Push nie jest dostępny w tej przeglądarce lub bez HTTPS.');
      if (!this.pushConfigured) throw new Error('Administrator nie skonfigurował jeszcze kluczy VAPID.');
      if (!this.selectedCharacterId) throw new Error('Najpierw wybierz postać.');

      const permission = await Notification.requestPermission();
      this.pushPermission = permission;
      if (permission !== 'granted') {
        throw new Error('Nie udzielono zgody na powiadomienia. Zmień ją w ustawieniach przeglądarki.');
      }

      let subscription = await this.serviceWorkerRegistration.pushManager.getSubscription();
      if (!subscription) {
        subscription = await this.serviceWorkerRegistration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: this.urlBase64ToUint8Array(this.pushPublicKey)
        });
      }

      try {
        await this.savePushSubscription(subscription);
      } catch (error) {
        await subscription.unsubscribe().catch(() => {});
        throw error;
      }
      this.pushEnabled = true;
      this.addToast('Powiadomienia push zostały włączone.', 'success');
    },

    async disablePushNotifications(silent = false) {
      const subscription = await this.serviceWorkerRegistration?.pushManager.getSubscription();
      if (subscription) {
        try {
          await fetch('/api/push/subscriptions', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              password: this.roomPassword,
              endpoint: subscription.endpoint
            })
          });
        } catch (error) {
          console.warn('Nie udało się usunąć subskrypcji push z serwera:', error);
        }
        await subscription.unsubscribe().catch(() => {});
      }
      this.pushEnabled = false;
      if (!silent) this.addToast('Powiadomienia push zostały wyłączone.', 'info');
    },

    async togglePushNotifications() {
      if (this.pushBusy) return;
      this.pushBusy = true;
      try {
        if (this.pushEnabled) {
          await this.disablePushNotifications();
        } else {
          await this.enablePushNotifications();
        }
      } catch (error) {
        const iosHint = /iphone|ipad|ipod/i.test(navigator.userAgent) && !this.isPWAInstalled
          ? ' Na iPhonie dodaj aplikację do ekranu początkowego i uruchom ją z ikony.'
          : '';
        this.addToast(`${error.message}${iosHint}`, 'error');
      } finally {
        this.pushBusy = false;
      }
    },

    async installPWA() {
      if (!this.deferredInstallPrompt) return;
      this.deferredInstallPrompt.prompt();
      const choice = await this.deferredInstallPrompt.userChoice;
      if (choice && choice.outcome === 'accepted') {
        this.canInstallPWA = false;
      }
      this.deferredInstallPrompt = null;
    },

    // --- Powiadomienia Toast ---
    clearNotifications() {
      this.notificationCount = 0;
      document.title = this.baseTitle;
    },

    unlockNotificationAudio() {
      if (!this.notificationSoundEnabled) return;
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextClass) return;
      try {
        if (!this.notificationAudio) this.notificationAudio = new AudioContextClass();
        if (this.notificationAudio.state === 'suspended') {
          this.notificationAudio.resume().catch(() => {});
        }
      } catch (error) {
        // Title notifications remain available when browser audio is blocked.
      }
    },

    toggleNotificationSound() {
      this.notificationSoundEnabled = !this.notificationSoundEnabled;
      localStorage.setItem('rpg_notification_sound', this.notificationSoundEnabled ? 'on' : 'off');
      if (this.notificationSoundEnabled) this.unlockNotificationAudio();
    },

    notifyGameEvent() {
      if (!this.isAuthenticated) return;
      if (document.hidden || !document.hasFocus()) {
        this.notificationCount += 1;
        document.title = `(${this.notificationCount}) ${this.baseTitle}`;
      }
      const context = this.notificationAudio;
      if (!this.notificationSoundEnabled || context?.state !== 'running') return;
      const now = performance.now();
      if (this.notificationLastSound && now - this.notificationLastSound < 1000) return;
      this.notificationLastSound = now;
      try {
        const oscillator = context.createOscillator();
        const gain = context.createGain();
        const start = context.currentTime;
        oscillator.type = 'sine';
        oscillator.frequency.setValueAtTime(660, start);
        oscillator.frequency.setValueAtTime(880, start + 0.12);
        gain.gain.setValueAtTime(0, start);
        gain.gain.linearRampToValueAtTime(0.1, start + 0.02);
        gain.gain.linearRampToValueAtTime(0, start + 0.3);
        oscillator.connect(gain);
        gain.connect(context.destination);
        oscillator.onended = () => { oscillator.disconnect(); gain.disconnect(); };
        oscillator.start(start);
        oscillator.stop(start + 0.32);
      } catch (error) {
        // Audio failure must not interrupt incoming chat or turn updates.
      }
    },

    addToast(message, type = 'info') {
      const id = Date.now();
      this.toasts.push({ id, message, type });
      setTimeout(() => {
        this.toasts = this.toasts.filter(t => t.id !== id);
      }, 5000);
    },

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

    // --- Pobieranie Stanu Sesji ---
    async fetchSession() {
      const previousUnspentStatPoints = this.currentCharacter?.unspent_stat_points;
      const previousCharacterId = this.currentCharacter?.id;
      const previousInventoryItemIds = previousCharacterId
        ? new Set(this.currentCharacter.inventory.map(item => item.id))
        : null;
      this.isLoadingSession = true;
      try {
        const res = await fetch(`/api/session?room_code=${this.roomCode}`);
        if (!res.ok) throw new Error('Błąd ładowania sesji.');
        const data = await res.json();
        this.session = data;
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
      } catch (err) {
        this.addToast(err.message, 'error');
      } finally {
        this.isLoadingSession = false;
      }
    },

    selectCharacter(charId) {
      this.selectedCharacterId = charId;
      this.magicAbilityId = null;
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
        charisma: 'CHA'
      }[stat] || String(stat || '').toUpperCase();
    },

    get hasSubmittedCurrentTurn() {
      if (this.isEditingSubmittedAction) return false;
      if (!this.session || !this.selectedCharacterId) return false;
      const curTurn = this.session.turns.find(t => t.turn_number === this.session.current_turn_number);
      if (!curTurn) return false;
      return curTurn.actions.some(a => a.character_id === this.selectedCharacterId);
    },

    get storyTurnsDescending() {
      if (!this.session?.turns) return [];
      return [...this.session.turns].sort((a, b) => b.turn_number - a.turn_number);
    },

    get currentStoryTurn() {
      if (!this.session) return null;
      return this.storyTurnsDescending.find(
        turn => turn.turn_number === this.session.current_turn_number
      ) || null;
    },

    get campaignMap() {
      return this.session?.campaign_map || null;
    },

    get currentMapNode() {
      return this.campaignMap?.nodes?.find(
        node => node.id === this.campaignMap.current_node_id
      ) || null;
    },

    get visitedMapNodes() {
      return (this.campaignMap?.nodes || [])
        .filter(node => ['current', 'visited'].includes(node.visibility))
        .sort((first, second) => (first.visit_order || 0) - (second.visit_order || 0));
    },

    get selectedMapNode() {
      return this.visitedMapNodes.find(node => node.id === this.selectedMapNodeId)
        || this.currentMapNode;
    },

    openMap() {
      this.selectedMapNodeId = this.campaignMap?.current_node_id || null;
      this.showMapModal = true;
      this.scheduleMapRender();
    },

    selectMapNode(nodeId) {
      if (!this.visitedMapNodes.some(node => node.id === nodeId)) return;
      this.selectedMapNodeId = nodeId;
      this.scheduleMapRender();
    },

    scheduleMapRender() {
      this.$nextTick(() => this.renderCampaignMap());
    },

    renderCampaignMap() {
      const drawing = this.$refs.campaignMapDrawing;
      const map = this.campaignMap;
      if (!drawing || !map) return;

      const svgNamespace = 'http://www.w3.org/2000/svg';
      const createSvgElement = (tagName, attributes = {}, textContent = null) => {
        const element = document.createElementNS(svgNamespace, tagName);
        Object.entries(attributes).forEach(([name, value]) => {
          if (value !== null && value !== undefined) element.setAttribute(name, String(value));
        });
        if (textContent !== null) element.textContent = textContent;
        return element;
      };

      const fragment = document.createDocumentFragment();
      (map.edges || []).forEach(edge => {
        const group = createSvgElement('g');
        group.appendChild(createSvgElement('path', {
          d: this.mapEdgePath(edge),
          class: this.mapEdgeClass(edge)
        }));
        if (edge.kind === 'door' && edge.visibility !== 'hidden') {
          const door = this.mapDoorPosition(edge);
          group.appendChild(createSvgElement('rect', {
            x: door.x - 5,
            y: door.y - 5,
            width: 10,
            height: 10,
            rx: 1,
            class: 'campaign-map-door'
          }));
        }
        fragment.appendChild(group);
      });

      (map.nodes || []).forEach(node => {
        const group = createSvgElement('g', { class: this.mapNodeClass(node) });
        if (['current', 'visited'].includes(node.visibility)) {
          group.setAttribute('role', 'button');
          group.setAttribute('tabindex', '0');
          group.setAttribute('aria-label', `Pokaż opis lokacji: ${node.name}`);
          group.addEventListener('click', () => this.selectMapNode(node.id));
          group.addEventListener('keydown', event => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              this.selectMapNode(node.id);
            }
          });
        }
        group.appendChild(createSvgElement('rect', {
          x: node.x - node.width / 2,
          y: node.y - node.height / 2,
          width: node.width,
          height: node.height,
          rx: 3,
          class: 'campaign-map-room'
        }));
        group.appendChild(createSvgElement('rect', {
          x: node.x - node.width / 2 + 5,
          y: node.y - node.height / 2 + 5,
          width: node.width - 10,
          height: node.height - 10,
          rx: 2,
          fill: 'url(#room-dots)',
          class: 'campaign-map-room-dots'
        }));
        group.appendChild(createSvgElement('text', {
          x: node.x,
          y: node.y - 9,
          'text-anchor': 'middle',
          class: 'campaign-map-glyph'
        }, this.mapNodeIcon(node.type)));
        group.appendChild(createSvgElement('text', {
          x: node.x,
          y: node.y + 13,
          'text-anchor': 'middle',
          class: 'campaign-map-label'
        }, this.mapNodeDisplayName(node)));
        if (node.visibility === 'current') {
          group.appendChild(createSvgElement('text', {
            x: node.x,
            y: node.y + node.height / 2 + 17,
            'text-anchor': 'middle',
            class: 'campaign-map-party'
          }, '● DRUŻYNA'));
        }
        if (node.visit_order) {
          group.appendChild(createSvgElement('circle', {
            cx: node.x - node.width / 2 + 12,
            cy: node.y - node.height / 2 + 12,
            r: 9,
            class: 'campaign-map-order-marker'
          }));
          group.appendChild(createSvgElement('text', {
            x: node.x - node.width / 2 + 12,
            y: node.y - node.height / 2 + 15,
            'text-anchor': 'middle',
            class: 'campaign-map-order-label'
          }, String(node.visit_order)));
        }
        fragment.appendChild(group);
      });

      drawing.replaceChildren(fragment);
    },

    mapNodeById(nodeId) {
      return this.campaignMap?.nodes?.find(node => node.id === nodeId) || null;
    },

    mapEdgePath(edge) {
      const source = this.mapNodeById(edge?.from);
      const target = this.mapNodeById(edge?.to);
      if (!source || !target) return '';
      if (Math.abs(target.x - source.x) >= Math.abs(target.y - source.y)) {
        const middleX = Math.round((source.x + target.x) / 2);
        return `M ${source.x} ${source.y} H ${middleX} V ${target.y} H ${target.x}`;
      }
      const middleY = Math.round((source.y + target.y) / 2);
      return `M ${source.x} ${source.y} V ${middleY} H ${target.x} V ${target.y}`;
    },

    mapDoorPosition(edge) {
      const source = this.mapNodeById(edge?.from);
      const target = this.mapNodeById(edge?.to);
      if (!source || !target) return { x: 0, y: 0 };
      if (Math.abs(target.x - source.x) >= Math.abs(target.y - source.y)) {
        return { x: Math.round((source.x + target.x) / 2), y: source.y };
      }
      return { x: source.x, y: Math.round((source.y + target.y) / 2) };
    },

    mapNodeIcon(type) {
      return {
        entrance: '⇥', finale: '☠', treasury: '$', shrine: '†', crypt: '☗',
        library: '≡', armory: '⚔', bridge: '═', prison: '#', well: '○',
        forge: '♨', tomb: '⌂', cave: '∩', study: '?', guardroom: '!',
        crossroads: '+', gallery: '◇', hall: '□', chamber: '◆', unknown: '·'
      }[type] || '·';
    },

    mapNodeDisplayName(node) {
      const name = String(node?.name || 'Nieodkryta lokacja');
      return name.length > 22 ? `${name.slice(0, 21)}…` : name;
    },

    mapNodeClass(node) {
      const selectedClass = node?.id === this.selectedMapNodeId
        ? ' campaign-map-node--selected'
        : '';
      return `campaign-map-node campaign-map-node--${node?.visibility || 'hidden'}${selectedClass}`;
    },

    mapEdgeClass(edge) {
      return `campaign-map-edge campaign-map-edge--${edge?.visibility || 'hidden'}`;
    },

    get latestResolvedTurn() {
      return this.storyTurnsDescending.find(turn => turn.status === 'completed') || null;
    },

    get primaryStoryTurns() {
      const turns = [this.latestResolvedTurn, this.currentStoryTurn].filter(Boolean);
      return turns.filter((turn, index) => turns.findIndex(item => item.id === turn.id) === index);
    },

    get storyTurnsInReadingOrder() {
      const primaryIds = new Set(this.primaryStoryTurns.map(turn => turn.id));
      return [
        ...this.primaryStoryTurns,
        ...this.storyTurnsDescending.filter(turn => !primaryIds.has(turn.id))
      ];
    },

    get visibleStoryTurns() {
      return this.showStoryArchive
        ? this.storyTurnsInReadingOrder
        : this.primaryStoryTurns;
    },

    get archivedStoryTurnCount() {
      return Math.max(0, this.storyTurnsDescending.length - this.primaryStoryTurns.length);
    },

    isFeaturedStoryTurn(turn) {
      return this.primaryStoryTurns.some(item => item.id === turn.id);
    },

    isStoryTurnExpanded(turn) {
      return this.isFeaturedStoryTurn(turn) || this.expandedStoryTurnIds.includes(turn.id);
    },

    toggleStoryTurn(turnId) {
      if (this.expandedStoryTurnIds.includes(turnId)) {
        this.expandedStoryTurnIds = this.expandedStoryTurnIds.filter(id => id !== turnId);
      } else {
        this.expandedStoryTurnIds = [...this.expandedStoryTurnIds, turnId];
      }
    },

    toggleStoryArchive() {
      this.showStoryArchive = !this.showStoryArchive;
      if (!this.showStoryArchive) this.expandedStoryTurnIds = [];
    },

    isCurrentTurnNearViewport() {
      const element = document.getElementById('current-turn-card');
      if (!element) return true;
      const rect = element.getBoundingClientRect();
      return rect.bottom >= 0 && rect.top <= window.innerHeight * 1.25;
    },

    scrollToCurrentTurn(smooth = true) {
      this.hasUnreadTurn = false;
      this.$nextTick(() => {
        const element = document.getElementById('current-turn-card');
        if (!element) return;
        const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        element.scrollIntoView({
          behavior: smooth && !reduceMotion ? 'smooth' : 'auto',
          block: 'start'
        });
      });
    },

    scrollToLatestResolution(smooth = true) {
      this.hasUnreadTurn = false;
      this.$nextTick(() => {
        const element = document.getElementById('latest-resolved-turn-card')
          || document.getElementById('current-turn-card');
        if (!element) return;
        const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        element.scrollIntoView({
          behavior: smooth && !reduceMotion ? 'smooth' : 'auto',
          block: 'start'
        });
      });
    },

    openNewestStoryContent() {
      if (this.hasUnreadTurn) {
        this.scrollToLatestResolution();
      } else {
        this.scrollToCurrentTurn();
      }
    },

    get readyCount() {
      if (!this.session) return 0;
      const curTurn = this.session.turns.find(t => t.turn_number === this.session.current_turn_number);
      if (!curTurn) return 0;
      return curTurn.actions.length;
    },

    get totalAlivePlayers() {
      if (!this.session) return 0;
      return this.session.characters.filter(c => c.is_alive).length;
    },

    get hasOpenProxyDecision() {
      return (this.session?.characters || []).some(
        character => character.proxy_action?.decision?.status === 'open'
      );
    },

    get proxyTargetCharacter() {
      return (this.session?.characters || []).find(
        character => character.id === this.proxyTargetCharacterId
      ) || null;
    },

    get proxyDecision() {
      return this.proxyTargetCharacter?.proxy_action?.decision || null;
    },

    get proxyOptions() {
      return this.proxyDecision?.options || this.proxyTargetCharacter?.proxy_action?.options || [];
    },

    get myProxyVoteOptionId() {
      return this.proxyDecision?.votes?.find(
        vote => vote.voter_character_id === this.selectedCharacterId
      )?.option_id || null;
    },

    canOpenProxyAction(character) {
      const availableAt = Date.parse(character?.proxy_action?.available_at || '');
      const isAvailable = character?.proxy_action?.available || (
        Number.isFinite(availableAt) && this.proxyNow >= availableAt
      );
      if (
        !isAvailable || this.session?.is_turn_resolving ||
        character.id === this.selectedCharacterId || character.has_submitted_action
      ) return false;
      return Boolean(
        this.currentCharacter?.is_alive &&
        this.currentCharacter?.has_submitted_action &&
        this.currentCharacter?.action_submission_source === 'player'
      );
    },

    openProxyActionVote(character) {
      if (!this.canOpenProxyAction(character)) return;
      this.proxyTargetCharacterId = character.id;
      this.proxyVoteError = '';
      this.showProxyActionModal = true;
    },

    closeProxyActionVote() {
      if (this.isSubmittingProxyVote) return;
      this.showProxyActionModal = false;
      this.proxyTargetCharacterId = null;
      this.proxyVoteError = '';
    },

    proxyVoteTimeLabel() {
      const voteHours = this.session?.proxy_action_config?.vote_hours || 2;
      if (!this.proxyDecision?.closes_at) return `Pierwszy głos otworzy głosowanie na ${voteHours} godz.`;
      const remainingMs = Date.parse(this.proxyDecision.closes_at) - this.proxyNow;
      if (remainingMs <= 0) return 'Głosowanie jest domykane…';
      const totalMinutes = Math.ceil(remainingMs / 60000);
      const hours = Math.floor(totalMinutes / 60);
      const minutes = totalMinutes % 60;
      return `Pozostało: ${hours ? `${hours} godz. ` : ''}${minutes} min.`;
    },

    async submitProxyVote(optionId) {
      if (!this.proxyTargetCharacter || !this.selectedCharacterId || this.isSubmittingProxyVote) return;
      this.proxyVoteError = '';
      this.isSubmittingProxyVote = true;
      try {
        const res = await fetch(`/api/proxy-actions/${this.proxyTargetCharacter.id}/votes`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            voter_character_id: this.selectedCharacterId,
            option_id: optionId
          })
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || 'Nie udało się zapisać głosu.');
        this.addToast(data.finalized ? 'Akcja zastępcza została wybrana.' : 'Twój głos został zapisany.', 'success');
        await this.fetchSession();
        if (data.finalized) {
          this.showProxyActionModal = false;
          this.proxyTargetCharacterId = null;
        }
      } catch (err) {
        this.proxyVoteError = err.message;
      } finally {
        this.isSubmittingProxyVote = false;
      }
    },

    get isCurrentCharacterReady() {
      if (!this.currentCharacter) return false;
      return Boolean(this.currentCharacter.is_ready);
    },

    get lobbyAliveCharacters() {
      if (!this.session?.characters) return [];
      return this.session.characters.filter(c => c.is_alive);
    },

    get lobbyReadyCount() {
      return this.lobbyAliveCharacters.filter(c => c.is_ready).length;
    },

    get allLobbyCharactersReady() {
      const chars = this.lobbyAliveCharacters;
      return chars.length > 0 && chars.every(c => c.is_ready);
    },

    get unreadyCharacterNames() {
      return this.lobbyAliveCharacters.filter(c => !c.is_ready).map(c => c.name);
    },

    get statPointsRemaining() {
      const sum = Number(this.newChar.strength) + Number(this.newChar.agility) + Number(this.newChar.intellect) + Number(this.newChar.charisma);
      return 4 - sum;
    },

    // --- WebSockets ---
    closeWebSocket() {
      clearTimeout(this.wsReconnectTimer);
      this.wsReconnectTimer = null;
      const socket = this.ws;
      this.ws = null;
      this.wsConnected = false;
      if (socket) {
        socket.onopen = null;
        socket.onmessage = null;
        socket.onclose = null;
        socket.close();
      }
    },

    destroy() {
      this.closeWebSocket();
      this.clearNotifications();
      document.removeEventListener('visibilitychange', this.notificationFocusHandler);
      window.removeEventListener('focus', this.notificationFocusHandler);
      document.removeEventListener('pointerup', this.notificationUnlockHandler);
      document.removeEventListener('keydown', this.notificationUnlockHandler);
      clearInterval(this.proxyClockTimer);
      this.proxyClockTimer = null;
      if (this.notificationAudio) this.notificationAudio.close().catch(() => {});
    },

    initWebSocket() {
      if (!this.session || !this.isAuthenticated) return;
      const charId = this.selectedCharacterId || 0;

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/ws/${this.session.session_id}/${charId}`;

      if (this.ws && this.ws.url === wsUrl &&
          [WebSocket.CONNECTING, WebSocket.OPEN].includes(this.ws.readyState)) return;
      this.closeWebSocket();
      if (this.chatSessionId !== this.session.session_id) {
        this.chatMessages = [];
        this.chatSessionId = this.session.session_id;
      }
      const socket = new WebSocket(wsUrl);
      this.ws = socket;

      socket.onopen = () => {
        if (this.ws !== socket) return;
        this.wsConnected = true;
        logger('Połączono z WebSockets gry');
      };

      socket.onmessage = (event) => {
        if (this.ws !== socket) return;
        try {
          const data = JSON.parse(event.data);
          this.handleWsMessage(data);
        } catch (e) {
          console.error('Błąd parsowania wiadomości WS:', e);
        }
      };

      socket.onclose = () => {
        if (this.ws !== socket) return;
        this.ws = null;
        this.wsConnected = false;
        clearTimeout(this.wsReconnectTimer);
        this.wsReconnectTimer = setTimeout(() => {
          this.wsReconnectTimer = null;
          if (this.isAuthenticated) {
            this.initWebSocket();
          }
        }, 3000);
      };
    },

    async handleWsMessage(msg) {
      switch (msg.type) {
        case 'CHAT_HISTORY':
          this.appendChatMessages(msg.messages || [], true);
          break;

        case 'CHAT_MESSAGE':
          this.appendChatMessages([msg]);
          if (msg.character_id !== this.selectedCharacterId && this.isMentionedInChat(msg)) {
            this.notifyGameEvent();
          }
          break;

        case 'NAMING_REQUESTED':
          this.pendingNaming = {
            category: msg.category,
            description: msg.description,
            prompt: msg.prompt,
            character_id: msg.character_id,
            character_name: msg.character_name
          };
          if (msg.character_id === this.selectedCharacterId) {
            this.showNamingModal = true;
            this.addToast('👑 LOS WYBRAŁ CIEBIE! Nadaj nazwę nowemu odkryciu!', 'warning');
          } else {
            this.addToast(`🔥 Odkryto ${msg.category}! Gracz ${msg.character_name} nadaje nazwę...`, 'info');
          }
          await this.fetchSession();
          break;

        case 'LORE_ENTITY_NAMED':
          this.showNamingModal = false;
          this.pendingNaming = null;
          this.addToast(`📜 Do Kroniki dodano: ${msg.custom_name} (${msg.category}) nazwany przez ${msg.named_by}!`, 'success');
          await this.fetchSession();
          break;

        case 'LOBBY_STARTED':
          this.addToast(`🏰 Mistrz Gry otworzył Zbiórkę Drużyny dla nowego scenariusza: ${msg.title}!`, 'info');
          await this.fetchSession();
          break;

        case 'CHARACTER_READY_TOGGLED':
          this.addToast(
            msg.is_ready 
              ? `✓ Bohater ${msg.character_name} jest gotowy do drogi!`
              : `⏳ Bohater ${msg.character_name} jeszcze się naradza...`,
            msg.is_ready ? 'success' : 'info'
          );
          await this.fetchSession();
          break;

        case 'PROLOGUE_STARTED':
          this.addToast('⚔️ Mistrz Gry Gemini wygłosił Prolog dla Zebranej Drużyny!', 'success');
          this.showStoryArchive = false;
          this.expandedStoryTurnIds = [];
          await this.fetchSession();
          this.scrollToCurrentTurn(false);
          break;

        case 'PLAYER_ACTION_SUBMITTED':
          this.addToast(`Gracz ${msg.character_name} złożył akcję (${msg.ready_count}/${msg.total_players})`, 'info');
          await this.fetchSession();
          break;

        case 'PROXY_ACTION_VOTE_UPDATED':
          await this.fetchSession();
          break;

        case 'PROXY_ACTION_FINALIZED':
          this.addToast(
            `🗳️ Drużyna wybrała dla ${msg.target_character_name}: ${msg.selected_label}.`,
            'success'
          );
          if (msg.target_character_id === this.proxyTargetCharacterId) {
            this.showProxyActionModal = false;
            this.proxyTargetCharacterId = null;
          }
          await this.fetchSession();
          break;

        case 'PROXY_ACTION_OVERRIDDEN':
          this.addToast(`${msg.character_name} zastąpił akcję drużyny własną deklaracją.`, 'info');
          await this.fetchSession();
          break;

        case 'ALL_PLAYERS_READY':
          this.addToast('⚔️ Wszyscy gracze zatwierdzili akcje! Można wygenerować kolejną turę.', 'success');
          await this.fetchSession();
          break;

        case 'TURN_RESOLVING':
          this.turnError = '';
          this.isResolvingTurn = true;
          this.isEditingSubmittedAction = false;
          this.addToast(msg.message, 'warning');
          if (this.session) this.session.is_turn_resolving = true;
          break;

        case 'TURN_COMPLETED': {
          const followCurrentTurn = this.isCurrentTurnNearViewport();
          this.notifyGameEvent();
          this.turnError = '';
          this.isResolvingTurn = false;
          this.isEditingSubmittedAction = false;
          this.addToast(`Tura #${msg.completed_turn_number} zakończona! Mistrz Gry wydał werdykt.`, 'success');
          this.actionText = '';
          this.actionIntent = null;
          this.actionTargetRef = null;
          this.magicAbilityId = null;
          await this.fetchSession();
          if (followCurrentTurn) {
            this.scrollToLatestResolution();
          } else {
            this.hasUnreadTurn = true;
          }
          break;
        }

        case 'LEVEL_UP_AVAILABLE': {
          const character = this.session?.characters?.find(c => c.id === msg.character_id);
          if (character) {
            character.level = msg.level;
            character.unspent_stat_points = msg.unspent_stat_points;
          }
          if (msg.character_id === this.selectedCharacterId) {
            if (msg.unspent_stat_points > 0) {
              this.showLevelUpModal = true;
              this.addToast(
                `⭐ Awans na poziom ${msg.level}! Wybierz atrybut do zwiększenia.`,
                'success'
              );
            } else {
              this.addToast(`⭐ Awans na poziom ${msg.level}!`, 'success');
            }
          }
          break;
        }

        case 'STAT_POINT_SPENT': {
          const character = this.session?.characters?.find(c => c.id === msg.character_id);
          if (character) {
            character[msg.stat] = msg.stat_value;
            character.unspent_stat_points = msg.unspent_stat_points;
          }
          if (msg.character_id === this.selectedCharacterId && msg.unspent_stat_points === 0) {
            this.showLevelUpModal = false;
          }
          break;
        }

        case 'IMAGE_GENERATING':
          this.addToast(`Rozpoczęto generowanie ilustracji dla Tury #${msg.turn_id}...`, 'info');
          if (this.session) {
            const t = this.session.turns.find(x => x.id === msg.turn_id);
            if (t) t.is_generating_image = true;
          }
          break;

        case 'IMAGE_READY':
          this.addToast(`Ilustracja do Tury #${msg.turn_id} jest gotowa!`, 'success');
          await this.fetchSession();
          break;

        case 'CHARACTER_CREATED':
          this.addToast(`Do drużyny dołączył ${msg.character.name} (${msg.character.character_class})!`, 'info');
          await this.fetchSession();
          break;

        case 'CHARACTER_DELETED':
          this.addToast(`Postać "${msg.character_name}" została usunięta z drużyny`, 'info');
          if (this.selectedCharacterId === msg.character_id) {
            this.selectedCharacterId = null;
            localStorage.removeItem('rpg_selected_char');
          }
          await this.fetchSession();
          break;

        case 'CAMPAIGN_RESET':
          this.addToast(msg.message, 'info');
          this.showStoryArchive = false;
          this.expandedStoryTurnIds = [];
          this.hasUnreadTurn = false;
          await this.fetchSession();
          break;

        case 'TURN_ERROR':
          this.turnError = msg.message;
          this.addToast(`Błąd tury: ${msg.message}`, 'error');
          if (this.session) this.session.is_turn_resolving = false;
          break;
      }
    },

    // --- Czat Drużyny ---
    get chatMentionOptions() {
      if (!this.chatMention) return [];
      const query = this.chatMention.query.normalize('NFC').toLocaleLowerCase('pl-PL');
      return [{ id: 'all', name: 'all', label: 'Wszyscy gracze' },
        ...(this.session?.characters || []).map(character => ({
          id: character.id, name: character.name, label: character.name
        }))
      ].filter(option => option.name.normalize('NFC').toLocaleLowerCase('pl-PL').startsWith(query));
    },

    updateChatMention(input) {
      const end = input.selectionStart;
      const before = input.value.slice(0, end);
      const match = before.match(/(^|[^\p{L}\p{N}\p{M}_@])@([^@\n]*)$/u);
      this.chatMention = match && input.selectionStart === input.selectionEnd
        ? { start: match.index + match[1].length, end, query: match[2] }
        : null;
      this.chatMentionIndex = 0;
    },

    selectChatMention(option) {
      if (!this.chatMention || !option) return;
      const { start, end } = this.chatMention;
      const insertion = `@${option.name} `;
      this.chatInput = this.chatInput.slice(0, start) + insertion + this.chatInput.slice(end);
      this.chatMention = null;
      this.$nextTick(() => {
        const input = this.$refs.chatInput;
        input.focus();
        input.setSelectionRange(start + insertion.length, start + insertion.length);
      });
    },

    handleChatMentionKey(event) {
      if (event.isComposing) return;
      const options = this.chatMentionOptions;
      if (!options.length) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        this.chatMention = null;
      } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        const step = event.key === 'ArrowDown' ? 1 : -1;
        this.chatMentionIndex = (this.chatMentionIndex + step + options.length) % options.length;
        this.$nextTick(() => {
          document.getElementById(`chat-mention-${this.chatMentionIndex}`)
            ?.scrollIntoView({ block: 'nearest' });
        });
      } else if (event.key === 'Enter' || event.key === 'Tab') {
        event.preventDefault();
        this.selectChatMention(options[this.chatMentionIndex]);
      }
    },

    isMentionedInChat(message) {
      const currentName = this.currentCharacter?.name?.normalize('NFC').toLocaleLowerCase('pl-PL');
      if (!currentName || !message.text) return false;
      if (/(^|[^\p{L}\p{N}\p{M}_@])@all(?=$|[^\p{L}\p{N}\p{M}_])/iu.test(message.text)) return true;
      // Match complete character names, preferring longer names with spaces.
      const names = (this.session?.characters || [])
        .map(character => character.name.normalize('NFC'))
        .sort((a, b) => b.length - a.length)
        .map(name => name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
      if (!names.length) return false;
      const mentions = new RegExp(
        `(^|[^\\p{L}\\p{N}\\p{M}_@])@(${names.join('|')})(?=$|[^\\p{L}\\p{N}\\p{M}_])`, 'giu'
      );
      return Array.from(message.text.normalize('NFC').matchAll(mentions))
        .some(match => match[2].toLocaleLowerCase('pl-PL') === currentName);
    },

    formatChatTime(value) {
      // Older servers only supplied HH:mm, without a date or timezone.
      if (!value || /^\d{2}:\d{2}$/.test(value)) return value || '';
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return '';
      return date.toLocaleTimeString('pl-PL', {
        timeZone: 'Europe/Warsaw', hour: '2-digit', minute: '2-digit'
      });
    },

    appendChatMessages(messages, isHistory = false) {
      const el = document.getElementById('chat-messages-container');
      const followLatest = !this.chatMessages.length ||
        (el && el.scrollHeight - el.clientHeight - el.scrollTop <= 32);
      // Merge reconnect history without replacing rows the player is reading.
      const known = new Set(this.chatMessages.map(msg => JSON.stringify(msg)));
      const incoming = isHistory
        ? messages.filter(msg => !known.has(JSON.stringify(msg)))
        : messages;
      if (!incoming.length) return;
      this.chatMessages.push(...incoming);
      if (this.chatMessages.length > 50) {
        this.chatMessages.splice(0, this.chatMessages.length - 50);
      }
      if (followLatest && el) {
        const previousTop = el.scrollTop;
        this.$nextTick(() => {
          // Do not override a scroll made while Alpine was rendering.
          if (el.scrollTop === previousTop) el.scrollTop = el.scrollHeight;
        });
      }
    },

    sendChatMessage() {
      const text = this.chatInput.trim();
      if (!text || !this.currentCharacter) return;

      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
        this.addToast('Trwa łączenie z serwerem gry... Spróbuj za chwilę.', 'warning');
        this.initWebSocket();
        return;
      }

      const payload = {
        type: 'CHAT_MESSAGE',
        author: this.currentCharacter.name,
        character_class: this.currentCharacter.character_class,
        text: text
      };

      this.ws.send(JSON.stringify(payload));
      this.chatInput = '';
      this.chatMention = null;
    },

    sendQuickChat(quickText) {
      this.chatInput = quickText;
      this.sendChatMessage();
    },

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
            custom_name: name
          })
        });
        if (!res.ok) throw new Error('Błąd zapisu nazwy.');
        this.namingInput = '';
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
        if (!res.ok) throw new Error('Błąd wywołania eventu.');
        const data = await res.json();
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
        const res = await fetch('/api/session/setup-scenario', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            room_code: this.roomCode,
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
        this.addToast('🏰 Otwarto Zbiórkę Drużyny dla nowego scenariusza!', 'success');
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
      return {
        strength: 'Siła',
        agility: 'Zręczność',
        intellect: 'Rozum',
        charisma: 'Charyzma'
      }[stat] || stat;
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
    async submitAction() {
      if (!this.actionText.trim()) {
        this.actionError = 'Wpisz treść akcji dla swojej postaci.';
        return;
      }
      if (!this.selectedCharacterId) {
        this.actionError = 'Musisz najpierw wybrać swoją postać.';
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
            intent: this.actionIntent,
            target_ref: this.actionTargetRef
          })
        });
        if (!res.ok) {
          const errData = await res.json();
          throw new Error(errData.detail || 'Nie udało się złożyć akcji.');
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
          this.magicAbilityId = myAction.magic_ability_id || null;
          this.actionIntent = myAction.intent || null;
          this.actionTargetRef = myAction.target_ref || null;
        }
      }
      this.isEditingSubmittedAction = true;
      this.$nextTick(() => {
        const textarea = document.querySelector('textarea[x-model="actionText"]');
        if (textarea) {
          textarea.scrollIntoView({ behavior: 'smooth', block: 'center' });
          textarea.focus();
        }
      });
    },

    setQuickAction(text, intent = null, targetRef = null) {
      this.actionText = text;
      this.magicAbilityId = null;
      this.actionIntent = intent;
      this.actionTargetRef = targetRef;
      this.$nextTick(() => {
        const textarea = document.querySelector('textarea[x-model="actionText"]');
        if (textarea) {
          textarea.scrollIntoView({ behavior: 'smooth', block: 'center' });
          textarea.focus();
        }
      });
      this.addToast('⚡ Wybrano ścieżkę działania – możesz ją dostosować przed zatwierdzeniem!', 'info');
    },

    selectMagicAbility(ability) {
      if (!ability?.unlocked) return;
      this.actionText = ability.action_text;
      this.magicAbilityId = ability.id;
      this.actionIntent = ability.intent || null;
      this.actionTargetRef = ability.target_ref || null;
      this.actionError = '';
      this.$nextTick(() => {
        const textarea = document.querySelector('textarea[x-model="actionText"]');
        if (textarea) {
          textarea.scrollIntoView({ behavior: 'smooth', block: 'center' });
          textarea.focus();
        }
      });
      this.addToast(`Wybrano: ${ability.name}. Możesz dopisać cel lub sposób wykonania.`, 'info');
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
      return { strength: 'SIŁ', agility: 'ZRĘ', intellect: 'ROZ', charisma: 'CHA' }[stat] || stat;
    },

    intentLabel(intent) {
      return {
        attack: 'atak', defend: 'obrona', interact: 'interakcja', support: 'wsparcie', other: 'inna akcja'
      }[intent] || intent;
    },

    targetLabel(targetRef) {
      if (!targetRef) return '';
      if (targetRef === 'boss') return this.session?.active_boss?.name || 'boss';
      const feature = (this.session?.active_boss?.features || []).find(item => item.id === targetRef);
      return feature?.name || targetRef;
    },

    // --- Ekwipunek ---
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
          throw new Error(err.detail || 'Błąd generowania obrazu');
        }
        const data = await res.json();
        if (turn) {
          turn.image_url = data.image_url;
          turn.is_generating_image = false;
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
        const res = await fetch('/api/generate-intro', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            scenario_type: this.scenarioChoice,
            tone: this.scenarioTone
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
  }));
});

function logger(...args) {
  console.log('[TTRPG]', ...args);
}
