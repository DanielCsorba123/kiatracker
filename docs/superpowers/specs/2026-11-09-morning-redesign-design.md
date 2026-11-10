# Dashboard redesign "Morning": design

Date: 2026-11-09. Status: direction, page mockups and range rule approved by the owner ("K is beautiful … go with that", "make a redesign and go with your mixed recommended", "write the spec and apply your same rule"). This written spec awaits review before an implementation plan.

Mockups: the "Final · K Morning" row of the private design canvas (claude.ai artifact `Sww2XAH5cnEsi2GrWJL7Vu`), six pages. Where this text and the mockups disagree, this text wins.

## 1. Purpose

Give Windrose a visual identity that reads as designed by a person, not generated: light, pleasant and calm, but not thin on information. The redesign changes how every page looks and opens, adds a few data-driven sections the owner asked for, and replaces the map. It does not change the data foundation, the model or the privacy model.

What the owner said, and what it rules out:

- Wanted: light and relaxed, "not too simple, not chaotic", graphs that explain, a real detailed map, the height profile along the road.
- Rejected: high-contrast, "racy" or party styles (dark cockpit, riso, thermal), simplified maps, big statement headlines on most pages.

## 2. Identity

### 2.1 Tokens

One light theme. Colours are named by role; every chart and component uses the role, never a raw hex.

| Role | Value | Use |
|---|---|---|
| `sky-top` → `paper` | `#E4EEF7` → `#F4F7FA` | page background: a vertical gradient over the first ~520 px, then flat paper |
| `card` | `#FFFFFF` | cards |
| `ink` | `#1D2B3A` | text, primary button |
| `ink-soft` | `#44525F` | body copy in cards |
| `muted` | `#6F7E8E` | labels, captions, axis text |
| `rule` | `#E2E8EF` | dividers, empty tracks |
| `wash` | `#EDF2F7` | input fields, slider and bar tracks |
| `coral` | `#E07A73` | the one highlight per chart: today, this week, the chosen route, costs more |
| `sky` | `#4A90C2` | the main data series, the EV, range |
| `sun` | `#F2C14E` | logo and the plug-in-hour peak only |
| `pale` | `#C8D8E8` | secondary bars (other weeks, other months) |
| tints | `#FDF0EE` coral, `#EAF3FA` sky, `#FEF6E4` sun, `#E8F4EC` green | icon chips and soft callouts |

**Text contrast.** `coral` and `sky` fail WCAG AA for normal-size text on white. Coloured text uses darker inks, `coral-ink #B4463E` and `sky-ink #2F6E9A`, each checked at 4.5 : 1 or better against white and `paper` by a unit test. The light fills stay for bars, dots and large display numbers (≥ 24 px), which need 3 : 1. The test computes the ratios, so a token change that breaks contrast fails CI.

**Shape.** Cards have a 24 px radius, no border, and a two-layer shadow (`0 1px 2px` and `0 8px 24px` in `ink` at 4–5 % opacity). Inputs and chips have a 14 px radius; pills and switches are fully rounded. Bars have rounded ends (6 px radius).

### 2.2 Type

- **Young Serif** (one weight) for display: section titles 24 px, big numbers 22–64 px.
- **Hanken Grotesk** 400/500/600 for everything else, 13–18 px.
- Both are SIL OFL fonts, self-hosted under `dashboard/static/` with their licences added to `FONTS-LICENSE.md`. Inter and Space Grotesk are removed. No font request leaves the server, as now.

### 2.3 Voice

- Plain sentences in the second person ("You can drive about 384 km today").
- Every number carries its unit and, where it matters, its uncertainty ("likely 352–411").
- No exclamation marks and no verdicts about the owner's habits.
- Statement headlines appear only on the Overview. Every other page opens straight into content and keeps a visually hidden `<h1>` with the page name for screen readers.

### 2.4 Light only

The current dashboard follows the viewer's light or dark setting. Morning is designed as a light theme, so `.streamlit/config.toml` sets `base = "light"` and drops `[theme.dark]`.

- **Why:** a faithful dark variant doubles the work on every custom component, and nobody asked for it.
- **Cost:** viewers whose system is set to dark get the light dashboard.
- **Screenshots:** the README screenshots are retaken in light mode.

## 3. Shell

