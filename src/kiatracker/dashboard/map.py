"""The Routes map: a small MapLibre page with the recoloured OpenFreeMap style and the routes drawn under the
labels, so town names stay readable. Rendered with `st.components.v1.html`; MapLibre and the style are
served from the dashboard's own static folder, only the tiles come from tiles.openfreemap.org.
"""

import json

from kiatracker.dashboard import theme

ATTRIBUTION = "© OpenStreetMap contributors · OpenFreeMap"
FALLBACK = "Map tiles unavailable; showing the routes only."


def _script_json(value) -> str:
    """JSON that is safe inside a <script> block: no character can close the tag or start markup."""
    return json.dumps(value).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


PAGE = """<!doctype html>
<html><head><meta charset="utf-8">
<link rel="stylesheet" href="app/static/maplibre/maplibre-gl.css">
<script src="app/static/maplibre/maplibre-gl.js"></script>
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
const ROUTES = {routes};
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
const bounds = all.reduce((b, c) => b.extend(c), new maplibregl.LngLatBounds(all[0], all[0]));
const map = new maplibregl.Map({{ container: 'map', style: 'app/static/map-style.json', bounds: bounds,
  fitBoundsOptions: {{ padding: 40 }}, attributionControl: false, cooperativeGestures: true }});
map.addControl(new maplibregl.NavigationControl({{ showCompass: false }}), 'top-right');

function addRoutes() {{
  if (map.getSource('route-0')) return;
  const layers = map.getStyle().layers || [];
  const firstSymbol = (layers.find(l => l.type === 'symbol') || {{}}).id;
  ROUTES.forEach((r, i) => map.addSource('route-' + i, {{ type: 'geojson',
    data: {{ type: 'Feature', properties: {{ label: r.label }}, geometry: {{ type: 'LineString', coordinates: r.coords }} }} }}));
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
const popup = new maplibregl.Popup({{ closeButton: false, closeOnClick: false }});
map.on('load', addRoutes);
let failed = false;
map.on('error', () => {{
  if (failed) return;
  failed = true;
  document.getElementById('notice').hidden = false;
  if (!map.isStyleLoaded()) {{
    map.setStyle({{ version: 8, sources: {{}}, layers: [{{ id: 'paper', type: 'background',
      paint: {{ 'background-color': PAPER }} }}] }});
    map.once('styledata', addRoutes);
  }}
}});
map.once('idle', () => {{ window.__mapReady = true; }});
</script></body></html>
"""


def map_html(routes: list[dict], *, height: int = 560) -> str:
    """A full HTML page for the Routes map. Each route: label, colour, coords ([[lon, lat], …]); the first
    route is the chosen one and is drawn on top."""
    return PAGE.format(
        routes=_script_json(routes),
        paper=theme.PAPER,
        paper_json=_script_json(theme.PAPER),
        ink=theme.INK,
        ink_json=_script_json(theme.INK),
        muted=theme.MUTED,
        attribution=ATTRIBUTION,
        fallback=FALLBACK,
    )
