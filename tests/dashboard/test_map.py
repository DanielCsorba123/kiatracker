import json
from pathlib import Path

from kiatracker.dashboard.map import map_html

STATIC = Path(__file__).parents[2] / "src" / "kiatracker" / "dashboard" / "static"
ROUTE = {"label": "Fastest", "colour": "#DC756D", "coords": [[15.6, 48.4], [16.2, 47.8]]}


def test_map_html_embeds_routes_and_attribution():
    out = map_html([ROUTE])
    assert "app/static/maplibre/maplibre-gl.js" in out and "app/static/map-style.json" in out
    assert "© OpenStreetMap contributors · OpenFreeMap" in out and "[15.6, 48.4]" in out


def test_map_html_has_tile_error_fallback():
    out = map_html([{"label": "A", "colour": "#000000", "coords": [[0, 0], [1, 1]]}])
    assert "on('error'" in out and "Map tiles unavailable; showing the routes only." in out


def test_route_labels_never_reach_innerhtml():
    evil = {"label": "</script><script>alert(1)</script>", "colour": "#000000", "coords": [[0, 0], [1, 1]]}
    out = map_html([evil])
    assert "</script><script>" not in out and "innerHTML" not in out


def test_committed_style_only_uses_openfreemap_tiles():
    style = json.loads((STATIC / "map-style.json").read_text(encoding="utf-8"))
    urls = [s.get("url", "") for s in style["sources"].values()] + [
        style.get("glyphs", ""),
        style.get("sprite", ""),
    ]
    assert all(u.startswith("https://tiles.openfreemap.org") for u in urls if u)
    background = next(layer for layer in style["layers"] if layer["type"] == "background")
    assert background["paint"]["background-color"] == "#F4F7FA"


def test_maplibre_is_vendored_with_its_licence():
    assert (STATIC / "maplibre" / "maplibre-gl.js").stat().st_size > 100_000
    assert (STATIC / "maplibre" / "maplibre-gl.css").exists() and (
        STATIC / "maplibre" / "LICENSE.txt"
    ).exists()
