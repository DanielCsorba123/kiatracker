"""The Routes map: a small MapLibre page with the recoloured OpenFreeMap style and the routes drawn under the
labels, so town names stay readable.

The page is a static file (`static/map.html`, generated from `page()` and committed), shown in an iframe. It
must not be a srcdoc iframe: there `location.origin` is "null", MapLibre's blob worker runs under the real
origin, and the two stop talking, so tiles never load. The routes travel in the URL fragment, which the
browser never sends to a server. MapLibre and the style come from the dashboard's own static folder; only the
tiles come from tiles.openfreemap.org.
"""

import json
from pathlib import Path
from urllib.parse import quote

from kiatracker.dashboard import theme

STATIC = Path(__file__).parent / "static"
ATTRIBUTION = "© OpenStreetMap contributors · OpenFreeMap"
FALLBACK = "Map tiles unavailable; showing the routes only."
MAX_POINTS = 800  # per route; keeps the fragment small, invisible at map zoom levels

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Routes map</title>
<link rel="stylesheet" href="maplibre/maplibre-gl.css">
<script src="maplibre/maplibre-gl.js"></script>
<style>
html, body {{ margin: 0; height: 100%; background: {paper}; font-family: "Hanken Grotesk", sans-serif; }}
#map {{ position: absolute; inset: 0; border-radius: 16px; overflow: hidden; }}
.legend {{ position: absolute; left: 14px; bottom: 14px; display: flex; flex-wrap: wrap; gap: 14px; background: #fff;
          border-radius: 14px; padding: 9px 13px; font-size: 13px; color: {ink};
          box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
.legend i {{ display: inline-block; width: 22px; height: 4px; border-radius: 2px; margin-right: 7px;
             vertical-align: middle; }}
.attrib {{ position: absolute; right: 12px; bottom: 10px; font-size: 11px; color: {muted};
          background: rgba(255,255,255,0.8); padding: 2px 6px; border-radius: 6px; }}
.notice {{ position: absolute; left: 14px; top: 14px; font-size: 13px; color: {ink}; background: #fff;
          padding: 8px 12px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
.maplibregl-popup-content {{ font: 13px "Hanken Grotesk", sans-serif; color: {ink}; border-radius: 10px; }}
</style></head>
<body><div id="map"></div><div class="legend" id="legend"></div>
<div class="attrib">{attribution}</div><div class="notice" id="notice" hidden>{fallback}</div>
<script>
let ROUTES = [];
try {{ ROUTES = JSON.parse(decodeURIComponent(location.hash.slice(1))); }} catch (e) {{ ROUTES = []; }}
const PAPER = {paper_json};
const legend = document.getElementById('legend');
ROUTES.forEach(r => {{
  const item = document.createElement('span');
  const swatch = document.createElement('i');
  swatch.style.background = r.colour;
  item.append(swatch, document.createTextNode(r.label));
  legend.append(item);
}});
const all = ROUTES.flatMap(r => r.coords);
const options = {{ container: 'map', style: 'map-style.json', attributionControl: false, cooperativeGestures: true }};
if (all.length) {{
  options.bounds = all.reduce((b, c) => b.extend(c), new maplibregl.LngLatBounds(all[0], all[0]));
  options.fitBoundsOptions = {{ padding: 40 }};
}} else {{
  options.center = [16.4, 48.2];
  options.zoom = 7;
}}
const map = new maplibregl.Map(options);
map.addControl(new maplibregl.NavigationControl({{ showCompass: false }}), 'top-right');
const popup = new maplibregl.Popup({{ closeButton: false, closeOnClick: false }});

function addRoutes() {{
  if (!ROUTES.length || map.getSource('route-0')) return;
  const layers = map.getStyle().layers || [];
  const firstSymbol = (layers.find(l => l.type === 'symbol') || {{}}).id;
  ROUTES.forEach((r, i) => map.addSource('route-' + i, {{ type: 'geojson',
    data: {{ type: 'Feature', properties: {{}}, geometry: {{ type: 'LineString', coordinates: r.coords }} }} }}));
  const order = ROUTES.map((_, i) => i).slice(1).concat([0]);  // the chosen route last, on top
  order.forEach(i => {{
    const width = i === 0 ? 6 : 4;
    map.addLayer({{ id: 'casing-' + i, type: 'line', source: 'route-' + i,
      layout: {{ 'line-cap': 'round', 'line-join': 'round' }},
      paint: {{ 'line-color': '#ffffff', 'line-width': width + 4 }} }}, firstSymbol);
    map.addLayer({{ id: 'line-' + i, type: 'line', source: 'route-' + i,
      layout: {{ 'line-cap': 'round', 'line-join': 'round' }},
      paint: {{ 'line-color': ROUTES[i].colour, 'line-width': width }} }}, firstSymbol);
    map.on('mousemove', 'line-' + i, e => {{
      const text = document.createElement('span');
      text.textContent = ROUTES[i].label;
      popup.setLngLat(e.lngLat).setDOMContent(text).addTo(map);
    }});
    map.on('mouseleave', 'line-' + i, () => popup.remove());
  }});
  const ends = [ROUTES[0].coords[0], ROUTES[0].coords[ROUTES[0].coords.length - 1]];
  map.addSource('ends', {{ type: 'geojson', data: {{ type: 'FeatureCollection',
    features: ends.map(c => ({{ type: 'Feature', properties: {{}}, geometry: {{ type: 'Point', coordinates: c }} }})) }} }});
  map.addLayer({{ id: 'ends', type: 'circle', source: 'ends',
    paint: {{ 'circle-radius': 7, 'circle-color': '#ffffff', 'circle-stroke-color': {ink_json},
              'circle-stroke-width': 3 }} }}, firstSymbol);
}}
map.on('load', addRoutes);
// One failed tile is normal on a flaky network: only many failures with nothing loaded mean the tiles are
// unreachable. Only a missing style itself swaps in the plain background.
let tileErrors = 0, tileLoaded = false, fellBack = false;
map.on('data', e => {{ if (e.tile && e.dataType === 'source') tileLoaded = true; }});
map.on('error', e => {{
  if (e.tile) {{
    tileErrors += 1;
    if (tileErrors >= 8 && !tileLoaded) document.getElementById('notice').hidden = false;
    return;
  }}
  if (fellBack) return;
  if (!map.getStyle() || !map.getStyle().sources || !Object.keys(map.getStyle().sources).length) {{
    fellBack = true;
    document.getElementById('notice').hidden = false;
    map.setStyle({{ version: 8, sources: {{}}, layers: [{{ id: 'paper', type: 'background',
      paint: {{ 'background-color': PAPER }} }}] }});
    map.once('styledata', addRoutes);
  }}
}});
map.once('idle', () => {{ window.__mapReady = true; }});
</script></body></html>
"""


def page() -> str:
    """The map page, with the Morning tokens filled in. `static/map.html` is this, committed."""
    return PAGE.format(
        paper=theme.PAPER,
        paper_json=json.dumps(theme.PAPER),
        ink=theme.INK,
        ink_json=json.dumps(theme.INK),
        muted=theme.MUTED,
        attribution=ATTRIBUTION,
        fallback=FALLBACK,
    )


def _thin(coords: list, limit: int = MAX_POINTS) -> list:
    if len(coords) <= limit:
        return coords
    step = len(coords) / limit
    return [coords[int(i * step)] for i in range(limit)] + [coords[-1]]


def map_src(routes: list[dict]) -> str:
    """The iframe address: the static page plus the routes (label, colour, coords as [lon, lat]) in the
    fragment. The first route is the chosen one and is drawn on top."""
    data = [{**r, "coords": _thin(r["coords"])} for r in routes]
    return "app/static/map.html#" + quote(json.dumps(data, separators=(",", ":")), safe="")


def write_page() -> None:
    (STATIC / "map.html").write_text(page(), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    write_page()
