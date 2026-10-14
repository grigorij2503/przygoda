"""Add per-room password credentials for parallel campaigns."""

from alembic import op
import sqlalchemy as sa


revision = "0008_multi_room_access"
down_revision = "0007_character_breaks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("game_sessions")
    }
    if "room_password_hash" not in existing:
        op.add_column(
            "game_sessions",
            sa.Column("room_password_hash", sa.String(length=255), nullable=True),
        )


def downgrade() -> None:
    existing = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("game_sessions")
    }
    if "room_password_hash" in existing:
        with op.batch_alter_table("game_sessions") as batch_op:
            batch_op.drop_column("room_password_hash")
