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

    local_assets = set(re.findall(r'(?:src|href)="(/static/[^"]+)', rendered))
    assert local_assets
    assert all(local_static_path(url).is_file() for url in local_assets)


def test_stylesheet_imports_exist_and_keep_declared_order():
    stylesheet = STYLE_PATH.read_text(encoding="utf-8")
    imports = re.findall(r"@import url\(['\"]([^'\"]+)['\"]\);", stylesheet)
    local_imports = [url for url in imports if url.startswith("./")]

    assert local_imports == [
        "./modules/tokens.css?v=21",
        "./modules/base.css?v=21",
        "./modules/components.css?v=21",
        "./modules/inventory.css?v=23",
        "./modules/map.css?v=21",
        "./modules/lore.css?v=21",
        "./modules/feedback.css?v=21",
        "./modules/responsive.css?v=21",
        "./modules/theme.css?v=24",
        "./modules/theme-art.css?v=3",
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
    assert "const CACHE_NAME = 'ttrpg-gemini-v41';" in service_worker

    scripts = re.findall(r'<script[^>]+src="([^"]+)"', index_source)
    app_index = scripts.index("/static/js/app.js?v=31")
    assert scripts.index("/static/js/theme-bootstrap.js?v=33") < scripts.index(
        "/static/js/modules/core.js?v=32"
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
