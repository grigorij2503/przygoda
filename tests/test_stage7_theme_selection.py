"""Theme contracts and explicit new-campaign world selection."""

from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.models import GameSession
from app.services import world_service
from app.worlds.models import WorldPack
from app.worlds.registry import WORLD_PACK_REGISTRY, WorldPackRegistry


def trial_registry() -> WorldPackRegistry:
    payload = WORLD_PACK_REGISTRY.default.model_dump(mode="json")
    payload["id"] = "theme_trial"
    payload["version"] = 1
    payload["display_name"] = "Świat próbny"
    payload["theme_id"] = "neon_trial"
    payload["theme"]["id"] = "neon_trial"
    payload["theme"]["typography_id"] = "modern"
    payload["theme"]["texture_id"] = "grid"
    payload["theme"]["icon_set_id"] = "neutral"
    payload["narrative_profile"]["scenario_options"] = ["Miasto próbne"]
    trial = WorldPack.model_validate(payload)
    return WorldPackRegistry(
        (WORLD_PACK_REGISTRY.default, trial),
        default_world_id="dark_fantasy",
        default_world_version=1,
    )


def test_world_summary_exposes_controlled_theme_and_scenarios():
    catalog = trial_registry().catalog()
    trial = next(world for world in catalog.worlds if world.key == "theme_trial@1")
    assert trial.theme.typography_id == "modern"
    assert trial.theme.texture_id == "grid"
    assert trial.scenario_options == ("Miasto próbne",)


def test_active_campaign_can_change_pack_only_during_explicit_new_campaign_reset(
    monkeypatch,
):
    monkeypatch.setattr(world_service, "WORLD_PACK_REGISTRY", trial_registry())
    session = GameSession(
        world_pack_id="dark_fantasy",
        world_pack_version=1,
        status="in_progress",
        current_turn_number=3,
    )
    with pytest.raises(HTTPException) as error:
        world_service.resolve_requested_world_pack(session, "theme_trial", 1)
    assert error.value.status_code == 409

    selected = world_service.resolve_requested_world_pack(
        session, "theme_trial", 1, allow_new_campaign_reset=True
    )
    assert selected.key == "theme_trial@1"
    assert session.world_pack_id == "dark_fantasy"


def test_theme_rejects_missing_semantic_tokens_and_unapproved_presentation():
    payload = WORLD_PACK_REGISTRY.default.model_dump(mode="json")
    payload["theme"]["tokens"] = [
        token for token in payload["theme"]["tokens"] if token["id"] != "focus"
    ]
    with pytest.raises(ValidationError, match="complete controlled color token set"):
        WorldPack.model_validate(payload)

    payload = WORLD_PACK_REGISTRY.default.model_dump(mode="json")
    payload["theme"]["typography_id"] = "external_font_url"
    with pytest.raises(ValidationError):
        WorldPack.model_validate(payload)


def test_preview_theme_uses_one_stylesheet_and_prepaint_script():
    root = Path(__file__).parents[1] / "app" / "static"
    stylesheet = (root / "css" / "modules" / "theme.css").read_text(
        encoding="utf-8"
    )
    bootstrap = (root / "js" / "theme-bootstrap.js").read_text(
        encoding="utf-8"
    )
    assert 'data-theme="dark_fantasy"' in stylesheet
    assert "neon_preview" in bootstrap
    assert "rpg_last_world_theme" in bootstrap
    assert "theme-color" in bootstrap
