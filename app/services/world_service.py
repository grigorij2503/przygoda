"""Read-only world catalog service."""

from fastapi import HTTPException

from app.models import GameSession
from app.worlds.models import WorldCatalogResponse, WorldPack
from app.worlds.registry import WORLD_PACK_REGISTRY, WorldPackNotFoundError


async def get_world_catalog() -> WorldCatalogResponse:
    return WORLD_PACK_REGISTRY.catalog()


def serialize_world_runtime(pack: WorldPack) -> dict:
    """Return the declarative subset consumed by the generic frontend."""
    return {
        "id": pack.id,
        "version": pack.version,
        "key": pack.key,
        "display_name": pack.display_name,
        "ruleset_id": pack.ruleset_id,
        "theme_id": pack.theme_id,
        "theme": pack.theme.model_dump(mode="json"),
        "terminology": pack.terminology.model_dump(mode="json"),
        "attributes": [attribute.model_dump(mode="json") for attribute in pack.attributes],
        "action_stat_cues": [
            cue.model_dump(mode="json") for cue in pack.action_stat_cues
        ],
        "classes": [
            {
                "id": class_definition.id,
                "name": class_definition.name,
                "icon": class_definition.icon,
                "primary_stat": class_definition.primary_stat,
                "starter_items": [
                    item.model_dump(mode="json")
                    for item in class_definition.starter_items
                ],
                "quick_actions": [
                    action.model_dump(mode="json")
                    for action in class_definition.quick_actions
                ],
                "ability_book_title": (
                    class_definition.ability_book.title
                    if class_definition.ability_book
                    else None
                ),
            }
            for class_definition in pack.classes
        ],
        "enemy_profile": pack.enemy_profile.model_dump(mode="json"),
        "map_room_icons": {
            room.id: room.icon for room in pack.map_profile.room_types if room.icon
        },
        "loot_search_action": (
            pack.narrative_profile.loot_search_action.model_dump(mode="json")
        ),
        "scenario_options": list(pack.narrative_profile.scenario_options),
        "setting_theme": pack.narrative_profile.setting_theme,
        "ui_copy": {
            "lobby_empty_message": pack.narrative_profile.lobby_empty_message,
            "lobby_ready_message": pack.narrative_profile.lobby_ready_message,
            "character_selection_heading": pack.narrative_profile.character_selection_heading,
            "first_character_message": pack.narrative_profile.first_character_message,
            "lobby_create_first_message": pack.narrative_profile.lobby_create_first_message,
        },
        "ability_action_phrases": list(dict.fromkeys(
            phrase for phrase in (
                *(
                    marker
                    for class_definition in pack.classes
                    if class_definition.ability_book
                    for marker in class_definition.ability_book.action_markers
                ),
                *(
                    phrase
                    for ability in pack.abilities
                    for phrase in (ability.name, *ability.aliases)
                ),
            )
        )),
        "lore_categories": [
            category.model_dump(mode="json") for category in pack.lore_categories
        ],
    }


def get_session_world_pack(session: GameSession) -> WorldPack:
    return WORLD_PACK_REGISTRY.get(
        getattr(session, "world_pack_id", None),
        getattr(session, "world_pack_version", None),
    )


def resolve_requested_world_pack(
    session: GameSession,
    world_pack_id: str | None,
    world_pack_version: int | None,
    *,
    allow_new_campaign_reset: bool = False,
) -> WorldPack:
    current_pack = get_session_world_pack(session)
    if world_pack_id is None and world_pack_version is None:
        return current_pack
    requested_key = f"{world_pack_id}@{world_pack_version}"
    if requested_key != current_pack.key and not allow_new_campaign_reset and (
        bool(getattr(session, "characters", []))
        or int(getattr(session, "current_turn_number", 1) or 1) > 1
    ):
        raise HTTPException(
            status_code=409,
            detail="Nie można zmienić świata aktywnej kampanii. Utwórz nową pustą kampanię.",
        )
    try:
        return WORLD_PACK_REGISTRY.get(world_pack_id, world_pack_version)
    except WorldPackNotFoundError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
