(() => {
  'use strict';
  const features = window.TTRPG_FEATURES = window.TTRPG_FEATURES || {};
  features.realtimeChat = {
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
      window.removeEventListener('blur', this.appPauseHandler);
      window.removeEventListener('pagehide', this.appPauseHandler);
      window.removeEventListener('pageshow', this.pageShowHandler);
      window.removeEventListener('online', this.networkOnlineHandler);
      window.removeEventListener('offline', this.networkOfflineHandler);
      document.removeEventListener('pointerup', this.notificationUnlockHandler);
      document.removeEventListener('keydown', this.notificationUnlockHandler);
      clearInterval(this.proxyClockTimer);
      this.proxyClockTimer = null;
      clearTimeout(this.welcomeBackTimer);
      this.welcomeBackTimer = null;
      if (this.notificationAudio) this.notificationAudio.close().catch(() => {});
    },

    initWebSocket(syncOnOpen = false) {
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
        if (syncOnOpen) this.fetchSession();
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
            this.initWebSocket(true);
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

        case 'CAMPAIGN_COMPLETED':
          this.addToast('Kampania zakończona. Epilog jest dostępny przy kronice.', 'success');
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
          this.actionTestedStat = null;
          this.actionTargetRef = null;
          this.magicAbilityId = null;
          this.namedAttackId = null;
          this.actionInterpretation = null;
          this.showActionInterpretationControls = false;
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

        case 'CHARACTER_STATS_UPDATED': {
          const character = this.session?.characters?.find(c => c.id === msg.character_id);
          if (character) Object.assign(character, msg.stats || {});
          if (!this.isSavingGmStats && msg.character_id === this.selectedCharacterId) {
            this.addToast('MG skorygował bazowe atrybuty Twojej postaci.', 'info');
          }
          if (!this.isSavingGmStats && Number(this.gmStatCharacterId) === msg.character_id) {
            this.loadGmCharacterStats();
          }
          break;
        }

        case 'CHARACTER_PARTICIPATION_UPDATED':
          if (msg.character_id === this.selectedCharacterId && !this.isSavingParticipation) {
            this.addToast(
              msg.participation_status === 'on_break'
                ? `Twoja postać jest na przerwie od tury ${msg.break_started_turn}. Jej poziom i stan zostały zachowane.`
                : 'MG przywrócił Twoją postać do gry.',
              'info'
            );
          }
          await this.fetchSession();
          break;

        case 'CHARACTER_COINS_UPDATED':
          if (this.selectedCharacterId === msg.character_id && !this.isSavingGmCoins) {
            this.addToast(`MG zmienił saldo: ${msg.coins} ${this.currencyLabel}.`, 'info');
          }
          await this.fetchSession();
          break;

        case 'CHARACTER_HEALTH_UPDATED':
          if (this.selectedCharacterId === msg.character_id && !this.isSavingGmHealth) {
            this.addToast(`MG ustawił Twoje PW na ${msg.current_hp}/${msg.max_hp}.`, 'info');
          }
          await this.fetchSession();
          if (!this.isSavingGmHealth && Number(this.gmStatCharacterId) === msg.character_id) {
            this.loadGmCharacterStats();
          }
          break;

        case 'CONSUMABLE_GRANTED':
          if (this.selectedCharacterId === msg.character_id && !this.isGrantingConsumable) {
            this.addToast(`MG podarował Ci ${msg.quantity} × ${msg.item_name}.`, 'success');
          }
          await this.fetchSession('grant');
          break;

        case 'WEARABLE_GRANTED':
          if (this.selectedCharacterId === msg.character_id && !this.isGrantingWearable) {
            this.addToast(`MG dodał do Twojego plecaka: ${msg.item_name}.`, 'success');
          }
          await this.fetchSession('grant');
          break;

        case 'INVENTORY_TRANSFERRED':
          if (this.selectedCharacterId === msg.recipient_character_id) {
            this.addToast(`${msg.sender_name} przekazał Ci ${msg.quantity} × ${msg.item_name}.`, 'success');
          }
          await this.fetchSession('transfer');
          break;

        case 'MARKET_UPDATED':
          await this.fetchSession('market');
          break;

        case 'IMAGE_GENERATING':
          this.addToast(`Rozpoczęto generowanie ilustracji dla Tury #${msg.turn_id}...`, 'info');
          if (this.session) {
            const t = this.session.turns.find(x => x.id === msg.turn_id);
            if (t) t.is_generating_image = true;
            this.session.image_generation = {
              ...(this.session.image_generation || {}),
              can_generate: false,
              next_available_at: msg.next_available_at
            };
          }
          break;

        case 'IMAGE_READY':
          this.addToast(`Ilustracja do Tury #${msg.turn_id} jest gotowa!`, 'success');
          await this.fetchSession();
          break;

        case 'IMAGE_GENERATION_FAILED':
          if (this.session) {
            const t = this.session.turns.find(x => x.id === msg.turn_id);
            if (t) t.is_generating_image = false;
            this.session.image_generation = {
              ...(this.session.image_generation || {}),
              can_generate: true,
              last_generated_at: null,
              next_available_at: null
            };
          }
          break;

        case 'CHARACTER_CREATED':
          this.addToast(`Do drużyny dołączył ${msg.character.name} (${msg.character.character_class})!`, 'info');
          await this.fetchSession();
          break;

        case 'CHARACTER_DELETED':
          this.addToast(`Postać "${msg.character_name}" została usunięta z drużyny`, 'info');
          if (this.selectedCharacterId === msg.character_id) {
            this.selectedCharacterId = null;
            localStorage.removeItem(`rpg_selected_char:${this.roomCode}`);
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

  };
})();
