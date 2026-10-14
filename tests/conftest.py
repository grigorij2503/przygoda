import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.database as database
import app.push_service as push_service
import app.services.chat_service as chat_service
import app.services.runtime as runtime
from app.database import Base
from app.models import GameSession, Turn


@pytest.fixture
def isolated_dark_fantasy_db(tmp_path, monkeypatch):
    """Bind app database access to a disposable Dark Fantasy campaign."""
    database_path = (tmp_path / "dark-fantasy-test.db").resolve().as_posix()
    sync_engine = create_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(sync_engine)

    with Session(sync_engine) as db:
        session = GameSession(
            room_code="kampania-1",
            world_pack_id="dark_fantasy",
            world_pack_version=1,
            title="Cienie Nad Przeklętą Kryptą",
            setting_theme="Dark Fantasy / Gotycki Horror",
            campaign_intro="Wyprawa rozpoczęta.",
            current_turn_number=1,
            status="in_progress",
            is_turn_resolving=False,
        )
        db.add(session)
        db.flush()
        db.add(Turn(
            session_id=session.id,
            turn_number=1,
            status="waiting_for_actions",
            gm_narration=session.campaign_intro,
            next_turn_prompt=(
                "Szkielety unoszą zardzewiałe miecze. Co robicie?"
            ),
            suggested_actions=[],
            combat_events=[],
        ))
        db.commit()
    sync_engine.dispose()

    async_engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path}",
        poolclass=NullPool,
    )
    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)

    monkeypatch.setattr(database, "engine", async_engine)
    monkeypatch.setattr(database, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(runtime, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(chat_service, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(push_service, "AsyncSessionLocal", session_factory)

    yield session_factory
