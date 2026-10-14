"""Store a campaign epilogue and secondary penalties on cursed items."""

from alembic import op
import sqlalchemy as sa


revision = "0005_campaign_endings_cursed_items"
down_revision = "0004_lore_discoveries"
branch_labels = None
depends_on = None


_COLUMNS = {
    "game_sessions": (
        sa.Column("campaign_epilogue", sa.Text(), nullable=False, server_default=""),
    ),
    "inventory_items": (
        sa.Column("curse_stat", sa.String(50), nullable=True),
        sa.Column("curse_penalty", sa.Integer(), nullable=False, server_default="0"),
    ),
}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table, columns in _COLUMNS.items():
        existing = {column["name"] for column in inspector.get_columns(table)}
        for column in columns:
            if column.name not in existing:
                op.add_column(table, column)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table, columns in reversed(tuple(_COLUMNS.items())):
        existing = {column["name"] for column in inspector.get_columns(table)}
        with op.batch_alter_table(table) as batch_op:
            for column in reversed(columns):
                if column.name in existing:
                    batch_op.drop_column(column.name)