- **Navigation:** pages move from the sidebar to the top bar (`st.navigation(position="top")`), restyled as the rounded tab bar in the mockups. The sun logo and the "Windrose" wordmark sit on the left. The sidebar is removed.
- **Period:** the date range moves into a compact "This year ▾" control (`st.popover` with the date input), right-aligned under the navigation, on the pages that use a period (Overview, Drives, Charging, Costs). Defaults stay as today: 365 days in the demo, 30 for personal data.
- **Demo notice:** instead of the blue `st.info` box, a slim rounded strip (`sky` tint) above the content gives the same text: simulated data, real tracker since …, real data expected … . The page footer line in the mockups repeats it in `muted`.
- **Greeting:** the Overview's first line follows local time: "Good morning" (05–12), "Good afternoon" (12–18), "Good evening" (otherwise), followed by the current temperature and wind.

## 4. Implementation approach

Streamlit stays. Each element is built the simplest way that reaches the mockup:

| Element | How |
|---|---|
| Colours, fonts, radius | `.streamlit/config.toml` `[theme]` (fonts, `primaryColor = ink`, backgrounds, `baseRadius`) |
| Card look and gradient | one CSS block in `ui.py`, aimed at keyed containers (`st.container(key="card-…")` gives the stable class `st-key-card-…`) and at `stApp` for the gradient |
| Stat strips, briefing, savings figures, forecast rows, route cards, drive and session lists, tips | small HTML builders in a new `dashboard/components.py`: frame or dict in, HTML string out, rendered with `st.html`; every interpolated value is escaped |
| Bar, scatter, histogram and profile charts | Altair, restyled by `charts.house()` with the new tokens; chart titles off, because section titles are HTML |
| Switches (Week · Month · Year, speed, Usual 80 % · Full 100 %) | `st.segmented_control`, restyled |
| What-if sliders | `st.slider`, restyled |
| Map | new MapLibre component (section 6) |

`components.py` has no Streamlit import, like `charts.py`, so its builders are unit-tested.

## 5. Pages

Each page lists its sections top to bottom. "(existing)" means the data already exists and only the presentation changes.

### 5.1 Overview (approved as mocked)

1. **Hero:** greeting line. Headline "You can drive about **N km** today" (N in `coral-ink`), with a sentence giving the likely range, the battery %, and one everyday comparison: commute round trips, from the most frequent drive pair, or a known road trip distance. Next to it, a battery card: a bar for the %, and This year / Average / Saved.
2. **Range this week, with the forecast:** seven day columns with icon, temperature and range. Today is highlighted with the coral tint. Day values follow the range rule (section 7).
3. **How much you use, month by month** (existing data): bars, with months more than 10 % above the period average in `coral`.
4. **Worth knowing:** up to three tips from fixed templates, each shown only when its condition holds:
   - cold forecast: minimum below 5 °C in the next three days → pre-heat while plugged in, with the estimated saving on the usual commute;
   - the week's biggest same-route difference: the same start and end zone, consumption differing by at least 5 % → shows the temperature difference;
   - share of energy charged at home.
5. **Distance per week** (existing): bars, this week in `coral`.

### 5.2 Drives

1. **Your briefing:** a warm-tinted card, "from the last 7 days", with up to three items:
   - the largest condition effect, from `condition_effects`, plus how many of this week's drives it touched;
   - this week against last week: drives, km, kWh/100 km and the % change;
   - the best drive of the week: lowest kWh/100 km among drives of 5 km or more, with its temperature.

   An item without enough data (for example no drive last week) is left out. With no drives in the 7 days, the card says so in one line.
2. **Stat strip** (existing tiles): Drives, Distance, Average, Best, Hardest.
3. **What makes a drive cost more** (existing `condition_effects`): one rounded bar per condition with its % and a "below 5 °C vs above 15 °C" explanation. A bar is grey while either side has fewer than `MIN_PER_SIDE` drives.
4. **How far a full battery goes** (existing `range_grid`): an HTML grid of temperatures (−10 to 30 °C) against wind (calm, 15, 30 km/h), shaded in `sky` by range, with the existing speed switch. This stays "on a full battery": it describes the car, not a forecast.
5. **Every drive of the year** (existing): a dot per drive over time, coral at 19 kWh/100 km or more, with the seasonal average line.
6. **Recent drives:** the last ~8 drives grouped by local day (Today, Yesterday, weekday names), each with time, weather icon, zone pair ("Home → Work"), km, a coloured kWh/100 km chip and temperature. The analyst expander and full table stay below, unchanged.

### 5.3 Charging

1. **Stat strip** (existing): Sessions, Energy charged, At home (share of kWh), Charged to full.
2. **A typical charge:** one battery bar from the median start % to the median end %, labelled with "+N % per session, typically".
3. **Battery when you plug in / when you stop** (existing histograms): side by side, start in `sky`, end in `coral`, each with one plain sentence about the most common bins.
4. **When you plug in:** sessions by local start hour. This chart is new, from existing session start times. Bars of the 4-hour peak window are in `sun`; the sentence is phrased conditionally ("If your tariff has a cheaper night rate …").
5. **Energy charged per week** (existing), this week in `coral`.
6. **Latest sessions:** date, time, zone, a from → to bar (DC sessions above 22 kW in `coral`), kWh and kW. The full table stays below.

