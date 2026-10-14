"""Persist usable named attacks and consistent NPC identities."""

from alembic import op
import sqlalchemy as sa


revision = "0004_lore_discoveries"
down_revision = "0003_inventory_wallet"
branch_labels = None
depends_on = None


_COLUMNS = {
    "game_sessions": (
        sa.Column("pending_naming_turn_number", sa.Integer(), nullable=True),
        sa.Column("pending_naming_map_node_id", sa.String(100), nullable=True),
        sa.Column("pending_naming_question", sa.Text(), nullable=True),
    ),
    "player_actions": (
        sa.Column("named_attack_id", sa.Integer(), nullable=True),
    ),
    "named_lore_entities": (
        sa.Column("discovered_turn_number", sa.Integer(), nullable=True),
        sa.Column("map_node_id", sa.String(100), nullable=True),
        sa.Column("npc_disposition", sa.String(20), nullable=True),
        sa.Column("npc_catchphrase", sa.String(150), nullable=True),
        sa.Column("npc_goal", sa.String(200), nullable=True),
    ),
}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table, columns in _COLUMNS.items():
        existing = {column["name"] for column in inspector.get_columns(table)}
        for column in columns:
            if column.name not in existing:
                op.add_column(table, column)
    op.execute(
        "UPDATE named_lore_entities SET discovered_turn_number = "
        "(SELECT current_turn_number FROM game_sessions "
        "WHERE game_sessions.id = named_lore_entities.session_id) "
        "WHERE category = 'attack' AND discovered_turn_number IS NULL"
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table, columns in reversed(tuple(_COLUMNS.items())):
        existing = {column["name"] for column in inspector.get_columns(table)}
        with op.batch_alter_table(table) as batch_op:
            for column in reversed(columns):
                if column.name in existing:
                    batch_op.drop_column(column.name)
