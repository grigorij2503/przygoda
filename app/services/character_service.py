from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.inventory import EQUIPMENT_SLOT_LIMITS, equipment_slot_group, hands_used
from app.models import Character, GameSession, InventoryItem, WebPushSubscription
from app.schemas import (
    CreateCharacterRequest,
    SpendStatPointRequest,
    TransferInventoryItemRequest,
    UpdatePersonalNoteRequest,
)
from app.services.runtime import MAX_BASE_ATTRIBUTE
from app.services.room_access import require_room
from app.services.world_service import get_session_world_pack
from app.worlds.registry import WORLD_PACK_REGISTRY, WorldPackNotFoundError
from app.websocket_manager import ws_manager


async def toggle_character_ready(character_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Character).where(Character.id == character_id)
    char = (await db.execute(stmt)).scalar_one_or_none()
    if not char:
        raise HTTPException(status_code=404, detail="Postać nie została znaleziona")

    char.is_ready = not bool(char.is_ready)
    await db.commit()

    await ws_manager.broadcast_to_session(char.session_id, {
        "type": "CHARACTER_READY_TOGGLED",
        "character_id": char.id,
        "character_name": char.name,
        "is_ready": char.is_ready
    })

    return {"success": True, "character_id": char.id, "is_ready": char.is_ready}

async def create_character(
    payload: CreateCharacterRequest,
    room_code: str = "kampania-1",
    db: AsyncSession = Depends(get_db)
):
    stmt = select(GameSession).where(GameSession.room_code == room_code)
    res = await db.execute(stmt)
    session = res.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Sesja nie istnieje")

    # Walidacja sumy punktów (np. 4 punkty do rozdania)
    total_stats = (
        payload.strength
        + payload.agility
        + payload.intellect
        + payload.charisma
        + payload.perception
    )
    if total_stats > 5:
        raise HTTPException(status_code=400, detail="Maksymalna suma punktów atrybutów to 4 lub 5")

    world_pack = get_session_world_pack(session)
    try:
        class_definition = (
            WORLD_PACK_REGISTRY.get_class(world_pack, payload.class_id)
            if payload.class_id
            else WORLD_PACK_REGISTRY.resolve_class(
                world_pack, payload.character_class, fallback=False
            )
        )
    except WorldPackNotFoundError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    max_hp = 20 + (payload.strength * 5)
    char = Character(
        session_id=session.id,
        player_name=payload.player_name.strip(),
        name=payload.name.strip(),
        character_class=class_definition.name,
        class_id=class_definition.id,
        level=1,
        xp=0,
        current_hp=max_hp,
        max_hp=max_hp,
        strength=payload.strength,
        agility=payload.agility,
        intellect=payload.intellect,
        charisma=payload.charisma,
        perception=payload.perception,
        is_alive=True,
        death_state="alive",
        death_failures=0,
        is_ready=False,
    )
    db.add(char)
    await db.commit()
    await db.refresh(char)

    # Startery są rozwiązywane z wersji świata przypiętej do kampanii.
    starter_items = [
        InventoryItem(
            character_id=char.id,
            **item_definition.model_dump(),
        )
        for item_definition in class_definition.starter_items
    ]

    for it in starter_items:
        db.add(it)
    await db.commit()

    # Powiadom innych graczy przez WebSocket
    await ws_manager.broadcast_to_session(session.id, {
        "type": "CHARACTER_CREATED",
        "character": {
            "id": char.id,
            "name": char.name,
            "player_name": char.player_name,
            "character_class": char.character_class,
            "class_id": char.class_id,
        }
    })

    return {"success": True, "character_id": char.id}

async def spend_stat_point(
    char_id: int,
    payload: SpendStatPointRequest,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Character).where(Character.id == char_id)
    char = (await db.execute(stmt)).scalar_one_or_none()
    if not char:
        raise HTTPException(status_code=404, detail="Postać nie istnieje")

    stat_column = getattr(Character, payload.stat)
    if getattr(char, payload.stat) >= MAX_BASE_ATTRIBUTE:
        raise HTTPException(
            status_code=400,
            detail=f"Atrybut osiągnął maksymalną wartość +{MAX_BASE_ATTRIBUTE}",
        )

    update_stmt = (
        update(Character)
        .where(
            Character.id == char_id,
            Character.unspent_stat_points > 0,
            stat_column < MAX_BASE_ATTRIBUTE,
        )
        .values({
            stat_column: stat_column + 1,
            Character.unspent_stat_points: Character.unspent_stat_points - 1,
        })
    )
    result = await db.execute(update_stmt)
    if result.rowcount != 1:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Postać nie ma punktów atrybutów do rozdania")

    await db.commit()
    await db.refresh(char)

    await ws_manager.broadcast_to_session(char.session_id, {
        "type": "STAT_POINT_SPENT",
        "character_id": char.id,
        "character_name": char.name,
        "stat": payload.stat,
        "stat_value": getattr(char, payload.stat),
        "unspent_stat_points": char.unspent_stat_points,
    })

    return {
        "success": True,
        "stat": payload.stat,
        "stat_value": getattr(char, payload.stat),
        "unspent_stat_points": char.unspent_stat_points,
    }

