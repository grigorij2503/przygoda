"""Persist controlled challenge tiers for noncombat turns."""

from alembic import op
import sqlalchemy as sa


revision = "0002_encounter_difficulty"
down_revision = "0001_versioned_world_packs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("turns")}
    if "challenge_tier" not in columns:
        op.add_column(
            "turns",
            sa.Column(
                "challenge_tier",
                sa.String(length=20),
                nullable=False,
                server_default="standard",
            ),
        )
    op.execute(
        "UPDATE turns SET challenge_tier = 'standard' "
        "WHERE challenge_tier IS NULL OR challenge_tier NOT IN ('standard', 'hard', 'climactic')"
    )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("turns")}
    if "challenge_tier" in columns:
        with op.batch_alter_table("turns") as batch_op:
            batch_op.drop_column("challenge_tier")
