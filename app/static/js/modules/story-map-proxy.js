(() => {
  'use strict';
  const features = window.TTRPG_FEATURES = window.TTRPG_FEATURES || {};
  features.storyMapProxy = {
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

    get loreCategories() {
      return [
        { id: 'boss', label: 'Bossowie', icon: '👑' },
        { id: 'location', label: 'Miejsca', icon: '🏰' },
        { id: 'npc', label: 'Napotkani NPC', icon: '🧙' },
        { id: 'weapon', label: 'Oręż i artefakty', icon: '🗡️' },
        { id: 'attack', label: 'Ataki drużynowe', icon: '💥' }
      ];
    },

    loreEntitiesByCategory(category) {
      return (this.session?.lore_entities || []).filter(entity => entity.category === category);
    },

    loreCategory(category) {
      return this.loreCategories.find(item => item.id === category)
        || { id: category, label: 'Pozostałe legendy', icon: '✨' };
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

    get mapBaseBounds() {
      const nodes = (this.campaignMap?.nodes || []).filter(node => node.visibility !== 'hidden');
      if (!nodes.length) {
        return { x: 0, y: 0, width: this.campaignMap?.width || 1100, height: this.campaignMap?.height || 500 };
      }
      const padding = 70;
      const left = Math.min(...nodes.map(node => node.x - node.width / 2)) - padding;
      const right = Math.max(...nodes.map(node => node.x + node.width / 2)) + padding;
      const top = Math.min(...nodes.map(node => node.y - node.height / 2)) - padding;
      const bottom = Math.max(...nodes.map(node => node.y + node.height / 2)) + padding;
      return { x: left, y: top, width: Math.max(260, right - left), height: Math.max(220, bottom - top) };
    },

    get mapViewBox() {
      const bounds = this.mapBaseBounds;
      const width = bounds.width / this.mapZoom;
      const height = bounds.height / this.mapZoom;
      const x = bounds.x + (bounds.width - width) / 2 + this.mapPanX;
      const y = bounds.y + (bounds.height - height) / 2 + this.mapPanY;
      return `${x} ${y} ${width} ${height}`;
    },

    openMap() {
      this.selectedMapNodeId = this.campaignMap?.current_node_id || null;
      this.resetMapView();
      this.showMapModal = true;
      this.scheduleMapRender();
    },

    resetMapView() {
      this.mapZoom = 1;
      this.mapPanX = 0;
      this.mapPanY = 0;
    },

    adjustMapZoom(delta) {
      this.mapZoom = Math.max(0.75, Math.min(3, this.mapZoom + delta));
    },

    showPartyOnMap() {
      const node = this.currentMapNode;
      if (!node) return;
      this.selectedMapNodeId = node.id;
      const bounds = this.mapBaseBounds;
      this.mapZoom = 2;
      this.mapPanX = node.x - (bounds.x + bounds.width / 2);
      this.mapPanY = node.y - (bounds.y + bounds.height / 2);
      this.scheduleMapRender();
    },

    beginMapPan(event) {
      if (event.button !== 0) return;
      event.currentTarget.setPointerCapture?.(event.pointerId);
      this.mapDrag = {
        x: event.clientX,
        y: event.clientY,
        panX: this.mapPanX,
        panY: this.mapPanY,
        width: event.currentTarget.clientWidth,
        height: event.currentTarget.clientHeight
      };
    },

    continueMapPan(event) {
      if (!this.mapDrag) return;
      const bounds = this.mapBaseBounds;
      const xUnits = (bounds.width / this.mapZoom) / Math.max(1, this.mapDrag.width);
      const yUnits = (bounds.height / this.mapZoom) / Math.max(1, this.mapDrag.height);
      this.mapPanX = this.mapDrag.panX - (event.clientX - this.mapDrag.x) * xUnits;
      this.mapPanY = this.mapDrag.panY - (event.clientY - this.mapDrag.y) * yUnits;
    },

    endMapPan() {
      this.mapDrag = null;
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
      const sum = Number(this.newChar.strength) + Number(this.newChar.agility) + Number(this.newChar.intellect) + Number(this.newChar.charisma) + Number(this.newChar.perception);
      return 4 - sum;
    },

  };
})();
