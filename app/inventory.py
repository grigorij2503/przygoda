from collections.abc import Iterable

from app.models import InventoryItem


EQUIPMENT_SLOT_LIMITS = {
    "hands": 2,
    "armor": 1,
    "active": 5,
}


def equipment_slot_group(item_type: str) -> str | None:
    """Mapuje typ przedmiotu na widoczny slot wyposażenia."""
    if item_type == "consumable":
        return None
    if item_type in {"weapon", "shield"}:
        return "hands"
    if item_type == "armor":
        return "armor"
    return "active"


def hands_used(item: InventoryItem) -> int:
    if item.item_type == "shield":
        return 1
    if item.item_type == "weapon":
        return 2 if item.hands_required == 2 else 1
    return 0


def get_effectively_equipped_items(items: Iterable[InventoryItem]) -> list[InventoryItem]:
    """Zwraca przedmioty mieszczące się w slotach, preferując najnowsze."""
    slot_counts = {slot: 0 for slot in EQUIPMENT_SLOT_LIMITS}
    equipped_items: list[InventoryItem] = []
    has_shield = False

    for item in sorted(items, key=lambda current: current.id or 0, reverse=True):
        if not item.is_equipped:
            continue

        slot_group = equipment_slot_group(item.item_type)
        if slot_group is None:
            continue
        if item.item_type == "shield" and has_shield:
            continue
        required_slots = hands_used(item) if slot_group == "hands" else 1
        if slot_counts[slot_group] + required_slots > EQUIPMENT_SLOT_LIMITS[slot_group]:
            continue

        equipped_items.append(item)
        slot_counts[slot_group] += required_slots
        has_shield = has_shield or item.item_type == "shield"

    return equipped_items