### 5.4 Costs

1. **Saved compared with a petrol car:** a Week · Month · Year switch, default Month.
   - **Figures for the last complete bucket:** saved (big, `coral-ink`), paid for electricity, what petrol would have cost, and the km driven.
   - **Chart:** one bar per bucket, the last 12 weeks, last 12 months or every year since the first drive. The last complete bucket is in `coral` with its value labelled.
   - **Caption:** the total over the shown buckets.
   - Hungary (Ft) is the primary currency, as now. Amounts are rounded to 100 Ft.
2. **Per 100 km in Hungary** (existing): EV, diesel and petrol as horizontal rounded bars, with the pump-price week in the note.
3. **The same driving in Austria** (existing): the same shape in €.

The old monthly grouped chart (EV, diesel, petrol) is removed: the savings section replaces it. `queries.costs` gains week and year bucketing next to month. The arithmetic and its tests are unchanged.

### 5.5 Range

1. **Stat strip:** Range now (likely interval, speed), Battery (% and kWh usable), Typical error (backtest MAE against temperature-only), Learned from (drives, "retrained every night").
2. **The next seven days, and what each one costs you:**
   - One row per day: the day and its starting charge ("from 76 %" / "from 80 %"); weather icon, minimum–maximum temperature, wind direction arrow and speed; a bar; the range with its likely interval.
   - The bar is split into the range achieved, km lost to cold and km lost to wind. Its full length is the same charge on a mild (20 °C), calm day.
   - A "Usual N % · Full 100 %" switch above the rows, and one line explaining the rule (section 7).
   - Wind stays averaged over all directions, with the existing note.
3. **What if…** (existing sliders: temperature, wind, speed): a result card with the full-battery range, its interval, and a bar against the EV3's best case (672 km).
4. **How well it predicts** (existing predicted-vs-actual).
5. **What it has learned about your car:** the existing model lines, each with an icon chip, worded as in the mockup and computed from the fitted coefficients, never hard-coded.

### 5.6 Routes

1. **Form card** (existing fields): From, To, Also through, When, Compare.
2. **Map** (section 6).
3. **Route cards:** one per route, with a coloured dot, name, "wins N of 100", kWh, minutes, km, arrival %, roads and climb.
4. **Up and down along the way:** elevation along the road for all routes on one shared distance axis. The fastest route is a `coral` filled area, the second a `sky` line, the others dashed `pale`. The highest point is annotated ("559 m · Wienerwald"), as is the second route's maximum. A sentence underneath gives the climb's energy cost and what descent returned, from `energy_breakdown`.
5. **Why they end up even** (existing `route_breakdown`): diverging bars by cause, with the net line and one callout sentence.

The statement headline is removed.

## 6. Map

**Problem.** The pydeck map draws the basemap from CARTO, which now returns watermarked "API KEY REQUIRED" tiles without a key. pydeck also draws routes over the basemap's labels, so town names disappear under the tracks.

**Decision.** Replace pydeck on the Routes page with a small MapLibre GL JS component:

- **Library:** MapLibre GL JS is self-hosted under `dashboard/static/maplibre/` with a pinned version and its BSD licence. It is rendered with `st.components.v1.html`, receiving the routes as GeoJSON.
- **Basemap:** OpenFreeMap's free vector tiles (no key, OpenStreetMap data). The style is a committed `dashboard/static/map-style.json`, generated once from OpenFreeMap "positron" by `scripts/make_map_style.py`, which recolours land, water, parks, roads and labels to the tokens.
- **Track order:** routes are added beneath the first symbol layer, so labels stay on top. Each route gets a white casing; the chosen (fastest) route is drawn last and thickest.
- **Interaction:** hovering a track shows its name; pan and zoom stay enabled. A route card's colour dot matches its track.
- **Attribution:** "© OpenStreetMap contributors · OpenFreeMap", always visible.

**Privacy.** As with CARTO today, the browser asks the tile server for the tiles in view. Neither the route nor any coordinate is sent beyond that. Geocoding (Nominatim) and routing (OSRM) are unchanged. ADR 0005 gains a sentence naming OpenFreeMap as the tile provider.

**Fallback.** If the tiles fail to load, the tracks still draw on a plain `paper` background with a one-line notice.

