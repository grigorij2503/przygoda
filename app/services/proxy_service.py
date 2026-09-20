from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Character, ProxyActionDecision, ProxyActionVote, Turn
from app.schemas import ProxyActionVoteRequest
from app.services.runtime import (
    PROXY_ACTION_VOTE_WINDOW,
    PROXY_ACTION_WAIT,
    as_utc,
    build_proxy_action_options,
    finalize_proxy_decision,
    serialize_proxy_decision,
)
from app.websocket_manager import ws_manager


async def vote_for_proxy_action(
    target_character_id: int,
    payload: ProxyActionVoteRequest,
    db: AsyncSession = Depends(get_db),
):
    target_stmt = (
        select(Character)
        .options(selectinload(Character.session))
        .where(Character.id == target_character_id)
    )
    target = (await db.execute(target_stmt)).scalar_one_or_none()
    if not target or not target.is_alive:
        raise HTTPException(status_code=404, detail="Nie znaleziono aktywnej postaci")

    session = target.session
    if session.status == "completed":
        raise HTTPException(status_code=409, detail="Kampania została zakończona")
    if session.is_turn_resolving:
        raise HTTPException(status_code=400, detail="Tura jest już rozstrzygana")

    turn_stmt = (
        select(Turn)
        .options(
            selectinload(Turn.actions),
            selectinload(Turn.proxy_decisions).selectinload(ProxyActionDecision.votes),
        )
        .where(Turn.session_id == session.id, Turn.turn_number == session.current_turn_number)
        .with_for_update()
    )
    turn = (await db.execute(turn_stmt)).scalar_one_or_none()
    if not turn or turn.status != "waiting_for_actions" or turn.mechanics_resolved_at is not None:
        raise HTTPException(status_code=400, detail="Brak aktywnej tury oczekującej na akcje")

    existing_action = next(
        (action for action in turn.actions if action.character_id == target_character_id),
        None,
    )
    if existing_action:
        raise HTTPException(status_code=409, detail="Ta postać ma już zadeklarowaną akcję")

    now = datetime.now(timezone.utc)
    available_at = (as_utc(turn.created_at) or now) + PROXY_ACTION_WAIT
    if now < available_at:
        raise HTTPException(
            status_code=400,
            detail=f"Głosowanie będzie dostępne od {available_at.isoformat()}",
        )

    alive_characters = (
        await db.execute(
            select(Character).where(Character.session_id == session.id, Character.is_alive == True)
        )
    ).scalars().all()
    alive_character_ids = {character.id for character in alive_characters}
    if len(alive_character_ids) < 2:
        raise HTTPException(status_code=400, detail="Brak innych graczy uprawnionych do głosowania")
    if payload.voter_character_id == target_character_id:
        raise HTTPException(status_code=400, detail="Nie można głosować za własną postać")
    if payload.voter_character_id not in alive_character_ids:
        raise HTTPException(status_code=403, detail="Głosować może tylko żywa postać z tej sesji")
    if not any(
        action.character_id == payload.voter_character_id and action.submission_source == "player"
        for action in turn.actions
    ):
        raise HTTPException(status_code=400, detail="Najpierw złóż własną akcję w tej turze")

    decision = next(
        (item for item in turn.proxy_decisions if item.target_character_id == target_character_id),
        None,
    )
    if not decision:
        decision = ProxyActionDecision(
            turn_id=turn.id,
            target_character_id=target_character_id,
            options=build_proxy_action_options(session, target),
            status="open",
            opened_at=now,
            closes_at=now + PROXY_ACTION_VOTE_WINDOW,
            votes=[],
        )
        db.add(decision)
        turn.proxy_decisions.append(decision)
        await db.flush()
    if decision.status != "open":
        raise HTTPException(status_code=409, detail="To głosowanie zostało już zakończone")

    if now >= (as_utc(decision.closes_at) or now):
        finalized = finalize_proxy_decision(db, decision, turn, alive_character_ids, now)
        await db.commit()
        if finalized:
            await ws_manager.broadcast_to_session(session.id, {
                "type": "PROXY_ACTION_FINALIZED",
                **finalized,
                "target_character_name": target.name,
            })
        return {
            "success": True,
            "finalized": bool(finalized),
            "decision": serialize_proxy_decision(decision, alive_character_ids),
        }

    valid_option_ids = {str(option.get("id")) for option in (decision.options or [])}
    if payload.option_id not in valid_option_ids:
        raise HTTPException(status_code=400, detail="Nieprawidłowa opcja akcji zastępczej")

    vote = next(
        (item for item in decision.votes if item.voter_character_id == payload.voter_character_id),
        None,
    )
    if vote:
        vote.option_id = payload.option_id
        vote.updated_at = now
    else:
        vote = ProxyActionVote(
            decision_id=decision.id,
            voter_character_id=payload.voter_character_id,
            option_id=payload.option_id,
            created_at=now,
            updated_at=now,
        )
        db.add(vote)
        decision.votes.append(vote)

    finalized = finalize_proxy_decision(db, decision, turn, alive_character_ids, now)
    await db.commit()

    await ws_manager.broadcast_to_session(session.id, {
        "type": "PROXY_ACTION_VOTE_UPDATED",
        "target_character_id": target.id,
        "target_character_name": target.name,
    })
    if finalized:
        await ws_manager.broadcast_to_session(session.id, {
            "type": "PROXY_ACTION_FINALIZED",
            **finalized,
            "target_character_name": target.name,
        })

    return {
        "success": True,
        "finalized": bool(finalized),
        "decision": serialize_proxy_decision(decision, alive_character_ids),
    }
