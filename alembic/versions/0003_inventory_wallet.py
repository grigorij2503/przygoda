"""Add a persistent per-character wallet for future campaign shops."""

from alembic import op
import sqlalchemy as sa


revision = "0003_inventory_wallet"
down_revision = "0002_encounter_difficulty"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("characters")}
    if "coins" not in columns:
        op.add_column(
            "characters",
            sa.Column("coins", sa.Integer(), nullable=False, server_default="0"),
        )
    op.execute("UPDATE characters SET coins = 0 WHERE coins IS NULL OR coins < 0")


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("characters")}
    if "coins" in columns:
        with op.batch_alter_table("characters") as batch_op:
            batch_op.drop_column("coins")