A new ADR, 0013, records the MapLibre and OpenFreeMap decision and why pydeck was dropped.

## 7. The range rule

Every multi-day range forecast (the Overview week strip and the Range page rows) uses:

- **Today** starts from the latest battery reading.
- **Later days** start from the **usual charge level**: the median end % of the last 20 finished charging sessions that are not DC fast charges (average power ≤ 22 kW), rounded to the nearest 5 %.
  - With fewer than 5 such sessions, it falls back to 80 % and the explanation line says "assumed 80 %".
  - It never goes below the latest reading's level, and never above 100 %.
- **Full 100 %** (switch on the Range page) makes every later day start from 100 %. Today keeps the real reading.
- **Explanation line**, generated from the same numbers: "Today starts from what is in the battery now (76 %). The coming days assume you charge as usual: you stopped at 80 % in 14 of your last 20 charges."
- **Cold and wind split** for each day, three model evaluations at the day's speed:
  - **A:** the same charge at 20 °C, calm;
  - **B:** the day's temperature, calm;
  - **C:** the day's temperature and wind.

  Lost to cold = A − B and lost to wind = B − C; the bar is C. The split runs in this order, cold first, which the code documents.
- **Forecast horizon:** `fetch_forecast` asks Open-Meteo for `forecast_days = 7` instead of 3. `daily_outlook` also returns each day's minimum and maximum temperature and its mean wind direction. `HOURLY` already fetches `wind_direction_10m`.

The "How far a full battery goes" grid and the What-if card stay at 100 % on purpose: they describe the car, not a forecast.

## 8. Code changes

| File | Change |
|---|---|
| `.streamlit/config.toml` | new theme: light base, tokens, Young Serif / Hanken Grotesk font faces |
| `dashboard/static/` | new fonts and licences; `maplibre/`; `map-style.json`; sun logo SVG |
| `dashboard/ui.py` | tokens as constants; CSS for cards, gradient, nav, switches and sliders; hidden `h1`; demo strip |
| `dashboard/components.py` (new) | HTML builders: stat strip, briefing, savings figures, forecast rows, route cards, drive list, session list, tips, map component HTML |
| `dashboard/charts.py` | `house()` restyled; new `plug_hours`, `savings_bars`, `drives_by_day`; `route_profile` reworked to the shared-axis area design; `grouped_bar` removed if unused |
| `dashboard/queries.py` | `usual_charge_level`, `plug_hours`, `costs` week and year buckets, `briefing_facts`, `recent_drives_by_day` |
| `forecast/outlook.py` | 7 days; minimum, maximum and wind direction; `start_soc` per day; cold and wind split |
| `dashboard/views/*.py` | each page rebuilt to section 5 |
| `dashboard/app.py` | top navigation, period popover, no sidebar |
| `scripts/make_map_style.py` (new) | generates the recoloured map style |
| `scripts/capture_screenshots.py` (new) | the README screenshot script, until now kept outside the repo, committed and switched to light mode; Playwright with the system's Edge, a development-only dependency |
| `dashboard/requirements.txt` | drop `pydeck` |
| `docs/` | ADR 0013; ADR 0005 sentence; README screenshots; architecture and dashboard docs updated |

## 9. Testing

- **Unit tests:**
  - `usual_charge_level`: median, DC sessions excluded, rounding, fewer-than-5 fallback, clamping;
  - the range split: A ≥ B ≥ C, and the parts add up to A;
  - week, month and year cost buckets: sums equal the period total;
  - briefing facts, including the empty-week and no-last-week cases;
  - plug-hour counts;
  - every `components.py` builder escapes its inputs (a test injects `<script>`);
  - token contrast ratios (section 2.1).
- **Chart builders:** each returns a valid Vega-Lite spec with the expected marks and colours, as the existing tests do.
- **App smoke test:** `AppTest` runs every page on the demo database without exceptions; the Routes page runs with OSRM stubbed.
- **Privacy:** the existing no-coordinate test still passes. The map component receives route geometry only on the Routes page, which already handles it.
- **Visual check:** `capture_screenshots.py` screenshots of all six pages at 1400 px wide, compared by eye with the mockups before merging. One mobile-width pass (390 px) checks that cards stack and nothing scrolls sideways.
- **Pi:** the redesigned dashboard is deployed to the Pi and opened over Tailscale. First load must stay within today's time, because MapLibre and the fonts are local.

## 10. Out of scope

- A dark theme (section 2.4).
- Changes to the model, the collector or the data foundation, beyond the 7-day forecast fields.
- Alerts or notifications (the owner declined phone alerts).
- An LLM-written briefing. Briefing and tips are fixed templates over computed facts.
