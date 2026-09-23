(() => {
  'use strict';
  const features = window.TTRPG_FEATURES = window.TTRPG_FEATURES || {};
  features.pwaNotifications = {
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

    initDialogAccessibility() {
      this.$nextTick(() => {
        const focusOrigins = new WeakMap();
        document.querySelectorAll('[role="dialog"][aria-modal="true"]').forEach(dialog => {
          let wasVisible = false;
          const syncVisibility = () => {
            const isVisible = getComputedStyle(dialog).display !== 'none';
            if (isVisible && !wasVisible) {
              focusOrigins.set(dialog, document.activeElement);
              requestAnimationFrame(() => {
                const focusable = dialog.querySelector(
                  '[autofocus], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
                );
                focusable?.focus({ preventScroll: true });
              });
            } else if (!isVisible && wasVisible) {
              const origin = focusOrigins.get(dialog);
              if (origin?.isConnected) origin.focus({ preventScroll: true });
            }
            wasVisible = isVisible;
          };
          new MutationObserver(syncVisibility).observe(dialog, { attributes: true, attributeFilter: ['style'] });
          dialog.addEventListener('keydown', event => {
            if (event.key !== 'Tab') return;
            const focusable = [...dialog.querySelectorAll(
              'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
            )].filter(element => element.offsetParent !== null);
            if (!focusable.length) return;
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (event.shiftKey && document.activeElement === first) {
              event.preventDefault();
              last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
              event.preventDefault();
              first.focus();
            }
          });
          syncVisibility();
        });
      });
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
              room_code: this.roomCode,
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
      const id = `${Date.now()}-${++this.toastSequence}`;
      this.toasts.push({ id, message, type });
      setTimeout(() => {
        this.toasts = this.toasts.filter(t => t.id !== id);
      }, 5000);
    },

    markAppInactive() {
      if (!this.appInactiveSince) this.appInactiveSince = Date.now();
    },

    async handleAppResume() {
      const inactiveSince = this.appInactiveSince;
      this.appInactiveSince = null;
      if (!this.isAuthenticated || document.hidden) return;

      const wasAwayLongEnough = Boolean(
        inactiveSince && Date.now() - inactiveSince >= this.resumeAbsenceThresholdMs
      );
      const synchronized = await this.synchronizeClientState();
      if (synchronized && wasAwayLongEnough && this.currentCharacter?.name) {
        this.showWelcomeBack(this.currentCharacter.name);
      }
    },

    async synchronizeClientState() {
      const now = Date.now();
      if (!this.isAuthenticated || this.resumeSyncInProgress || now - this.lastResumeSyncAt < 1000) {
        return false;
      }

      this.resumeSyncInProgress = true;
      this.lastResumeSyncAt = now;
      try {
        // Systemy mobilne potrafią zostawić zamrożony WebSocket w stanie OPEN.
        // Nowe połączenie jest zestawiane przed pobraniem snapshotu, aby nie zgubić
        // zdarzeń emitowanych w trakcie synchronizacji.
        this.closeWebSocket();
        this.initWebSocket();
        const synchronized = await this.fetchSession();
        this.initWebSocket();
        return synchronized;
      } finally {
        this.resumeSyncInProgress = false;
      }
    },

    showWelcomeBack(characterName) {
      clearTimeout(this.welcomeBackTimer);
      this.welcomeBackVisible = false;
      this.welcomeBackName = characterName;
      this.$nextTick(() => {
        this.welcomeBackVisible = true;
        this.welcomeBackTimer = setTimeout(() => {
          this.welcomeBackVisible = false;
          this.welcomeBackTimer = null;
        }, 2800);
      });
    },

  };
})();
