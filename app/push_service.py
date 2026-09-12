import asyncio
import json
import logging
from collections.abc import Iterable

from pywebpush import WebPushException, webpush_async
from sqlalchemy import delete, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import WebPushSubscription

logger = logging.getLogger("ttrpg.push")

_push_tasks: set[asyncio.Task] = set()


def is_web_push_configured() -> bool:
    return bool(
        settings.VAPID_PUBLIC_KEY.strip()
        and settings.VAPID_PRIVATE_KEY.strip()
        and settings.VAPID_SUBJECT.strip()
    )


def schedule_web_push(
    session_id: int,
    *,
    title: str,
    body: str,
    tag: str,
    character_ids: Iterable[int] | None = None,
    url: str = "/",
) -> None:
    if not is_web_push_configured():
        return

    task = asyncio.create_task(
        send_web_push(
            session_id,
            title=title,
            body=body,
            tag=tag,
            character_ids=character_ids,
            url=url,
        )
    )
    _push_tasks.add(task)
    task.add_done_callback(_push_task_finished)


def _push_task_finished(task: asyncio.Task) -> None:
    _push_tasks.discard(task)
    try:
        task.result()
    except Exception:
        logger.exception("Nieoczekiwany błąd zadania Web Push")


async def send_web_push(
    session_id: int,
    *,
    title: str,
    body: str,
    tag: str,
    character_ids: Iterable[int] | None = None,
    url: str = "/",
) -> None:
    if not is_web_push_configured():
        return

    async with AsyncSessionLocal() as db:
        query = select(WebPushSubscription).where(WebPushSubscription.session_id == session_id)
        if character_ids is not None:
            target_ids = set(character_ids)
            if not target_ids:
                return
            query = query.where(WebPushSubscription.character_id.in_(target_ids))
        rows = (await db.execute(query)).scalars().all()
        subscriptions = [
            {
                "endpoint": row.endpoint,
                "keys": {"p256dh": row.p256dh, "auth": row.auth},
            }
            for row in rows
        ]

    if not subscriptions:
        return

    data = json.dumps(
        {"title": title, "body": body, "tag": tag, "url": url},
        ensure_ascii=False,
    )
    expired_endpoints: list[str] = []

    async def send_one(subscription: dict) -> None:
        try:
            await webpush_async(
                subscription_info=subscription,
                data=data,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_SUBJECT},
                ttl=5 * 60,
                headers={"Urgency": "high"},
            )
        except WebPushException as exc:
            response = exc.response
            response_status = getattr(response, "status", None) or getattr(response, "status_code", None)
            if response_status in {404, 410}:
                expired_endpoints.append(subscription["endpoint"])
            else:
                logger.warning("Nie udało się wysłać Web Push: %s", exc)
        except Exception:
            logger.exception("Nie udało się wysłać Web Push")

    await asyncio.gather(*(send_one(subscription) for subscription in subscriptions))

    if expired_endpoints:
        async with AsyncSessionLocal() as db:
            await db.execute(
                delete(WebPushSubscription).where(
                    WebPushSubscription.endpoint.in_(expired_endpoints)
                )
            )
            await db.commit()
