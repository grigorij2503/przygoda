# Repository Guidelines

## Project Structure & Module Organization
This is a Python/FastAPI multiplayer TTRPG application with Gemini narration and generated illustrations.
- `app/main.py`: FastAPI composition, middleware, static mounts, lifespan wiring, and domain-router registration.
- `app/api/routers/`: UI, auth, push, admin, session, character, turn, action, image, world-catalog, and chat/WebSocket route registration; keep public paths and response models stable.
- `app/services/`: extracted application behavior. `runtime.py` contains shared helpers and startup compatibility logic; focused services own sessions, characters, turns, proxy voting, chat, images, the read-only world catalog, push subscriptions, auth, admin, and UI responses.
- `app/worlds/models.py`, `registry.py`, and `packs/`: frozen Pydantic `WorldPack` contracts, validated ID/version/reference lookup, and immutable declarative JSON definitions. `dark_fantasy@1` is the only registered pack; zero-argument fallback exists only for legacy rows lacking both persisted world fields.
- `app/models.py`, `database.py`, and `schemas.py`: SQLAlchemy persistence and Pydantic contracts, including pinned world-pack versions, stable class/ability IDs, five character attributes, named world-lore entries, death state, and the persistent per-campaign calendar-day image-generation quota.
- `app/dice.py`, `combat.py`, `inventory.py`, `loot.py`, and `magic.py`: weighted narrative intent/stat interpretation, server-side dice, targeted ally support, death/stabilization/resurrection, equipment, loot/crafting, and class magic rules.
- `app/map_generator.py`: deterministic campaign-map generation and map serialization.
- `app/gemini_service.py`: structured Gemini narration, campaign setup, and generated scene images.
- `app/push_service.py` and `generate_vapid_keys.py`: Web Push delivery and VAPID setup.
- `app/websocket_manager.py`: real-time event and chat broadcasting.
- `app/templates/index.html`: document shell and ordered frontend assets; `app/templates/partials/` owns the auth gate, lobby, character selection, game-table panels, and individual accessible modals.
- `app/static/js/app.js` composes the single Alpine `rpgGame` component from feature objects in `app/static/js/modules/`; named local Alpine components own story-hint and attribute-info disclosure state.
- `app/static/css/style.css` is the cascade entrypoint for token, base, component, inventory, map, lore, feedback, and responsive modules under `app/static/css/modules/`; `app/static/sw.js` must precache every versioned local frontend module.
- `tests/`: dice, combat, loot/crafting, API, lobby/admin, full turn resolution, WebSocket chat, the current-world and frontend module contracts, world-registry validation, and isolated Alembic migration coverage.
- `docs/WORLD_PACK_ROADMAP.md`, `docs/WORLD_DEPENDENCY_INVENTORY.md`, and `docs/adr/0001-versioned-world-packs.md`: staged multi-world roadmap, inventory of Dark Fantasy coupling, and the accepted direction for immutable declarative world packs.
- `alembic/` and `alembic.ini`: versioned schema migrations. Revision `0001_versioned_world_packs` creates a fresh schema or additively backfills existing campaigns; Docker upgrades to head before starting Uvicorn.
- `uploads/`: generated images; `data/`: Docker-mounted SQLite storage.

## Current Feature Baseline
The maintained feature set includes room-password access, a GM PIN and admin tools with emergency five-attribute correction for any character, lobby/readiness flow, server-side random d20 rolls, narrative-first weighted recognition of the dominant action intent and tested stat with a live confidence/reason preview and optional player correction, levels up to 25, equipment limits, explicit equipment-claim validation with Polish diacritic normalization, boss phases and status effects, targeted support actions, class-personalized quick actions with magic exposed only through unlocked Wizard or Cleric abilities and fixing its own casting intent/stat, class-neutral Gemini action hints, explicit downed/stable/dead states with Cleric resurrection, Wizard and Cleric abilities, location/boss loot, post-boss crafting that safely handles ORM defaults before persistence, a persistent zoomable/pannable campaign map, a categorized shared world chronicle for named bosses, locations, NPCs, weapons/artifacts, and team attacks, proxy-action voting for inactive players, persistent chat and personal notes, collapsible sticky session and action panels on phones and desktop viewports up to 1799 px, accessible dialogs and notifications, reduced-motion support, Web Push, PWA support, automatic session/WebSocket resynchronization after browser or device suspension with a welcome-back cue, and on-demand scene illustration limited atomically to one successful generation per campaign per `Europe/Warsaw` calendar day. The validated registry exposes `dark_fantasy@1` through `GET /api/worlds`; each campaign persists its exact pack ID/version, characters persist `class_id`, and actions persist `ability_id` alongside compatibility fields. Perception is active in ORM, API, item contracts, dice interpretation, Gemini context, creation, cards, lobby, level-up, and GM correction; sensory awareness must remain distinct from intellectual analysis. World selection is not yet exposed in the UI, and active campaigns reject pack changes. Keep this baseline synchronized with implementation changes.

