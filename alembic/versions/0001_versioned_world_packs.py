"""Add campaign world versioning, stable class and ability ids, and perception."""

from alembic import op
import sqlalchemy as sa


revision = "0001_versioned_world_packs"
down_revision = None
branch_labels = None
depends_on = None


def _column_names(table_name: str) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def upgrade() -> None:
    # A fresh database receives the complete current schema. On an existing
    # database create_all is a no-op and the additive columns below are applied.
    from app.database import Base
    from app import models  # noqa: F401

    Base.metadata.create_all(op.get_bind())

    session_columns = _column_names("game_sessions")
    if "world_pack_id" not in session_columns:
        op.add_column(
            "game_sessions",
            sa.Column(
                "world_pack_id",
                sa.String(length=80),
                nullable=False,
                server_default="dark_fantasy",
            ),
        )
    if "world_pack_version" not in session_columns:
        op.add_column(
            "game_sessions",
            sa.Column(
                "world_pack_version",
                sa.Integer(),
                nullable=False,
                server_default="1",
            ),
        )

    character_columns = _column_names("characters")
    if "class_id" not in character_columns:
        op.add_column(
            "characters",
            sa.Column(
                "class_id",
                sa.String(length=80),
                nullable=False,
                server_default="cleric",
            ),
        )
    if "perception" not in character_columns:
        op.add_column(
            "characters",
            sa.Column(
                "perception",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )

    action_columns = _column_names("player_actions")
    if "ability_id" not in action_columns:
        op.add_column(
            "player_actions",
            sa.Column("ability_id", sa.String(length=80), nullable=True),
        )

    op.execute(
        "UPDATE game_sessions SET world_pack_id = 'dark_fantasy' "
        "WHERE world_pack_id IS NULL OR world_pack_id = ''"
    )
    op.execute(
        "UPDATE game_sessions SET world_pack_version = 1 "
        "WHERE world_pack_version IS NULL OR world_pack_version < 1"
    )
    op.execute(
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
    )
    op.execute(
        "UPDATE player_actions SET ability_id = magic_ability_id "
        "WHERE ability_id IS NULL AND magic_ability_id IS NOT NULL"
    )


def downgrade() -> None:
    with op.batch_alter_table("player_actions") as batch_op:
        batch_op.drop_column("ability_id")
    with op.batch_alter_table("characters") as batch_op:
        batch_op.drop_column("perception")
        batch_op.drop_column("class_id")
    with op.batch_alter_table("game_sessions") as batch_op:
        batch_op.drop_column("world_pack_version")
        batch_op.drop_column("world_pack_id")
