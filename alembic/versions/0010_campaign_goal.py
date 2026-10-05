"""Persist a spoiler-safe campaign goal shown in the world chronicle."""

from alembic import op
import sqlalchemy as sa


revision = "0010_campaign_goal"
down_revision = "0009_scenario_narrative_form"
branch_labels = None
depends_on = None


def upgrade() -> None:
    session_columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("game_sessions")
    }
    if "campaign_goal_summary" not in session_columns:
        op.add_column(
            "game_sessions",
            sa.Column(
                "campaign_goal_summary",
                sa.Text(),
                nullable=False,
                server_default="",
            ),
        )
    if "campaign_current_clue" not in session_columns:
        op.add_column(
            "game_sessions",
            sa.Column(
                "campaign_current_clue",
                sa.Text(),
                nullable=False,
                server_default="",
            ),
        )
    if "campaign_goal_status" not in session_columns:
        op.add_column(
            "game_sessions",
            sa.Column(
                "campaign_goal_status",
                sa.String(length=30),
                nullable=False,
                server_default="started",
            ),
        )
    op.execute(
        "UPDATE game_sessions SET campaign_goal_status = "
        "CASE WHEN status = 'completed' THEN 'completed' ELSE 'started' END "
        "WHERE campaign_goal_status IS NULL OR campaign_goal_status NOT IN "
        "('started', 'in_progress', 'near_resolution', 'completed')"
    )


def downgrade() -> None:
    session_columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("game_sessions")
    }
    with op.batch_alter_table("game_sessions") as batch_op:
        for column_name in (
            "campaign_goal_status",
            "campaign_current_clue",
            "campaign_goal_summary",
        ):
            if column_name in session_columns:
                batch_op.drop_column(column_name)
