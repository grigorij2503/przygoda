"""Server-owned post-battle market, prices and merchant interactions."""

import re
import secrets
import unicodedata

from fastapi import Depends, HTTPException, Request
from sqlalchemy import case, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Character, GameSession, InventoryItem, NamedLoreEntity
from app.schemas import MarketInteractionRequest, MarketTransactionRequest
from app.services.room_access import require_room
from app.services.runtime import require_gm
from app.services.world_service import get_session_world_pack
from app.websocket_manager import ws_manager
from app.worlds.models import WorldPack


MERCHANT_PERSONAS = (
    ("Mira", "wędrowna kupczyni"), ("Iwo", "karczmarz"),
    ("Nela", "handlarka"), ("Rin", "gospodarz postoju"),
    ("Oskar", "wędrowny kupiec"), ("Ada", "karczmarka"),
    ("Borys", "handlarz"), ("Sana", "gospodyni postoju"),
)
THEFT_STEMS = ("krad", "ukra", "skra", "wykrad", "zwin", "podkrad", "krasc")
THEFT_PHRASES = ("po cichu", "bez placenia", "do kieszeni", "niezauwazenie")


def _plain(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold()


def item_buy_value(item: InventoryItem | dict) -> int:
    field = item.get if isinstance(item, dict) else lambda key, default=None: getattr(item, key, default)
    if field("item_type") == "consumable":
        return max(4, min(24, 3 + max(0, int(field("stat_bonus") or 0)) // 4))
    bonus = min(5, max(0, int(field("stat_bonus") or 0)))
    power = min(9, max(0, int(field("damage_power") or 0)))
    base_power = 6 if int(field("hands_required") or 1) == 2 else 4
    extra = max(0, power - base_power) if field("item_type") == "weapon" else 0
    return 6 + 4 * bonus + 2 * extra


def item_sell_value(item: InventoryItem) -> int:
    return max(1, item_buy_value(item) * 3 // 10)


def open_market_visit(
    session: GameSession,
    characters: list[Character],
    pack: WorldPack,
    visit_turn: int,
    *,
    guaranteed: bool = False,
) -> dict | None:
    """Create one persisted offer set; never regenerate it on a session read."""
    state = build_market_visit(session.market_state or {}, characters, pack, visit_turn, guaranteed=guaranteed)
    session.market_state = state
    session.market_revision = int(session.market_revision or 0) + 1
    return state["merchant"]


def build_market_visit(
    old_state: dict,
    characters: list[Character],
    pack: WorldPack,
    visit_turn: int,
    *,
    guaranteed: bool = False,
) -> dict:
    merchant_appears = guaranteed or secrets.randbelow(100) < 60
    pending_ban = list(dict.fromkeys([*old_state.get("pending_ban", []), *old_state.get("caught", [])]))
    state: dict = {
        "visit_turn": visit_turn,
        "merchant": None,
        "offers": [],
        "banned": pending_ban if merchant_appears else [],
        "pending_ban": [] if merchant_appears else pending_ban,
        "caught": [],
        "negotiated": [],
        "discounts": {},
        "theft_attempted": [],
    }
    if merchant_appears:
        name, role = secrets.choice(MERCHANT_PERSONAS)
        state["merchant"] = {
            "name": name,
            "role": role,
            "greeting": f"{name}, {role}, rozkłada towary i zaprasza drużynę do obejrzenia oferty.",
        }
        living = [
            character for character in characters
            if character.is_alive and character.is_participating
        ]
        level = max((character.level for character in living), default=1)
        level_cap = min(5, 2 + max(0, level - 1) // 5)
        equipped_strength = [
            max((max(0, int(item.stat_bonus or 0)) for item in character.inventory if item.is_equipped), default=0)
            for character in living
        ]
        gear_baseline = sum(equipped_strength) // len(equipped_strength) if equipped_strength else 0
        offer_baseline = min(level_cap, max(1, level_cap - 1, gear_baseline))
        entries = [entry for table in pack.loot_tables for entry in table.entries]
        selected = secrets.SystemRandom().sample(entries, min(4, len(entries)))
        rarities = sorted(pack.loot_rarities, key=lambda rarity: rarity.rank)
        for index, entry in enumerate(selected, 1):
            rank = min(level_cap, offer_baseline + index % 2)
            rarity = max((r for r in rarities if r.rank <= rank), key=lambda r: r.rank)
            damage_power = 0
            if entry.item_type == "weapon":
                damage_power = (6 if entry.hands_required == 2 else 4) + min(3, max(0, rank - 1))
            offer = {
                "id": f"o{index}",
                "name": f"{entry.label} {rarity.suffix}",
                "description": entry.description,
                "item_type": entry.item_type,
                "target_stat": entry.target_stat,
                "stat_bonus": rank,
                "damage_power": damage_power,
                "hands_required": entry.hands_required,
                "stock": 1,
            }
            offer["price"] = item_buy_value(offer)
            state["offers"].append(offer)
        healing = min(
            pack.consumable_loot.healing_cap,
            pack.consumable_loot.base_healing
            + level * pack.consumable_loot.healing_per_level,
        )
        consumable = {
            "id": "o5",
            "name": pack.consumable_loot.name,
            "description": pack.consumable_loot.description_template.format(healing=healing),
            "item_type": "consumable",
            "target_stat": "none",
            "stat_bonus": healing,
            "damage_power": 0,
            "hands_required": 1,
            "stock": 2,
        }
        consumable["price"] = item_buy_value(consumable)
        state["offers"].append(consumable)
    return state


def serialize_market(session: GameSession) -> dict | None:
    state = session.market_state or {}
    if session.status != "in_progress" or state.get("visit_turn") != session.current_turn_number:
        return None
    return {
        "merchant": state.get("merchant"),
        "offers": state.get("offers", []),
        "banned": state.get("banned", []),
        "negotiated": state.get("negotiated", []),
        "discounts": state.get("discounts", {}),
        "workshop_available": int(session.crafting_available_until_turn or 0) == session.current_turn_number,
    }


async def _load_visit(db: AsyncSession, character_id: int) -> tuple[GameSession, Character, dict]:
    character = (await db.execute(select(Character).where(Character.id == character_id))).scalar_one_or_none()
    if not character:
        raise HTTPException(status_code=404, detail="Postać nie istnieje")
    session = (await db.execute(select(GameSession).where(GameSession.id == character.session_id))).scalar_one()
    state = dict(session.market_state or {})
    if (session.status != "in_progress" or session.is_turn_resolving or state.get("visit_turn") != session.current_turn_number):
        raise HTTPException(status_code=409, detail="Postój nie jest teraz dostępny")
    if session.active_boss_name and (session.active_boss_hp or 0) > 0:
        raise HTTPException(status_code=409, detail="Nie można handlować podczas walki")
    if not character.is_alive or not character.is_participating:
        raise HTTPException(status_code=400, detail="Ta postać nie może teraz handlować")
    if not state.get("merchant"):
        raise HTTPException(status_code=409, detail="Podczas tego postoju nie ma handlarza")
    if character.id in state.get("banned", []):
        raise HTTPException(status_code=403, detail="Handlarz odmawia obsługi tej postaci")
    return session, character, state


def _offer(state: dict, offer_id: str | None) -> dict:
    offer = next((item for item in state.get("offers", []) if item["id"] == offer_id), None)
    if not offer or offer["stock"] < 1:
        raise HTTPException(status_code=409, detail="Ten przedmiot nie jest już dostępny")
    return offer


async def _commit_state(db: AsyncSession, session: GameSession, state: dict) -> None:
    revision = int(session.market_revision or 0)
    result = await db.execute(
        update(GameSession)
        .where(
            GameSession.id == session.id,
            GameSession.market_revision == revision,
            GameSession.current_turn_number == state["visit_turn"],
            GameSession.is_turn_resolving.is_(False),
            GameSession.status == "in_progress",
        )
        .values(market_state=state, market_revision=revision + 1)
    )
    if result.rowcount != 1:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Oferta się zmieniła. Odśwież postój.")
    await db.commit()
    await ws_manager.broadcast_to_session(session.id, {"type": "MARKET_UPDATED"})


def _new_item(character_id: int, offer: dict) -> InventoryItem:
    return InventoryItem(
        character_id=character_id,
        name=offer["name"],
        description=offer["description"],
        item_type=offer["item_type"],
        target_stat=offer["target_stat"],
        stat_bonus=offer["stat_bonus"],
        damage_power=offer["damage_power"],
        hands_required=offer["hands_required"],
        is_equipped=False,
        quantity=1,
    )


async def transact(
    payload: MarketTransactionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    session, character, state = await _load_visit(db, payload.character_id)
    require_room(request, session.room_code)
    if payload.operation in {"buy", "haggle"}:
        offer = _offer(state, payload.offer_id)
        if payload.operation == "haggle":
            if character.id in state.get("negotiated", []):
                raise HTTPException(status_code=409, detail="Ta postać już negocjowała podczas postoju")
            raw = secrets.randbelow(20) + 1
            total = raw + int(character.charisma or 0)
            dc = 14 + min(5, int(offer["stat_bonus"] or 0))
            success = total >= dc
            state["negotiated"] = [*state.get("negotiated", []), character.id]
            if success:
                state["discounts"] = {**state.get("discounts", {}), str(character.id): {"offer_id": offer["id"], "percent": 15}}
            await _commit_state(db, session, state)
            return {"success": success, "roll": raw, "total": total, "dc": dc, "discount_percent": 15 if success else 0}
        discount = state.get("discounts", {}).get(str(character.id), {})
        price = int(offer["price"])
        if discount.get("offer_id") == offer["id"]:
            price = max(1, (price * (100 - int(discount["percent"])) + 99) // 100)
        debit = await db.execute(
            update(Character)
            .where(Character.id == character.id, Character.coins >= price)
            .values(coins=Character.coins - price)
        )
        if debit.rowcount != 1:
            await db.rollback()
            raise HTTPException(status_code=400, detail="Za mało środków na zakup")
        db.add(_new_item(character.id, offer))
        offer["stock"] -= 1
        if discount.get("offer_id") == offer["id"]:
            state["discounts"] = {key: value for key, value in state["discounts"].items() if key != str(character.id)}
        await _commit_state(db, session, state)
        return {"success": True, "item_name": offer["name"], "coins_delta": -price}

    item = (await db.execute(select(InventoryItem).where(
        InventoryItem.id == payload.item_id,
        InventoryItem.character_id == character.id,
    ))).scalar_one_or_none()
    if not item or item.is_equipped or int(item.quantity or 0) < 1:
        raise HTTPException(status_code=400, detail="Można sprzedać tylko przedmiot z plecaka")
    price = item_sell_value(item)
    name = item.name
    quantity = int(item.quantity)
    if quantity == 1:
        changed = await db.execute(delete(InventoryItem).where(
            InventoryItem.id == item.id,
            InventoryItem.character_id == character.id,
            InventoryItem.is_equipped.is_(False),
            InventoryItem.quantity == 1,
        ))
    else:
        changed = await db.execute(update(InventoryItem).where(
            InventoryItem.id == item.id,
            InventoryItem.character_id == character.id,
            InventoryItem.is_equipped.is_(False),
            InventoryItem.quantity == quantity,
        ).values(quantity=quantity - 1))
    if changed.rowcount != 1:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Stan plecaka się zmienił")
    await db.execute(update(Character).where(Character.id == character.id).values(coins=Character.coins + price))
    await _commit_state(db, session, state)
    return {"success": True, "item_name": name, "coins_delta": price}


async def interact(
    payload: MarketInteractionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    session, character, state = await _load_visit(db, payload.character_id)
    require_room(request, session.room_code)
    normalized = _plain(payload.text)
    words = re.findall(r"[a-z0-9]+", normalized)
    stealing = any(word.startswith(stem) for word in words for stem in THEFT_STEMS) or any(
        phrase in normalized for phrase in THEFT_PHRASES
    )
    if not stealing:
        return {"success": True, "message": f"{state['merchant']['name']} pokazuje dostępne towary i słucha propozycji."}
    if character.id in state.get("theft_attempted", []):
        raise HTTPException(status_code=409, detail="Ta postać wykorzystała już swoją próbę podczas postoju")
    matches = [offer for offer in state["offers"] if offer["stock"] > 0 and _plain(offer["name"]) in normalized]
    if len(matches) != 1:
        raise HTTPException(status_code=400, detail="W opisie wskaż dokładną nazwę jednego dostępnego przedmiotu")
    offer = matches[0]
    raw = secrets.randbelow(20) + 1
    total = raw + int(character.agility or 0)
    dc = 21 + min(5, int(offer["stat_bonus"] or 0)) + max(0, int(character.level or 1) - 1) // 4
    success = raw == 20 or total >= dc
    state["theft_attempted"] = [*state.get("theft_attempted", []), character.id]
    if success:
        offer["stock"] -= 1
        db.add(_new_item(character.id, offer))
        message = f"Udało się zabrać {offer['name']} bez zwrócenia uwagi handlarza."
        fine = 0
    else:
        fine = max(2, (int(offer["price"]) + 1) // 2)
        charged = min(int(character.coins or 0), fine)
        await db.execute(update(Character).where(Character.id == character.id).values(
            coins=case((Character.coins >= fine, Character.coins - fine), else_=0)
        ))
        state["caught"] = [*state.get("caught", []), character.id]
        state["banned"] = [*state.get("banned", []), character.id]
        fine_text = f"Zabiera {charged} środków" if charged else "Nie znajduje środków do odebrania"
        message = f"{state['merchant']['name']} przyłapuje {character.name}. {fine_text} i odmawia dalszego handlu; wieść dotrze też do kolejnego handlarza."
        lore = (await db.execute(select(NamedLoreEntity).where(
            NamedLoreEntity.session_id == session.id,
            NamedLoreEntity.category == "npc",
            NamedLoreEntity.custom_name == state["merchant"]["name"],
        ).order_by(NamedLoreEntity.id.desc()).limit(1))).scalar_one_or_none()
        if lore:
            lore.npc_disposition = "rough"
            lore.npc_goal = f"Pamięta próbę kradzieży postaci {character.name}."
    await _commit_state(db, session, state)
    return {"success": success, "message": message, "roll": raw, "total": total, "dc": dc, "coins_lost": 0 if success else charged}


async def open_post_manually(
    request: Request,
    room_code: str = "kampania-1",
    db: AsyncSession = Depends(get_db),
) -> dict:
    require_room(request, room_code)
    require_gm(request)
    session = (await db.execute(
        select(GameSession).options(selectinload(GameSession.campaign_map)).where(GameSession.room_code == room_code)
    )).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Sesja nie istnieje")
    if session.status != "in_progress" or session.is_turn_resolving or (session.active_boss_hp or 0) > 0:
        raise HTTPException(status_code=409, detail="Postój można otworzyć tylko między starciami w trwającej kampanii")
    if ((session.market_state or {}).get("visit_turn") == session.current_turn_number
            and (session.market_state or {}).get("merchant")):
        raise HTTPException(status_code=409, detail="Postój jest już otwarty w tej turze")
    characters = (await db.execute(
        select(Character).options(selectinload(Character.inventory)).where(Character.session_id == session.id)
    )).scalars().all()
    state = build_market_visit(
        session.market_state or {}, list(characters), get_session_world_pack(session),
        session.current_turn_number, guaranteed=True,
    )
    revision = int(session.market_revision or 0)
    changed = await db.execute(
        update(GameSession).where(
            GameSession.id == session.id,
            GameSession.market_revision == revision,
            GameSession.current_turn_number == session.current_turn_number,
            GameSession.is_turn_resolving.is_(False),
            GameSession.status == "in_progress",
        ).values(
            market_state=state,
            market_revision=revision + 1,
            crafting_available_until_turn=session.current_turn_number,
        )
    )
    if changed.rowcount != 1:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Stan kampanii się zmienił. Odśwież postój.")
    merchant = state["merchant"]
    known_merchant = (await db.execute(select(NamedLoreEntity.id).where(
        NamedLoreEntity.session_id == session.id,
        NamedLoreEntity.category == "npc",
        NamedLoreEntity.custom_name == merchant["name"],
    ).limit(1))).scalar_one_or_none()
    if known_merchant is None:
        db.add(NamedLoreEntity(
            session_id=session.id,
            category="npc",
            original_description=merchant["greeting"],
            custom_name=merchant["name"],
            discovered_turn_number=session.current_turn_number,
            map_node_id=session.campaign_map.current_node_id if session.campaign_map else None,
            npc_disposition="reserved",
            npc_goal="Handluje podczas postoju drużyny.",
        ))
    await db.commit()
    await ws_manager.broadcast_to_session(session.id, {"type": "MARKET_UPDATED"})
    return {"success": True, "merchant": merchant}
