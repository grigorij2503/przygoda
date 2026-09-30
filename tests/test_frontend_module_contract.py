import re
from pathlib import Path
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader
from app.worlds.registry import WORLD_PACK_REGISTRY


ROOT = Path(__file__).parents[1]
INDEX_PATH = ROOT / "app" / "templates" / "index.html"
STATIC_ROOT = ROOT / "app" / "static"
STYLE_PATH = STATIC_ROOT / "css" / "style.css"
SERVICE_WORKER_PATH = STATIC_ROOT / "sw.js"
STORY_MAP_PROXY_PATH = STATIC_ROOT / "js" / "modules" / "story-map-proxy.js"
STORY_HISTORY_PATH = ROOT / "app" / "templates" / "partials" / "table" / "story_history.html"
AUTH_GATE_PATH = ROOT / "app" / "templates" / "partials" / "auth_gate.html"


def local_static_path(url: str) -> Path:
    return STATIC_ROOT / urlsplit(url).path.removeprefix("/static/")


def test_index_partials_render_and_referenced_assets_exist():
    environment = Environment(loader=FileSystemLoader(ROOT / "app" / "templates"))
    pack = WORLD_PACK_REGISTRY.default
    rendered = environment.get_template("index.html").render(
        theme=pack.theme,
        theme_style=" ".join(
            f"--ui-{token.id.replace('_', '-')}: {token.value};"
            for token in pack.theme.tokens
        ),
        theme_background=next(
            token.value for token in pack.theme.tokens if token.id == "background"
        ),
        world_key=pack.key,
    )
    assert "{% include" not in rendered
    assert 'data-theme="dark_fantasy"' in rendered
    assert "Jak narrator ma opisywać postać?" in rendered
    assert "Bez rodzaju — narrator używa imienia" in rendered
    assert "On — forma męska" in rendered
    assert "Ona — forma żeńska" in rendered

    local_assets = set(re.findall(r'(?:src|href)="(/static/[^"]+)', rendered))
    assert local_assets
    assert all(local_static_path(url).is_file() for url in local_assets)


def test_room_code_patterns_escape_hyphen_for_html_v_mode_regex():
    auth_gate = AUTH_GATE_PATH.read_text(encoding="utf-8")

    assert auth_gate.count(r'pattern="[a-z0-9\-]{3,50}"') == 2
    assert 'pattern="[a-z0-9-]{3,50}"' not in auth_gate


def test_stylesheet_imports_exist_and_keep_declared_order():
    stylesheet = STYLE_PATH.read_text(encoding="utf-8")
    imports = re.findall(r"@import url\(['\"]([^'\"]+)['\"]\);", stylesheet)
    local_imports = [url for url in imports if url.startswith("./")]

    assert local_imports == [
        "./modules/tokens.css?v=21",
        "./modules/base.css?v=21",
        "./modules/components.css?v=23",
        "./modules/inventory.css?v=24",
        "./modules/market.css?v=2",
        "./modules/map.css?v=22",
        "./modules/lore.css?v=21",
        "./modules/feedback.css?v=21",
        "./modules/responsive.css?v=21",
        "./modules/theme.css?v=24",
        "./modules/theme-art.css?v=5",
    ]
    assert all((STYLE_PATH.parent / urlsplit(url).path).is_file() for url in local_imports)


