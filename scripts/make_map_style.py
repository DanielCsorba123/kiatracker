"""Generate the dashboard's map style: OpenFreeMap "positron", recoloured to the Morning palette.

Run once (or when the palette changes) and commit the result:

    uv run python scripts/make_map_style.py

Only paint colours change; the tile, glyph and sprite URLs stay on tiles.openfreemap.org.
"""

import json
from pathlib import Path

import httpx

from kiatracker.dashboard import theme

SOURCE = "https://tiles.openfreemap.org/styles/positron"
OUT = Path(__file__).parents[1] / "src" / "kiatracker" / "dashboard" / "static" / "map-style.json"

# basemap shades: quieter than the UI tokens, so the routes on top stay the strongest colour on the map
MAP_COLOURS = {
    "land": theme.PAPER,
    "water": "#C7DDF0",
    "park": "#E1ECDD",
    "wood": "#D8E6D3",
    "residential": "#EBEFF3",
    "minor": "#E1E6EC",
    "major": "#CCD6E0",
    "motorway": "#AFC0D1",
    "rail": "#D3DAE2",
}


def recolour(style: dict) -> dict:
    c = MAP_COLOURS
    for layer in style["layers"]:
        lid, kind, paint = layer["id"], layer["type"], layer.setdefault("paint", {})
        if kind == "background":
            paint["background-color"] = c["land"]
        elif lid in ("water", "waterway"):
            paint["fill-color" if kind == "fill" else "line-color"] = c["water"]
        elif lid == "park":
            paint["fill-color"] = c["park"]
        elif lid == "landcover_wood":
            paint["fill-color"], paint["fill-opacity"] = c["wood"], 0.9
        elif lid in ("landuse_residential", "building"):
            paint["fill-color"] = c["residential"]
            if lid == "landuse_residential":
                paint["fill-opacity"] = 1
        elif lid.startswith("highway_motorway"):
            paint["line-color"] = c["major"] if "casing" in lid else c["motorway"]
        elif lid.startswith("highway_major") or lid.startswith("boundary"):
            paint["line-color"] = c["major"]
        elif lid.startswith("highway_minor") or lid == "highway_path":
            paint["line-color"] = c["minor"]
        elif lid.startswith("railway"):
            paint["line-color"] = c["rail"]
        if kind == "symbol":
            paint["text-color"], paint["text-halo-color"], paint["text-halo-width"] = (
                theme.INK,
                c["land"],
                1.6,
            )
    return style


def main() -> None:
    style = (
        httpx.get(SOURCE, timeout=30, headers={"User-Agent": "kiatracker-map-style"})
        .raise_for_status()
        .json()
    )
    OUT.write_text(json.dumps(recolour(style), indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(f"wrote {OUT} ({len(style['layers'])} layers)")


if __name__ == "__main__":
    main()