async def delete_character(char_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Character).where(Character.id == char_id)
    res = await db.execute(stmt)
    char = res.scalar_one_or_none()
    if not char:
        raise HTTPException(status_code=404, detail="Postać nie istnieje")

    session_id = char.session_id
    char_name = char.name

    # Usuń dane zależne również w SQLite bez włączonego ON DELETE CASCADE.
    await db.execute(delete(InventoryItem).where(InventoryItem.character_id == char_id))
    await db.execute(
        delete(WebPushSubscription).where(WebPushSubscription.character_id == char_id)
    )

    # Usuń postać
    await db.delete(char)
    await db.commit()

    # Powiadom innych graczy
    await ws_manager.broadcast_to_session(session_id, {
        "type": "CHARACTER_DELETED",
        "character_id": char_id,
        "character_name": char_name,
    })

    return {"success": True, "message": f"Postać {char_name} została usunięta"}

async def get_personal_note(char_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Character).where(Character.id == char_id)
    res = await db.execute(stmt)
    char = res.scalar_one_or_none()
    if not char:
        raise HTTPException(status_code=404, detail="Postać nie istnieje")

    return {"content": char.personal_note or ""}

async def update_personal_note(
    char_id: int,
    payload: UpdatePersonalNoteRequest,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Character).where(Character.id == char_id)
    res = await db.execute(stmt)
    char = res.scalar_one_or_none()
    if not char:
        raise HTTPException(status_code=404, detail="Postać nie istnieje")

    char.personal_note = payload.content
    await db.commit()
    return {"success": True, "content": char.personal_note}

