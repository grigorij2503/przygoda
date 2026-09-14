from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base
from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

Base = declarative_base()

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

from sqlalchemy import text

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Tymczasowy fallback zgodności dla uruchomień bez polecenia Alembic.
        new_columns = [
            ("game_sessions", "active_boss_name", "VARCHAR(100)"),
            ("game_sessions", "active_boss_title", "VARCHAR(150)"),
            ("game_sessions", "active_boss_hp", "INTEGER"),
            ("game_sessions", "active_boss_max_hp", "INTEGER"),
            ("game_sessions", "active_boss_armor", "INTEGER NOT NULL DEFAULT 0"),
            ("game_sessions", "active_boss_defense_dc", "INTEGER NOT NULL DEFAULT 12"),
            ("game_sessions", "active_boss_phase", "INTEGER NOT NULL DEFAULT 1"),
            ("game_sessions", "active_boss_effects", "JSON"),
            ("game_sessions", "active_boss_features", "JSON"),
            ("game_sessions", "active_boss_telegraph", "JSON"),
            ("game_sessions", "last_loot_character_id", "INTEGER"),
            ("game_sessions", "looted_location_ids", "JSON"),
            ("game_sessions", "crafting_available_until_turn", "INTEGER NOT NULL DEFAULT 0"),
            ("game_sessions", "last_image_generated_at", "DATETIME"),
            ("game_sessions", "pending_naming_category", "VARCHAR(50)"),
            ("game_sessions", "pending_naming_prompt", "TEXT"),
            ("game_sessions", "pending_naming_character_id", "INTEGER"),
            ("game_sessions", "pending_naming_character_name", "VARCHAR(100)"),
            ("game_sessions", "status", "VARCHAR(50)"),
            ("game_sessions", "world_pack_id", "VARCHAR(80) NOT NULL DEFAULT 'dark_fantasy'"),
            ("game_sessions", "world_pack_version", "INTEGER NOT NULL DEFAULT 1"),
            ("characters", "is_ready", "BOOLEAN"),
            ("characters", "class_id", "VARCHAR(80) NOT NULL DEFAULT 'cleric'"),
            ("characters", "perception", "INTEGER NOT NULL DEFAULT 0"),
            ("characters", "personal_note", "TEXT NOT NULL DEFAULT ''"),
            ("characters", "unspent_stat_points", "INTEGER NOT NULL DEFAULT 0"),
            ("characters", "status_effects", "JSON"),
            ("characters", "death_state", "VARCHAR(20) NOT NULL DEFAULT 'alive'"),
            ("characters", "death_failures", "INTEGER NOT NULL DEFAULT 0"),
            ("inventory_items", "hands_required", "INTEGER NOT NULL DEFAULT 1"),
            ("inventory_items", "damage_power", "INTEGER NOT NULL DEFAULT 0"),
            ("turns", "suggested_actions", "TEXT"),
            ("turns", "mechanics_resolved_at", "DATETIME"),
            ("turns", "combat_events", "JSON"),
            ("player_actions", "intent", "VARCHAR(30)"),
            ("player_actions", "magic_ability_id", "VARCHAR(80)"),
            ("player_actions", "ability_id", "VARCHAR(80)"),
            ("player_actions", "target_ref", "VARCHAR(100)"),
            ("player_actions", "status_modifier", "INTEGER NOT NULL DEFAULT 0"),
            ("player_actions", "damage_dealt", "INTEGER NOT NULL DEFAULT 0"),
            ("player_actions", "damage_roll", "INTEGER NOT NULL DEFAULT 0"),
            ("player_actions", "damage_base", "INTEGER NOT NULL DEFAULT 0"),
            ("player_actions", "damage_reduction", "INTEGER NOT NULL DEFAULT 0"),
            ("player_actions", "hp_delta", "INTEGER NOT NULL DEFAULT 0"),
            ("player_actions", "xp_gained", "INTEGER NOT NULL DEFAULT 0"),
            ("player_actions", "submission_source", "VARCHAR(30) NOT NULL DEFAULT 'player'"),
        ]
        for table, col, col_type in new_columns:
            try:
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type};"))
            except Exception:
                pass
        # Ten fallback utrzymuje start przez samo `uvicorn` dla starszej bazy.
        # Alembic pozostaje źródłem wersji schematu i jest uruchamiany w Dockerze.
        await conn.execute(text(
            "UPDATE game_sessions SET world_pack_id = 'dark_fantasy' "
            "WHERE world_pack_id IS NULL OR world_pack_id = ''"
        ))
        await conn.execute(text(
            "UPDATE game_sessions SET world_pack_version = 1 "
            "WHERE world_pack_version IS NULL OR world_pack_version < 1"
        ))
        await conn.execute(text(
            """
            UPDATE characters
            SET class_id = CASE
                WHEN lower(character_class) LIKE '%woj%' OR lower(character_class) LIKE '%rycerz%' THEN 'warrior'
                WHEN character_class LIKE '%Łot%' OR character_class LIKE '%łot%'
                  OR lower(character_class) LIKE '%zabójc%' OR lower(character_class) LIKE '%zabojc%'
                  OR character_class LIKE '%Złodziej%' OR character_class LIKE '%złodziej%'
                  OR lower(character_class) LIKE '%zlodziej%' THEN 'rogue'
                WHEN lower(character_class) LIKE '%mag%' OR lower(character_class) LIKE '%czaro%' THEN 'wizard'
                ELSE 'cleric'
            END
            WHERE (class_id IS NULL OR class_id = '' OR class_id = 'cleric')
              AND session_id IN (
                  SELECT id FROM game_sessions
                  WHERE world_pack_id = 'dark_fantasy' AND world_pack_version = 1
              )
            """
        ))
        await conn.execute(text(
            "UPDATE player_actions SET ability_id = magic_ability_id "
            "WHERE ability_id IS NULL AND magic_ability_id IS NOT NULL"
        ))
        try:
            await conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_player_action_turn_character "
                "ON player_actions (turn_id, character_id);"
            ))
        except Exception:
            # Zachowaj start aplikacji z historyczną bazą, nawet jeśli zawiera stare duplikaty.
            pass
