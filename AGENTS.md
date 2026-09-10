# Repository Guidelines

## Project Structure & Module Organization
This is a Python/FastAPI multiplayer TTRPG application with Gemini narration and generated illustrations.
- `app/main.py`: HTTP routes, WebSockets, and turn orchestration.
- `app/models.py`, `database.py`, and `schemas.py`: SQLAlchemy persistence and Pydantic contracts.
- `app/dice.py`, `gemini_service.py`, and `websocket_manager.py`: dice mechanics, AI integration, and event broadcasting.
- `app/templates/index.html`: Jinja2 interface; `app/static/` contains JavaScript, CSS, and PWA assets.
- `tests/`: dice, API, lobby, turn resolution, and WebSocket tests.
- `uploads/`: generated images; `data/`: Docker-mounted SQLite storage.

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
History uses short English subjects such as `Images fix` and `app as a PWA`; no strict prefix convention is established. Write descriptive subjects focused on the change. PRs should explain behavior changes, reference relevant issues, and include screenshots for UI changes. Report only validation actually performed.

## Security & Configuration
Keep secrets in `.env`; update `.env.example` when adding settings. Never commit credentials, SQLite databases, or generated uploads.

## Agent Instructions
Respond in Polish, concisely, as to an engineer. State concrete changes and relevant limitations without unnecessary explanation. Do not run tests or propose running them; the user runs tests independently unless explicitly requesting otherwise.
