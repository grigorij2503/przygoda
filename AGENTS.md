# Repository Guidelines

## Project Structure & Module Organization
This is a Python/FastAPI multiplayer TTRPG application with Gemini narration and generated illustrations.
- `app/main.py`: HTTP routes, WebSockets, and turn orchestration.
- `app/models.py`, `database.py`, and `schemas.py`: SQLAlchemy persistence and Pydantic contracts, including named world-lore entries and character death state.
- `app/dice.py`, `combat.py`, `inventory.py`, `loot.py`, and `magic.py`: server-side dice, targeted ally support, death/stabilization/resurrection, equipment, loot/crafting, and class magic rules.
- `app/map_generator.py`: deterministic campaign-map generation and map serialization.
- `app/gemini_service.py`: structured Gemini narration, campaign setup, and generated scene images.
- `app/push_service.py` and `generate_vapid_keys.py`: Web Push delivery and VAPID setup.
- `app/websocket_manager.py`: real-time event and chat broadcasting.
- `app/templates/index.html`: accessible Jinja2/Alpine.js interface with a compact mobile action sheet, categorized world chronicle, and interactive campaign map; `app/static/` contains JavaScript, CSS, icons, the PWA manifest, and service worker.
- `tests/`: dice, combat, loot/crafting, API, lobby/admin, full turn resolution, and WebSocket chat tests.
- `uploads/`: generated images; `data/`: Docker-mounted SQLite storage.

## Current Feature Baseline
The maintained feature set includes room-password access, a GM PIN and admin tools, lobby/readiness flow, server-side random d20 rolls, levels up to 25, equipment limits, boss phases and status effects, targeted support actions, explicit downed/stable/dead states with Cleric resurrection, Wizard and Cleric abilities, location/boss loot, post-boss crafting, a persistent zoomable/pannable campaign map, a categorized shared world chronicle for named bosses, locations, NPCs, weapons/artifacts, and team attacks, proxy-action voting for inactive players, persistent chat and personal notes, accessible dialogs and notifications, reduced-motion support, Web Push, PWA support, automatic session/WebSocket resynchronization after browser or device suspension with a welcome-back cue, and on-demand scene illustration. Keep this baseline synchronized with implementation changes.

## Build, Test, and Development Commands
Use Python 3.11+ locally; Docker uses Python 3.12. Run commands from the repository root.
- `python -m venv .venv`: create a virtual environment; activate it in PowerShell with `.\.venv\Scripts\Activate.ps1`.
- `python -m pip install -r requirements.txt`: install application and testing dependencies.
- `Copy-Item .env.example .env`: initialize local configuration if `.env` does not exist.
- `python -m uvicorn app.main:app --reload --port 8000`: start the development server.
- `docker compose up -d --build`: build and start the container.

There is no separate frontend build step.

## Coding Style & Naming Conventions
Follow surrounding code: four-space Python indentation, `snake_case` functions and modules, `PascalCase` classes, and uppercase configuration constants. Preserve existing JavaScript naming and indentation. Use type annotations for backend interfaces and Pydantic models for structured payloads. Keep database access asynchronous. No formatter or linter is currently configured.

## Testing Guidelines
Tests use pytest, pytest-asyncio, and HTTPX ASGI clients. Name files `test_*.py` and functions `test_<behavior>`. No coverage threshold is configured. The suite command, for the maintainer's reference, is `python -m pytest tests/`. Integration tests can touch the configured database; use an isolated database when executing them.

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