def test_local_frontend_assets_are_precached_and_scripts_load_before_alpine():
    index_source = INDEX_PATH.read_text(encoding="utf-8")
    service_worker = SERVICE_WORKER_PATH.read_text(encoding="utf-8")
    local_assets = set(re.findall(r'(?:src|href)="(/static/[^"]+)', index_source))
    stylesheet = STYLE_PATH.read_text(encoding="utf-8")
    local_assets.update(
        "/static/css/" + url.removeprefix("./")
        for url in re.findall(r"@import url\(['\"]([^'\"]+)['\"]\);", stylesheet)
        if url.startswith("./")
    )

    assert all(f"'{url}'" in service_worker for url in local_assets)
    assert "const CACHE_NAME = 'ttrpg-gemini-v61';" in service_worker

    scripts = re.findall(r'<script[^>]+src="([^"]+)"', index_source)
    app_index = scripts.index("/static/js/app.js?v=35")
    assert scripts.index("/static/js/theme-bootstrap.js?v=33") < scripts.index(
        "/static/js/modules/core.js?v=41"
    )
    alpine_index = scripts.index(
        "https://cdn.jsdelivr.net/npm/alpinejs@3.14.3/dist/cdn.min.js"
    )
    feature_indexes = [
        index for index, url in enumerate(scripts)
        if url.startswith("/static/js/modules/")
    ]
    assert feature_indexes
    assert max(feature_indexes) < app_index < alpine_index


def test_character_break_never_exposes_proxy_vote_after_wait_timer():
    source = STORY_MAP_PROXY_PATH.read_text(encoding="utf-8")
    method = source.split("canOpenProxyAction(character) {", 1)[1].split(
        "openProxyActionVote(character) {", 1
    )[0]
    break_guard = "character?.participation_status === 'on_break'"
    timer_fallback = "this.proxyNow >= availableAt"
    assert break_guard in method
    assert method.index(break_guard) < method.index(timer_fallback)


def test_incapacitated_character_never_exposes_proxy_vote_after_wait_timer():
    source = STORY_MAP_PROXY_PATH.read_text(encoding="utf-8")
    method = source.split("canOpenProxyAction(character) {", 1)[1].split(
        "openProxyActionVote(character) {", 1
    )[0]
    alive_guard = "!character?.is_alive"
    timer_fallback = "this.proxyNow >= availableAt"
    assert alive_guard in method
    assert method.index(alive_guard) < method.index(timer_fallback)


def test_incapacitated_character_is_not_presented_as_waiting_for_action():
    party_panel = (ROOT / "app" / "templates" / "partials" / "table" / "party_panel.html").read_text(encoding="utf-8")
    waiting_expression = party_panel.split('x-text="p.participation_status', 1)[1].split('">', 1)[0]

    assert "!p.is_alive" in waiting_expression
    assert waiting_expression.index("!p.is_alive") < waiting_expression.index("p.has_submitted_action")


def test_mechanical_turn_events_are_grouped_inside_character_action_cards():
    template = STORY_HISTORY_PATH.read_text(encoding="utf-8")
    story_module = STORY_MAP_PROXY_PATH.read_text(encoding="utf-8")

    assert "Mechaniczny zapis tury" not in template
    assert 'class="dice-badge action-result-card' in template
    assert "actionMechanicalEvents(t, act)" in template
    assert "Suma obrażeń:" in template
    assert "actionDamageTaken(turn, action)" in story_module
    assert "actionHealingReceived(turn, action)" in story_module
    assert "unassignedMechanicalEvents(turn)" in story_module


def test_action_result_card_keeps_player_declaration_readable_and_uses_compact_labels():
    template = STORY_HISTORY_PATH.read_text(encoding="utf-8")
    components = (STATIC_ROOT / "css" / "modules" / "components.css").read_text(encoding="utf-8")

    assert "action-result-card__declaration" in template
    assert "action-result-card__roll" in template
    assert "CEL AKCJI:" not in template
    assert "? 'SUKCES' : 'PORAŻKA'" in template
    assert ".action-result-card__declaration" in components
    assert "flex: 1 0 100%;" in components
    assert ".action-result-card__roll" in components
    assert "min-width: min(100%, 27rem);" in components


def test_roll_context_shows_equipment_total_instead_of_item_list():
    story_module = STORY_MAP_PROXY_PATH.read_text(encoding="utf-8")
    roll_context = story_module.split("if (event.type === 'roll_context') {", 1)[1].split(
        "if (event.type === 'boss_attack')", 1
    )[0]

    assert "event.item_bonus" in roll_context
    assert "source.name" not in roll_context
