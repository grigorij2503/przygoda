"""Add reversible character participation breaks."""

from alembic import op
import sqlalchemy as sa


revision = "0007_character_breaks"
down_revision = "0006_market_post"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("characters")
    }
    if "participation_status" not in existing:
        op.add_column(
            "characters",
            sa.Column(
                "participation_status",
                sa.String(length=20),
                nullable=False,
                server_default="active",
            ),
        )
    if "break_started_turn" not in existing:
        op.add_column(
            "characters",
            sa.Column("break_started_turn", sa.Integer(), nullable=True),
        )
    op.execute(
        "UPDATE characters SET participation_status = 'active' "
        "WHERE participation_status IS NULL "
        "OR participation_status NOT IN ('active', 'on_break')"
    )


def downgrade() -> None:
    existing = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("characters")
    }
    with op.batch_alter_table("characters") as batch_op:
        if "break_started_turn" in existing:
            batch_op.drop_column("break_started_turn")
        if "participation_status" in existing:
            batch_op.drop_column("participation_status")
