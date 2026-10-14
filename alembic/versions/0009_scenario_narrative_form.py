"""Persist the selected scenario and character narrative form."""

from alembic import op
import sqlalchemy as sa


revision = "0009_scenario_narrative_form"
down_revision = "0008_multi_room_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    session_columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("game_sessions")
    }
    if "scenario_type" not in session_columns:
        op.add_column(
            "game_sessions",
            sa.Column("scenario_type", sa.String(length=200), nullable=True),
        )

    character_columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("characters")
    }
    if "narrative_form" not in character_columns:
        op.add_column(
            "characters",
            sa.Column(
                "narrative_form",
                sa.String(length=20),
                nullable=False,
                server_default="neutral",
            ),
        )
    op.execute(
        "UPDATE characters SET narrative_form = 'neutral' "
        "WHERE narrative_form IS NULL "
        "OR narrative_form NOT IN ('masculine', 'feminine', 'neutral')"
    )


def downgrade() -> None:
    character_columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("characters")
    }
    if "narrative_form" in character_columns:
        with op.batch_alter_table("characters") as batch_op:
            batch_op.drop_column("narrative_form")

    session_columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("game_sessions")
    }
    if "scenario_type" in session_columns:
        with op.batch_alter_table("game_sessions") as batch_op:
            batch_op.drop_column("scenario_type")
