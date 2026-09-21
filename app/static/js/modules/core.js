(() => {
  'use strict';
  const features = window.TTRPG_FEATURES = window.TTRPG_FEATURES || {};
  features.createCoreFeature = () => ({
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
    actionTestedStat: null,
    actionTargetRef: null,
    magicAbilityId: null,
    namedAttackId: null,
    actionInterpretation: null,
    showActionInterpretationControls: false,
    isInterpretingAction: false,
    actionInterpretationRequestId: 0,
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
    mapZoom: 1,
    mapPanX: 0,
    mapPanY: 0,
    mapDrag: null,

    // Level Up
    isSpendingStatPoint: false,
    statPointError: '',
    maxBaseStat: 12,

    // Character Form
    newChar: {
      player_name: '',
      name: '',
      character_class: '',
      class_id: '',
      strength: 2,
      agility: 1,
      intellect: 1,
      charisma: 0,
      perception: 0
    },
    charError: '',
    isCreatingChar: false,

    // Campaign Intro & Prologue
    scenarioChoice: '',
    scenarioTone: '',
    worldCatalog: [],
    selectedWorldKey: '',
    isLoadingWorldCatalog: false,
    worldCatalogError: '',
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
    gmEpilogue: '',
    gmEpilogueError: '',
    isFinishingCampaign: false,
    gmStatCharacterId: null,
    gmStatForm: {
      strength: 0,
      agility: 0,
      intellect: 0,
      charisma: 0,
      perception: 0
    },
    gmOriginalStats: null,
    gmStatError: '',
    isSavingGmStats: false,
    participationError: '',
    isSavingParticipation: false,

    // Party Chat
    chatMessages: [],
    chatInput: '',
    chatSessionId: null,
    chatMention: null,
    chatMentionIndex: 0,

    // Lore Naming System
    pendingNaming: null, // {category, description, prompt, character_id, character_name}
    namingInput: '',
    namingDisposition: 'reserved',
    namingCatchphrase: '',
    namingGoal: '',
    isSubmittingNaming: false,

    // WebSockets
    ws: null,
    wsConnected: false,
    wsReconnectTimer: null,
    toasts: [],
    toastSequence: 0,
    notificationCount: 0,
    baseTitle: document.title,
    notificationSoundEnabled: localStorage.getItem('rpg_notification_sound') !== 'off',
    notificationAudio: null,
    notificationLastSound: 0,
    notificationFocusHandler: null,
    notificationUnlockHandler: null,
    appPauseHandler: null,
    pageShowHandler: null,
    networkOnlineHandler: null,
    networkOfflineHandler: null,
    appInactiveSince: null,
    resumeSyncInProgress: false,
    lastResumeSyncAt: 0,
    welcomeBackVisible: false,
    welcomeBackName: '',
    welcomeBackTimer: null,
    resumeAbsenceThresholdMs: 120000,
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
    transferItemId: null,
    transferRecipientId: null,
    transferQuantity: 1,
    transferError: '',
    isTransferringItem: false,
    gmCoinAmount: 1,
    gmCoinError: '',
    isSavingGmCoins: false,
    gmWearableForm: { item_type: 'helmet', name: '', description: '', target_stat: 'none', stat_bonus: 0 },
    gmWearableError: '',
    isGrantingWearable: false,
    marketTab: 'buy',
    marketBusy: false,
    marketPortraitFailedUrl: '',
    marketError: '',
    marketFeedback: '',
    marketInteractionText: '',
    marketCraftItemIds: [],

    // PWA & Network
    deferredInstallPrompt: null,
    canInstallPWA: false,
    isPWAInstalled: false,
    isOffline: !navigator.onLine,

    init() {
      this.notificationFocusHandler = () => {
        if (document.hidden) {
          this.markAppInactive();
          return;
        }
        this.clearNotifications();
        this.handleAppResume();
      };
      this.appPauseHandler = () => this.markAppInactive();
      this.pageShowHandler = () => {
        if (!document.hidden) this.handleAppResume();
      };
      this.notificationUnlockHandler = () => this.unlockNotificationAudio();
      document.addEventListener('visibilitychange', this.notificationFocusHandler);
      window.addEventListener('focus', this.notificationFocusHandler);
      window.addEventListener('blur', this.appPauseHandler);
      window.addEventListener('pagehide', this.appPauseHandler);
      window.addEventListener('pageshow', this.pageShowHandler);
      document.addEventListener('pointerup', this.notificationUnlockHandler);
      document.addEventListener('keydown', this.notificationUnlockHandler);
      this.initDialogAccessibility();
      // Rejestracja Service Workera
      this.registerServiceWorker();

      // Nasłuchiwanie zdarzeń sieciowych (Online/Offline)
      this.networkOnlineHandler = () => {
        this.isOffline = false;
        this.addToast('Połączenie z siecią zostało przywrócone!', 'success');
        if (this.isAuthenticated) this.synchronizeClientState();
      };
      this.networkOfflineHandler = () => {
        this.isOffline = true;
        this.addToast('Utracono połączenie z siecią. Jesteś w trybie offline.', 'warning');
      };
      window.addEventListener('online', this.networkOnlineHandler);
      window.addEventListener('offline', this.networkOfflineHandler);

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

  });
})();
