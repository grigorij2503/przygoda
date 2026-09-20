import os
import sqlite3
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_alembic_backfills_existing_campaign_without_changing_progress(tmp_path):
    database_path = tmp_path / "historical_campaign.db"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE game_sessions (
            id INTEGER PRIMARY KEY,
            room_code VARCHAR(50) NOT NULL,
            title VARCHAR(200),
            current_turn_number INTEGER
        );
        CREATE TABLE characters (
            id INTEGER PRIMARY KEY,
            session_id INTEGER NOT NULL,
            player_name VARCHAR(100) NOT NULL,
            name VARCHAR(100) NOT NULL,
            character_class VARCHAR(100),
            level INTEGER,
            xp INTEGER,
            current_hp INTEGER,
            max_hp INTEGER,
            strength INTEGER,
            agility INTEGER,
            intellect INTEGER,
            charisma INTEGER
        );
        CREATE TABLE player_actions (
            id INTEGER PRIMARY KEY,
            magic_ability_id VARCHAR(80)
        );
        CREATE TABLE turns (
            id INTEGER PRIMARY KEY,
            session_id INTEGER NOT NULL,
            turn_number INTEGER NOT NULL
        );
        INSERT INTO game_sessions VALUES (1, 'historia', 'Stara kampania', 7);
        INSERT INTO characters VALUES (
            1, 1, 'Gracz', 'Arkanista', 'Czarodziej', 9, 1234, 17, 35, 3, 2, 7, 1
        );
        INSERT INTO player_actions VALUES (1, 'lightning_bolt');
        INSERT INTO turns VALUES (1, 1, 7);
        """
    )
    connection.commit()
    connection.close()

    environment = os.environ.copy()
    environment["DATABASE_URL"] = (
        f"sqlite+aiosqlite:///{database_path.as_posix()}"
    )
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    connection = sqlite3.connect(database_path)
    session = connection.execute(
        "SELECT title, current_turn_number, world_pack_id, world_pack_version "
        "FROM game_sessions WHERE id = 1"
    ).fetchone()
    character = connection.execute(
        "SELECT level, xp, current_hp, max_hp, strength, agility, intellect, "
        "charisma, perception, class_id, coins FROM characters WHERE id = 1"
    ).fetchone()
    action = connection.execute(
        "SELECT magic_ability_id, ability_id FROM player_actions WHERE id = 1"
    ).fetchone()
    turn = connection.execute(
        "SELECT session_id, turn_number, challenge_tier FROM turns WHERE id = 1"
    ).fetchone()
    revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    connection.close()

    assert session == ("Stara kampania", 7, "dark_fantasy", 1)
    assert character == (9, 1234, 17, 35, 3, 2, 7, 1, 0, "wizard", 0)
    assert action == ("lightning_bolt", "lightning_bolt")
    assert turn == (1, 7, "standard")
    assert revision == ("0005_campaign_endings_cursed_items",)
