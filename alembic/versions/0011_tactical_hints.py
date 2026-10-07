"""Persist per-character hints generated with the normal turn narration."""

from alembic import op
import sqlalchemy as sa


revision = "0011_tactical_hints"
down_revision = "0010_campaign_goal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("turns")
    }
    if "character_suggested_actions" not in columns:
        op.add_column(
            "turns",
            sa.Column("character_suggested_actions", sa.JSON(), nullable=False, server_default="{}"),
        )


def downgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("turns")
    }
    if "character_suggested_actions" in columns:
        with op.batch_alter_table("turns") as batch_op:
            batch_op.drop_column("character_suggested_actions")
