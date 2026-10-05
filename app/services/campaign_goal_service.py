"""Server-owned, spoiler-safe campaign goal state."""

from app.models import GameSession


CAMPAIGN_GOAL_STATUSES = {"started", "in_progress", "near_resolution", "completed"}


def _compact_public_text(value: str | None, max_length: int) -> str:
    return " ".join(str(value or "").split())[:max_length].strip()


def main_mission_from_session(session: GameSession) -> str:
    scenario = _compact_public_text(session.scenario_type, 200)
    if scenario:
        return f"Zbadać sprawę „{scenario}”."
    title = _compact_public_text(session.title, 200)
    return f"Poznać cel wyprawy „{title}”." if title else "Poznać cel wyprawy."


def reset_campaign_goal(
    session: GameSession,
    *,
    current_clue: str | None = None,
) -> None:
    session.campaign_goal_summary = main_mission_from_session(session)
    session.campaign_current_clue = _compact_public_text(current_clue, 1200)
    session.campaign_goal_status = "started"


def ensure_campaign_goal(
    session: GameSession,
    *,
    current_clue: str | None = None,
    near_resolution: bool = False,
) -> bool:
    changed = False
    if not _compact_public_text(session.campaign_goal_summary, 1200):
        session.campaign_goal_summary = main_mission_from_session(session)
        changed = True
    if not _compact_public_text(session.campaign_current_clue, 1200) and current_clue:
        session.campaign_current_clue = _compact_public_text(current_clue, 1200)
        changed = True
    if session.status == "completed":
        expected_status = "completed"
    elif near_resolution:
        expected_status = "near_resolution"
    else:
        expected_status = session.campaign_goal_status
    if expected_status not in CAMPAIGN_GOAL_STATUSES:
        expected_status = "started"
    if expected_status == "started" and int(session.current_turn_number or 1) > 1:
        expected_status = "in_progress"
    if session.campaign_goal_status != expected_status:
        session.campaign_goal_status = expected_status
        changed = True
    return changed


def advance_campaign_goal(
    session: GameSession,
    *,
    current_clue: str,
    near_resolution: bool = False,
) -> None:
    ensure_campaign_goal(session)
    session.campaign_current_clue = _compact_public_text(current_clue, 1200)
    if session.status == "completed":
        session.campaign_goal_status = "completed"
    elif (
        session.campaign_goal_status != "near_resolution"
        and near_resolution
    ):
        session.campaign_goal_status = "near_resolution"
    elif session.campaign_goal_status == "started":
        session.campaign_goal_status = "in_progress"


def complete_campaign_goal(session: GameSession) -> None:
    ensure_campaign_goal(session)
    session.campaign_goal_status = "completed"


def serialize_campaign_goal(session: GameSession) -> dict[str, str]:
    return {
        "main_mission": _compact_public_text(session.campaign_goal_summary, 1200),
        "current_clue": _compact_public_text(session.campaign_current_clue, 1200),
        "status": (
            session.campaign_goal_status
            if session.campaign_goal_status in CAMPAIGN_GOAL_STATUSES
            else "started"
        ),
    }
