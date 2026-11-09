# 0013. The Routes map on MapLibre and OpenFreeMap, with a recoloured style in the repository

**Status:** Accepted, November 2026

## Context

The Routes page drew its map with pydeck (`st.pydeck_chart`) on CARTO's basemap. Two things broke that:

- CARTO's basemap tiles now come back watermarked "API KEY REQUIRED" without a key, so the public demo
  and the Pi dashboard showed a stamped map.
- pydeck draws its layers over the whole basemap, labels included, so town names disappeared under the
  route lines. The owner asked for a real, detailed map where roads and towns stay readable.

The Morning redesign ([spec](../superpowers/specs/2026-11-09-morning-redesign-design.md)) also wanted the
map recoloured to the dashboard's palette.

## Decision

- **MapLibre GL JS 4.7.1**, vendored in `dashboard/static/maplibre/` with its BSD licence, rendered in an
  HTML component (`dashboard/map.py` → `st.components.v1.html`).
- **OpenFreeMap** vector tiles: free, no key, OpenStreetMap data.
- **The style is committed:** `scripts/make_map_style.py` takes OpenFreeMap's "positron" style once, changes
  only paint colours (land, water, parks, roads, labels) to the Morning palette, and writes
  `dashboard/static/map-style.json`. Tile, glyph and sprite URLs stay on tiles.openfreemap.org.
- **Routes are inserted below the first label layer**, with a white casing, so labels stay on top. The chosen
  route is drawn last and thickest; hovering a line shows its name.
- **If the tiles or the style fail to load**, the page keeps the routes on a plain background and says so.
- Route labels reach the page as escaped JSON and are shown with `textContent`, never as HTML.

## Consequences

- No API key, no account, no watermark; the map matches the rest of the dashboard.
- The browser still asks a tile server for the tiles in view, as it did with CARTO: the area on screen is
  visible to tiles.openfreemap.org, but no route geometry or other coordinate is sent
  ([0005](0005-privacy-by-construction.md)).
- About 0.9 MB of JavaScript and CSS ship with the dashboard; it is served locally, so the Pi needs no CDN.
- A palette change means re-running the style script and committing the new JSON.

## Alternatives considered

- **Keep pydeck, add a CARTO key:** fixes the watermark, not the hidden labels; adds an account and a secret.
- **pydeck with a custom MapLibre style:** pydeck in Streamlit cannot insert layers below the basemap's labels.
- **Raster tiles from tile.openstreetmap.org:** their usage policy discourages app traffic, and raster tiles
  can't be recoloured cleanly.
- **Loading MapLibre from a CDN:** one more third party on every page view; vendoring is simple and works
  offline.