async def toggle_equip_item(char_id: int, item_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(InventoryItem).where(InventoryItem.id == item_id, InventoryItem.character_id == char_id)
    res = await db.execute(stmt)
    item = res.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Przedmiot nie znaleziony")

    slot_group = equipment_slot_group(item.item_type)
    if slot_group is None:
        raise HTTPException(status_code=400, detail="Przedmiotów zużywalnych nie zakłada się w slotach")

    replaced_item_names = []
    if item.is_equipped:
        item.is_equipped = False
    else:
        equipped_items = (
            await db.execute(
                select(InventoryItem).where(
                    InventoryItem.character_id == char_id,
                    InventoryItem.is_equipped.is_(True),
                )
            )
        ).scalars().all()

        items_in_slot = [
            equipped
            for equipped in equipped_items
            if equipment_slot_group(equipped.item_type) == slot_group
        ]
        if slot_group == "active" and len(items_in_slot) >= EQUIPMENT_SLOT_LIMITS[slot_group]:
            raise HTTPException(
                status_code=400,
                detail="Wszystkie 5 slotów aktywnych przedmiotów jest zajętych. Najpierw zdejmij jeden z nich.",
            )

        if slot_group in {"armor", "helmet", "boots"}:
            for equipped in items_in_slot:
                equipped.is_equipped = False
                replaced_item_names.append(equipped.name)

        if slot_group == "hands":
            required_hands = hands_used(item)
            two_handed_items = [equipped for equipped in items_in_slot if hands_used(equipped) == 2]
            equipped_shields = [equipped for equipped in items_in_slot if equipped.item_type == "shield"]

            if required_hands == 2:
                for equipped in items_in_slot:
                    equipped.is_equipped = False
                    replaced_item_names.append(equipped.name)
            elif two_handed_items:
                for equipped in two_handed_items:
                    equipped.is_equipped = False
                    replaced_item_names.append(equipped.name)
            elif item.item_type == "shield" and equipped_shields:
                for equipped in equipped_shields:
                    equipped.is_equipped = False
                    replaced_item_names.append(equipped.name)
            elif sum(hands_used(equipped) for equipped in items_in_slot) >= EQUIPMENT_SLOT_LIMITS[slot_group]:
                raise HTTPException(
                    status_code=400,
                    detail="Obie dłonie są zajęte. Najpierw odłóż jedną z broni albo tarczę.",
                )

        item.is_equipped = True

    await db.commit()
    return {
        "success": True,
        "item_name": item.name,
        "is_equipped": item.is_equipped,
        "slot_group": slot_group,
        "replaced_item_names": replaced_item_names,
    }


async def transfer_inventory_item(
    char_id: int,
    item_id: int,
    payload: TransferInventoryItemRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    require_room(request)
    sender = (await db.execute(select(Character).where(Character.id == char_id))).scalar_one_or_none()
    recipient = (
        await db.execute(
            select(Character).where(Character.id == payload.recipient_character_id)
        )
    ).scalar_one_or_none()
    if not sender or not recipient or sender.session_id != recipient.session_id:
        raise HTTPException(status_code=404, detail="Postacie muszą należeć do tej samej kampanii")
    if sender.id == recipient.id:
        raise HTTPException(status_code=400, detail="Wybierz inną postać")
    if not sender.is_alive or not recipient.is_alive:
        raise HTTPException(status_code=400, detail="Przekaz wymaga dwóch żyjących postaci")
    session = (
        await db.execute(select(GameSession).where(GameSession.id == sender.session_id))
    ).scalar_one()
    if session.is_turn_resolving:
        raise HTTPException(status_code=409, detail="Poczekaj na rozstrzygnięcie tury")

    item = (
        await db.execute(
            select(InventoryItem).where(
                InventoryItem.id == item_id,
                InventoryItem.character_id == sender.id,
            )
        )
    ).scalar_one_or_none()
    if not item or item.is_equipped:
        raise HTTPException(status_code=400, detail="Można przekazać tylko przedmiot z plecaka")
    available = int(item.quantity or 0)
    if payload.quantity > available:
        raise HTTPException(status_code=400, detail="W plecaku nie ma tylu sztuk")

    item_name = item.name
    if payload.quantity == available:
        result = await db.execute(
            update(InventoryItem)
            .where(
                InventoryItem.id == item.id,
                InventoryItem.character_id == sender.id,
                InventoryItem.is_equipped.is_(False),
                InventoryItem.quantity == available,
            )
            .values(character_id=recipient.id)
        )
    else:
        result = await db.execute(
            update(InventoryItem)
            .where(
                InventoryItem.id == item.id,
                InventoryItem.character_id == sender.id,
                InventoryItem.is_equipped.is_(False),
                InventoryItem.quantity == available,
            )
            .values(quantity=available - payload.quantity)
        )
        if result.rowcount == 1:
            db.add(InventoryItem(
                character_id=recipient.id,
                name=item.name,
                description=item.description,
                item_type=item.item_type,
                target_stat=item.target_stat,
                stat_bonus=item.stat_bonus,
                damage_power=item.damage_power,
                hands_required=item.hands_required,
                is_equipped=False,
                quantity=payload.quantity,
            ))
    if result.rowcount != 1:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Stan przedmiotu się zmienił. Odśwież plecak.")
    await db.commit()
    await ws_manager.broadcast_to_session(sender.session_id, {
        "type": "INVENTORY_TRANSFERRED",
        "sender_character_id": sender.id,
        "recipient_character_id": recipient.id,
        "sender_name": sender.name,
        "recipient_name": recipient.name,
        "item_name": item_name,
        "quantity": payload.quantity,
    })
    return {"success": True, "item_name": item_name, "quantity": payload.quantity}

async def use_consumable_item(char_id: int, item_id: int, db: AsyncSession = Depends(get_db)):
    c_stmt = select(Character).where(Character.id == char_id)
    c_res = await db.execute(c_stmt)
    char = c_res.scalar_one_or_none()

    i_stmt = select(InventoryItem).where(InventoryItem.id == item_id, InventoryItem.character_id == char_id)
    i_res = await db.execute(i_stmt)
    item = i_res.scalar_one_or_none()

    if not char or not item:
        raise HTTPException(status_code=404, detail="Nie znaleziono postaci lub przedmiotu")

    if item.item_type != "consumable":
        raise HTTPException(status_code=400, detail="Ten przedmiot nie jest zdatny do spożycia/użycia")
    if not char.is_alive:
        raise HTTPException(status_code=400, detail="Nieprzytomna lub martwa postać nie może używać przedmiotów.")

    # Ulecz
    heal_amount = item.stat_bonus or 10
    char.current_hp = min(char.max_hp, char.current_hp + heal_amount)

    # Zmniejsz ilość lub usuń
    if item.quantity > 1:
        item.quantity -= 1
    else:
        await db.delete(item)

    await db.commit()
    return {"success": True, "new_hp": char.current_hp, "healed_by": heal_amount}