## Build, Test, and Development Commands
Use Python 3.11+ locally; Docker uses Python 3.12. Run commands from the repository root.
- `python -m venv .venv`: create a virtual environment; activate it in PowerShell with `.\.venv\Scripts\Activate.ps1`.
- `python -m pip install -r requirements.txt`: install application and testing dependencies.
- `Copy-Item .env.example .env`: initialize local configuration if `.env` does not exist.
- `python -m alembic upgrade head`: migrate the configured database after taking a backup of any active SQLite campaign.
- `python -m uvicorn app.main:app --reload --port 8000`: start the development server.
- `docker compose up -d --build`: build and start the container.

There is no separate frontend build step.

## Coding Style & Naming Conventions
Follow surrounding code: four-space Python indentation, `snake_case` functions and modules, `PascalCase` classes, and uppercase configuration constants. Preserve existing JavaScript naming and indentation. Use type annotations for backend interfaces and Pydantic models for structured payloads. Keep database access asynchronous. No formatter or linter is currently configured.

## Testing Guidelines
Tests use pytest, pytest-asyncio, and HTTPX ASGI clients. Name files `test_*.py` and functions `test_<behavior>`. Intent/stat tests cover ambiguous prose, including incidental shouts and defensive words used inside offensive declarations. No coverage threshold is configured. The suite command, for the maintainer's reference, is `python -m pytest tests/`. Integration tests can touch the configured database; use an isolated database when executing them.

Tests that deliberately reuse an existing turn must clear `resolved_at`, `mechanics_resolved_at`, and stale combat events before submitting a new action. Map assertions must resolve special nodes through `start_node_id` or `final_node_id`, because branch nodes are appended after the main path and list position is not a stable domain contract.

`tests/test_world_migration.py` creates an isolated legacy SQLite schema and invokes Alembic to verify additive backfills while preserving campaign progress. Migration tests must never point at `data/ttrpg_game.db` or another active campaign database.

WebSocket integration tests running against a persistent database must consume an optional initial `CHAT_HISTORY` snapshot before asserting the newly broadcast `CHAT_MESSAGE`; prior chat data is valid application state, not an event-order failure.

`tests/test_current_world_contract.py` is the compatibility gate for the staged multi-world refactor. Its route walker must continue to support FastAPI's lazily included routers. Update its fixture only for intentional public behavior changes. Backend/frontend moves must preserve the route table, WebSocket event names, current class starter sets, ability books, session shape, map profile, and UI markers recorded there. Consult `docs/WORLD_DEPENDENCY_INVENTORY.md` before moving world-specific behavior. Published world-pack versions described by ADR 0001 are immutable, declarative data and must not contain executable Python, JavaScript, arbitrary HTML/CSS, or untrusted external asset URLs.

World packs are loaded and fully validated when `app.worlds.registry` is imported. All collections in their Pydantic models must remain tuples or frozen child models. Resolve explicit packs only by the complete `(id, version)` pair and fail closed for unknown values; the zero-argument lookup is the sole legacy fallback to `dark_fantasy@1`. New pack fields must use controlled schemas and mechanic keys rather than arbitrary mappings or executable behavior.

Frontend refactors must preserve the property descriptors of the main Alpine component, rendered DOM selectors and accessibility attributes, CSS cascade order, and script initialization order. When adding or renaming a local JS/CSS module, bump its query-string version and the service-worker cache name, then include the exact versioned path in `PRECACHE_ASSETS`. There remains no separate frontend build step.

Perception is the fifth canonical attribute. Historical characters backfill to `0`; their four prior attributes and HP/XP/level, the character-creation point budget, and the HP formula remain unchanged. Perception/awareness/sensory actions must stay distinct from intellect/knowledge/analysis actions. Every roadmap stage includes a user-facing local build-and-click acceptance checklist. Keep those checklists current when an implementation changes the expected manual verification path, and always direct manual state-changing checks to an isolated database or a copy rather than the active campaign database.

## Commit & Pull Request Guidelines
History uses short English subjects such as `Images fix` and `app as a PWA`; no strict prefix convention is established. Write descriptive subjects focused on the change. PRs should explain behavior changes, reference relevant issues, and include screenshots for UI changes. Report only validation actually performed. At the end of every completed change, propose a short English commit subject to the user; do not create the commit unless explicitly requested.

## Security & Configuration
Keep secrets in `.env`; update `.env.example` when adding settings. Never commit credentials, SQLite databases, or generated uploads.

## Agent Instructions
Respond in Polish, concisely, as to an engineer. State concrete changes and relevant limitations without unnecessary explanation. Do not run tests or propose running them; the user runs tests independently unless explicitly requesting otherwise.

Treat documentation as part of every completed change. Before finishing any implementation, configuration, structure, command, or workflow change:
- update `README.md` so its feature list, setup instructions, configuration, project tree, and test inventory match the repository;
- update `AGENTS.md` with the corresponding repository guidance or current feature baseline;
- mention both documentation updates in the final summary;
- finish the final response with `Proponowana nazwa commitu: <short English subject>`.

Do not leave either Markdown file stale merely because a change is small. If a change does not affect an existing section, add a concise note to the most relevant section instead of creating an unrelated changelog entry.
