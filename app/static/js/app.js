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
    isSubmittingAction: false,
    actionError: '',
    turnError: '',
    isRetryingTurn: false,
    isResolvingTurn: false,
    isEditingSubmittedAction: false,

    // Modals
    showCharModal: false,
    showIntroModal: false,
    showLightbox: false,
    showNamingModal: false,
    showLoreBookModal: false,
    lightboxImageUrl: '',

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

    // Party Chat
    chatMessages: [],
    chatInput: '',

    // Lore Naming System
    pendingNaming: null, // {category, description, prompt, character_id, character_name}
    namingInput: '',
    isSubmittingNaming: false,

    // WebSockets
    ws: null,
    wsConnected: false,
    toasts: [],

    init() {
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

    // --- Powiadomienia Toast ---
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

    logout() {
      this.isAuthenticated = false;
      this.selectedCharacterId = null;
      localStorage.removeItem('rpg_room_pw');
      localStorage.removeItem('rpg_selected_char');
      if (this.ws) this.ws.close();
    },

    // --- Pobieranie Stanu Sesji ---
    async fetchSession() {
      this.isLoadingSession = true;
      try {
        const res = await fetch(`/api/session?room_code=${this.roomCode}`);
        if (!res.ok) throw new Error('Błąd ładowania sesji.');
        const data = await res.json();
        this.session = data;

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
      localStorage.setItem('rpg_selected_char', charId);
      this.initWebSocket();
      this.addToast(`Wybrano postać: ${this.currentCharacter?.name}`, 'success');
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

    get hasSubmittedCurrentTurn() {
      if (this.isEditingSubmittedAction) return false;
      if (!this.session || !this.selectedCharacterId) return false;
      const curTurn = this.session.turns.find(t => t.turn_number === this.session.current_turn_number);
      if (!curTurn) return false;
      return curTurn.actions.some(a => a.character_id === this.selectedCharacterId);
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
    initWebSocket() {
      if (!this.session) return;
      const charId = this.selectedCharacterId || 0;
      if (this.ws) {
        try { this.ws.close(); } catch (e) {}
      }

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/ws/${this.session.session_id}/${charId}`;

      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        this.wsConnected = true;
        logger('Połączono z WebSockets gry');
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.handleWsMessage(data);
        } catch (e) {
          console.error('Błąd parsowania wiadomości WS:', e);
        }
      };

      this.ws.onclose = () => {
        this.wsConnected = false;
        setTimeout(() => {
          if (this.isAuthenticated && this.selectedCharacterId) {
            this.initWebSocket();
          }
        }, 3000);
      };
    },

    async handleWsMessage(msg) {
      console.log('WS Event:', msg);
      switch (msg.type) {
        case 'CHAT_HISTORY':
          this.chatMessages = msg.messages || [];
          this.$nextTick(() => {
            const el = document.getElementById('chat-messages-container');
            if (el) el.scrollTop = el.scrollHeight;
          });
          break;

        case 'CHAT_MESSAGE':
          this.chatMessages.push(msg);
          this.$nextTick(() => {
            const el = document.getElementById('chat-messages-container');
            if (el) el.scrollTop = el.scrollHeight;
          });
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
          await this.fetchSession();
          this.$nextTick(() => {
            const el = document.getElementById('story-log-container');
            if (el) el.scrollTop = 0;
          });
          break;

        case 'PLAYER_ACTION_SUBMITTED':
          this.addToast(`Gracz ${msg.character_name} złożył akcję (${msg.ready_count}/${msg.total_players})`, 'info');
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

        case 'TURN_COMPLETED':
          this.turnError = '';
          this.isResolvingTurn = false;
          this.isEditingSubmittedAction = false;
          this.addToast(`Tura #${msg.completed_turn_number} zakończona! Mistrz Gry wydał werdykt.`, 'success');
          this.actionText = '';
          await this.fetchSession();
          this.$nextTick(() => {
            const el = document.getElementById('story-log-container');
            if (el) el.scrollTop = el.scrollHeight;
          });
          break;

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
        if (!res.ok) throw new Error('Błąd inicjowania poczekalni.');
        this.showIntroModal = false;
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
            action_text: this.actionText.trim()
          })
        });
        if (!res.ok) {
          const errData = await res.json();
          throw new Error(errData.detail || 'Nie udało się złożyć akcji.');
        }
        const data = await res.json();
        this.isEditingSubmittedAction = false;
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

    setQuickAction(text) {
      this.actionText = text;
      this.$nextTick(() => {
        const textarea = document.querySelector('textarea[x-model="actionText"]');
        if (textarea) {
          textarea.scrollIntoView({ behavior: 'smooth', block: 'center' });
          textarea.focus();
        }
      });
      this.addToast('⚡ Wybrano ścieżkę działania – możesz ją dostosować przed zatwierdzeniem!', 'info');
    },

    // --- Ekwipunek ---
    async toggleEquip(itemId) {
      try {
        const res = await fetch(`/api/characters/${this.selectedCharacterId}/inventory/${itemId}/toggle-equip`, {
          method: 'POST'
        });
        if (!res.ok) throw new Error('Nie udało się zmienić ekwipunku.');
        await this.fetchSession();
      } catch (err) {
        this.addToast(err.message, 'error');
      }
    },

    async useItem(itemId) {
      try {
        const res = await fetch(`/api/characters/${this.selectedCharacterId}/inventory/${itemId}/use`, {
          method: 'POST'
        });
        if (!res.ok) throw new Error('Nie udało się użyć przedmiotu.');
        const data = await res.json();
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
            password: this.roomPassword,
            title: this.generatedIntro.title,
            setting_theme: this.generatedIntro.setting_theme,
            campaign_intro: this.generatedIntro.campaign_intro + '\n\n' + this.generatedIntro.first_challenge
          })
        });
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
