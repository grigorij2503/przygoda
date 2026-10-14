"""Persist the current market visit and its transaction revision."""

from alembic import op
import sqlalchemy as sa


revision = "0006_market_post"
down_revision = "0005_campaign_endings_cursed_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("game_sessions")}
    if "market_state" not in existing:
        op.add_column("game_sessions", sa.Column("market_state", sa.JSON(), nullable=False, server_default="{}"))
    if "market_revision" not in existing:
        op.add_column("game_sessions", sa.Column("market_revision", sa.Integer(), nullable=False, server_default="0"))
    action_columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("player_actions")}
    if "craft_item_ids" not in action_columns:
        op.add_column("player_actions", sa.Column("craft_item_ids", sa.JSON(), nullable=True))


def downgrade() -> None:
    action_columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("player_actions")}
    if "craft_item_ids" in action_columns:
        with op.batch_alter_table("player_actions") as batch_op:
            batch_op.drop_column("craft_item_ids")
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("game_sessions")}
    with op.batch_alter_table("game_sessions") as batch_op:
        if "market_revision" in existing:
            batch_op.drop_column("market_revision")
        if "market_state" in existing:
            batch_op.drop_column("market_state")
