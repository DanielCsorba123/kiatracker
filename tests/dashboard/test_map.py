import json
from pathlib import Path
from urllib.parse import unquote

from kiatracker.dashboard.map import map_src, page

STATIC = Path(__file__).parents[2] / "src" / "kiatracker" / "dashboard" / "static"
ROUTE = {"label": "Fastest", "colour": "#DC756D", "coords": [[15.6, 48.4], [16.2, 47.8]]}


def test_page_loads_vendored_maplibre_style_and_attribution():
    out = page()
    assert "maplibre/maplibre-gl.js" in out and "map-style.json" in out
    assert "© OpenStreetMap contributors · OpenFreeMap" in out


def test_committed_map_page_matches_the_template():
    """The page is served from static/ so it has a real origin (MapLibre's worker needs one)."""
    assert (STATIC / "map.html").read_text(encoding="utf-8") == page()


def test_page_has_tile_error_fallback():
    out = page()
    assert "on('error'" in out and "Map tiles unavailable; showing the routes only." in out


def test_routes_travel_in_the_fragment_and_never_reach_innerhtml():
    evil = {"label": "</script><script>alert(1)</script>", "colour": "#000000", "coords": [[0, 0], [1, 1]]}
    src = map_src([evil])
    assert src.startswith("app/static/map.html#") and "<" not in src  # the fragment is never sent to a server
    assert json.loads(unquote(src.split("#", 1)[1]))[0]["label"] == evil["label"]
    assert "innerHTML" not in page() and "textContent" in page()


def test_long_routes_are_thinned_but_keep_their_ends():
    coords = [[16 + i / 10_000, 48.0] for i in range(5000)]
    [route] = json.loads(unquote(map_src([{**ROUTE, "coords": coords}]).split("#", 1)[1]))
    assert (
        len(route["coords"]) <= 801 and route["coords"][0] == coords[0] and route["coords"][-1] == coords[-1]
    )


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
    assert (STATIC / "maplibre" / "maplibre-gl.css").exists()
    assert (STATIC / "maplibre" / "LICENSE.txt").exists()
