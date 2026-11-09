# Dashboard redesign "Morning" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Windrose Streamlit dashboard in the approved "Morning" identity: a light theme, top navigation, six redesigned pages, the range rule, and a MapLibre map on OpenFreeMap.

**Architecture:**
- Streamlit stays. Colours live in a new `dashboard/theme.py` token module.
- Custom sections are HTML strings from a new `dashboard/components.py` (no Streamlit import, unit-tested), rendered with `st.html`.
- Charts stay Altair, restyled through `charts.house()`. The map becomes an HTML component built by `dashboard/map.py`.
- New data logic lives in the query and forecast layers, so pages stay thin.

**Tech Stack:** Python 3.13, uv, Streamlit ≥ 1.50, Altair 5, DuckDB, pandas, MapLibre GL JS (vendored, pinned), OpenFreeMap vector tiles, pytest, Playwright (development only, for screenshots).

**Spec:** `docs/superpowers/specs/2026-11-09-morning-redesign-design.md`. Read it first. Mockups: the "Final · K Morning" row of the design canvas, claude.ai artifact `Sww2XAH5cnEsi2GrWJL7Vu`. Where they disagree, the spec wins.

## Global Constraints

- **Theme:** light only. `.streamlit/config.toml` has `base = "light"` and no `[theme.dark]`.
- **Tokens, exact values:**

  | Token | Value |
  |---|---|
  | `SKY_TOP` | `#E4EEF7` |
  | `PAPER` | `#F4F7FA` |
  | `CARD` | `#FFFFFF` |
  | `INK` | `#1D2B3A` |
  | `INK_SOFT` | `#44525F` |
  | `MUTED` | `#5F6E7E` (the spec's `#6F7E8E` measures about 4.15 : 1 on white, below AA for caption text, so it is darkened slightly) |
  | `RULE` | `#E2E8EF` |
  | `WASH` | `#EDF2F7` |
  | `CORAL` | `#E07A73` |
  | `CORAL_INK` | `#B4463E` |
  | `SKY` | `#4A90C2` |
  | `SKY_INK` | `#2F6E9A` |
  | `SUN` | `#F2C14E` |
  | `PALE` | `#C8D8E8` |
  | `TINT_CORAL` | `#FDF0EE` |
  | `TINT_SKY` | `#EAF3FA` |
  | `TINT_SUN` | `#FEF6E4` |
  | `TINT_GREEN` | `#E8F4EC` |

- **Colour rules:**
  - Coloured text uses `CORAL_INK` or `SKY_INK` (≥ 4.5 : 1 on `CARD` and `PAPER`).
  - `CORAL` and `SKY` are for fills and display numbers of 24 px or more (≥ 3 : 1).
  - Every chart and component uses a token, never a raw hex.
- **Type:**
  - Young Serif (display) and Hanken Grotesk 400/500/600 (text), self-hosted in `src/kiatracker/dashboard/static/`.
  - No request to Google Fonts or any font CDN.
  - Inter and Space Grotesk are removed.
- **Shape:**
  - Cards: radius 24 px, no border, shadow `0 1px 2px rgba(29,43,58,0.04), 0 8px 24px rgba(29,43,58,0.05)`.
  - Inputs and chips: radius 14 px. Pills and switches: fully rounded. Bar ends: radius 6.
- **Headlines:**
  - Statement headlines only on the Overview.
  - Every other page renders `components.hidden_title(name)` first, then content.
- **Voice:** second person, no exclamation marks, units on every number, and "likely lo–hi" wherever an interval exists.
- **Money:** forint amounts in the savings section are rounded to 100 Ft. Hungary (Ft) is the primary currency.
- **Range rule:**
  - Today starts from the latest SoC.
  - Later days start from `usual_charge_level` (spec §7): the median end % of the last 20 sessions with `avg_kw <= 22`, rounded to 5. With fewer than 5 sessions it falls back to 80, marked assumed. It is clamped to ≥ the latest SoC and ≤ 100.
  - The "How far a full battery goes" grid and the What-if card stay at 100 %.
- **Privacy:**
  - No coordinates leave the query layer, except route geometry on the Routes page.
  - The map tile host is `tiles.openfreemap.org` only.
  - README screenshots come from demo mode only.
  - Nothing personal goes in the repo: no VIN, home coordinates, Pi IP or tailnet name.
- **Every HTML builder** escapes every interpolated value with `html.escape`.
- **Commits:** conventional commit messages ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Run `uv run pytest -q` and `uv run ruff check .` before each commit.

## Review Focus

Spec-implied inputs that no happy-path test covers, most likely first. Each one has a test in the task named.

1. **A brand-new or empty personal database** (no sessions, no drives in the last 7 days, no forecast). Every page renders with one-line empty states and no exception. Test: `test_every_page_renders_on_an_empty_database`, Task 2.
2. **Unusual charging history.** Only DC fast charges, fewer than 5 sessions, or a latest SoC above the usual level (just charged to 100 % for a trip). The usual level falls back to 80 % marked assumed, or clamps to the latest SoC. Tests in Task 5.
3. **A short or patchy forecast** (3 days of data, missing hours, null wind direction or cloud). The outlook returns the days it can and the rows render without gaps or crashes. Tests in Task 5.
4. **Markup in user text** (a typed place name or zone label containing `<script>` or `&`). It is shown literally. Tests in Task 3 and Task 11.
5. **Map tiles unreachable** (Pi offline, OpenFreeMap down). The tracks still draw on a plain `PAPER` background with a one-line notice. Test: `test_map_html_has_tile_error_fallback`, Task 12.

---

## File map

| File | Responsibility |
|---|---|
| `src/kiatracker/dashboard/theme.py` (new) | token constants, `contrast()` |
| `src/kiatracker/dashboard/components.py` (new) | HTML builders for every custom section; pure functions |
| `src/kiatracker/dashboard/map.py` (new) | `map_html()`: MapLibre page for the Routes map |
| `src/kiatracker/dashboard/ui.py` | CSS (cards, gradient, nav, switches, sliders), `card()` container helper, demo strip, `render_html()`; `page_header` and `tiles` removed when no page uses them |
| `src/kiatracker/dashboard/charts.py` | `house()` restyled on tokens; new `plug_hours`, `savings_bars`, `drives_over_year`, `monthly_use`, `weekly_distance`, `route_heights`, `route_difference`; `grouped_bar` and `bar_with_interval` removed |
| `src/kiatracker/dashboard/queries.py` | `usual_charge_level`, `plug_hours`, `savings`, `briefing_facts`, `recent_drives`, `tips_facts` |
| `src/kiatracker/forecast/outlook.py` | 7 days; daily min/max, direction, sky; per-day start SoC; cold and wind split |
| `src/kiatracker/db.py`, `src/kiatracker/synthetic.py` | forecast cloud and rain fields |
| `src/kiatracker/route_energy.py` | `win_shares()` |
| `src/kiatracker/dashboard/views/*.py` | pages rebuilt to spec §5 |
| `src/kiatracker/dashboard/app.py` | top navigation, period popover, demo strip |
| `scripts/make_map_style.py` (new) | generates `static/map-style.json` |
| `scripts/capture_screenshots.py` (new) | light README screenshots |

---

### Task 1: Theme tokens, fonts and config

**Files:**
- Create: `src/kiatracker/dashboard/theme.py`
- Create: `src/kiatracker/dashboard/static/young-serif.woff2`
- Create: `src/kiatracker/dashboard/static/hanken-grotesk-var.woff2`
- Modify: `src/kiatracker/dashboard/static/FONTS-LICENSE.md`
- Delete: `src/kiatracker/dashboard/static/inter-var.woff2`
- Delete: `src/kiatracker/dashboard/static/space-grotesk-var.woff2`
- Modify: `.streamlit/config.toml`
- Test: `tests/dashboard/test_theme.py`

**Interfaces:**
- Produces:
  - `theme.py` constants: every token in Global Constraints, with the same names.
  - `theme.contrast(fg: str, bg: str) -> float`: WCAG 2.1 contrast ratio of two `#RRGGBB` colours.
  - `theme.SERIF = "Young Serif"` and `theme.SANS = "Hanken Grotesk"`.

- [ ] **Step 1: Replace `test_both_light_and_dark_themes_are_defined` and add contrast tests**

```python
def test_light_theme_only():
    theme = tomllib.loads(CONFIG.read_text(encoding="utf-8"))["theme"]
    assert theme["base"] == "light" and "dark" not in theme
    assert theme["font"] == "Hanken Grotesk" and theme["headingFont"] == "Young Serif"

def test_contrast_matches_wcag_reference():
    assert round(theme.contrast("#000000", "#FFFFFF"), 1) == 21.0
    assert round(theme.contrast("#777777", "#FFFFFF"), 2) == 4.48

def test_text_inks_pass_aa_and_fills_pass_large_text():
    for ink in (theme.INK, theme.INK_SOFT, theme.MUTED, theme.CORAL_INK, theme.SKY_INK):
        for bg in (theme.CARD, theme.PAPER):
            assert theme.contrast(ink, bg) >= 4.5, ink
    for fill in (theme.CORAL, theme.SKY):
        assert theme.contrast(fill, theme.CARD) >= 3.0  # fills and ≥24 px numbers only; see spec 2.1

def test_fonts_are_self_hosted():
    text = CONFIG.read_text(encoding="utf-8")
    assert "googleapis" not in text and "app/static/young-serif.woff2" in text
```

Keep `test_no_folder_named_pages_next_to_the_app`. Replace `test_chart_ink_is_readable…` with an import-only check that `charts.MUTED == theme.MUTED` (Task 4 makes it pass; mark it `xfail(strict=True)` here and remove the mark in Task 4).

- [ ] **Step 2: Run the tests and see them fail**

Run `uv run pytest tests/dashboard/test_theme.py -q`. Expected: FAIL on the missing `theme` module and the config assertions.

- [ ] **Step 3: Implement `theme.py`, add the fonts, and rewrite `[theme]` in config.toml**

- **`contrast`:** relative luminance with the sRGB channel formula, `(L1 + 0.05) / (L2 + 0.05)` with the larger luminance on top.
- **Fonts:** download Young Serif and Hanken Grotesk (variable, wght 100–900) from the Google Fonts GitHub repository (`github.com/google/fonts`, `ofl/youngserif` and `ofl/hankengrotesk`) as woff2. Convert with `fonttools` if only TTF is available. Append both OFL notices to `FONTS-LICENSE.md`.
- **Config values:**
  - `base = "light"`, `font = "Hanken Grotesk"`, `headingFont = "Young Serif"`, `headingFontWeights = [400,400,400,400,400,400]`.
  - `primaryColor = INK`, `backgroundColor = PAPER`, `secondaryBackgroundColor = WASH`, `textColor = INK`, `borderColor = RULE`.
  - `baseRadius = "14px"`.
  - `chartCategoricalColors = [CORAL, SKY, PALE, SUN, SKY_INK, CORAL_INK]`.
  - Two `[[theme.fontFaces]]` entries pointing at `app/static/…`.

- [ ] **Step 4: Run the tests and see them pass**

Run `uv run pytest tests/dashboard/test_theme.py -q`. Expected: PASS, with the one xfail.

- [ ] **Step 5: Commit**

```bash
git add -A src/kiatracker/dashboard/theme.py src/kiatracker/dashboard/static .streamlit/config.toml tests/dashboard/test_theme.py
git commit -m "feat(dashboard): Morning theme tokens, self-hosted Young Serif and Hanken Grotesk"
```

---

### Task 2: Shell (top navigation, period popover, card CSS, demo strip)

**Files:**
- Modify: `src/kiatracker/dashboard/ui.py`
- Modify: `src/kiatracker/dashboard/app.py`
- Create: `src/kiatracker/dashboard/static/windrose-sun.svg`
- Test: `tests/dashboard/test_app.py`

**Interfaces:**
- Consumes: `theme` tokens (Task 1).
- Produces:
  - `ui.card(key: str, *, tint: str | None = None) -> DeltaGenerator`: `st.container(key=f"card-{key}")`. The CSS gives every `.st-key-card-*` the card look; `tint` sets a background token through a second key class `card-tint-<name>`, where name is one of `coral`, `sky`, `sun`, `warm`.
  - `ui.render_html(markup: str) -> None`: wraps `st.html`.
  - `ui.demo_strip(text: str) -> None`.
  - `ui.period_control(default_days: int) -> Period`: a popover labelled with the span ("This year", "Last 30 days", or "3 Mar – 9 Nov") holding the date input.
  - `app.PAGES` unchanged in content. Navigation via `st.navigation(pages, position="top")`.

- [ ] **Step 1: Update the app tests**

In `test_without_opt_in_the_app_shows_demo`, replace the `at.info` and `at.title` assertions:

```python
    html = " ".join(str(h.proto) for h in at.get("html"))  # st.html elements; adjust the accessor if AppTest names them differently
    assert "Simulated data" in html
    assert not at.sidebar.children  # no sidebar any more
```

Add:

```python
@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_on_an_empty_database(page, tmp_path):
    from kiatracker.config import Settings
    from kiatracker.db import build_database
    settings = Settings(None, None, tmp_path, home=None)
    build_database(settings)
    at = run_page(page, settings.db_path)
    assert not at.exception
```

- [ ] **Step 2: Run the tests and see them fail**

Run `uv run pytest tests/dashboard/test_app.py -q`. Expected: the demo test fails (the banner is still `st.info`, and the sidebar has children). The empty-database cases may already pass or fail. Record which pages fail: those are the empty states later tasks must keep green.

- [ ] **Step 3: Implement the shell**

- **CSS in `ui.STYLE`, built from tokens:**
  - `stApp` background `linear-gradient(180deg, SKY_TOP 0px, PAPER 520px)`.
  - `.st-key-card-*` with radius, shadow and 26 px padding; the tint classes.
  - Top navigation as a rounded pill bar: the active link white with a shadow, inactive links in `MUTED`.
  - `stSegmentedControl` as a `WASH` pill with a white active segment.
  - Slider track in `WASH`, fill in `SKY`, a white thumb with a shadow.
  - Hide the sidebar collapse control.
- **`app.main`:**
  - Delete `sidebar_brand` and the sidebar date input.
  - Call `st.logo(windrose-sun.svg)` and set the page title.
  - Show `ui.demo_strip(demo_banner(...))` in demo mode.
  - Compute `period = ui.period_control(default_days)` once and pass it to every page as now. The popover renders on every page; Range and Routes ignore the period.
- **Logo:** `windrose-sun.svg` is the 30×30 sun from the mockup: a circle of radius 7 in `SUN` plus four rays.

- [ ] **Step 4: Run the tests and see them pass**

Run `uv run pytest tests/dashboard -q`. Expected: PASS. Fix empty-state crashes the new test exposes, in the page where they occur, with `empty(...)`.

- [ ] **Step 5: Look at it**

Run `uv run kiatracker dashboard --demo`. Expected: the gradient background, the top pill navigation, the popover on the right, and the demo strip. Screenshot it for the review.

- [ ] **Step 6: Commit**

```bash
git commit -am "feat(dashboard): top navigation, period popover, card styling and demo strip"
```

---

### Task 3: Components module (shared HTML builders)

**Files:**
- Create: `src/kiatracker/dashboard/components.py`
- Test: `tests/dashboard/test_components.py`

**Interfaces:**
- Consumes: `theme` (Task 1).
- Produces (every function returns `str`, never calls Streamlit, and escapes every argument; the module does `from kiatracker.dashboard import theme`, and tests reach the tokens as `components.theme`; `charts.py` does the same):
  - `hidden_title(name: str)`: an `<h1>` hidden with the clip pattern.
  - `section_title(title: str, note: str = "")`: Young Serif 24 px title, with an optional muted note on the right.
  - `stat_strip(items: list[tuple[str, str, str | None]])`: label, value, note cells divided by `RULE`, in a card.
  - `icon_list(items: list[tuple[str, str, str]])`: rows of an icon chip (icon, tint token) and body text. Used by tips and "what it has learned".
  - `chip(text: str, tone: Literal["coral", "sky"])`: a rounded tag, tint background, ink text.
  - `fmt_ft(value: float) -> str`: rounds to 100 and uses a thin space as the thousands separator, `"60 200 Ft"`.
  - `SKY_ICONS = {"sun": "☀", "part": "⛅", "cloud": "☁", "rain": "☂"}`.

- [ ] **Step 1: Write the tests**

```python
def test_every_builder_escapes_markup():
    evil = "<script>x</script> & co"
    for out in (components.section_title(evil, evil), components.stat_strip([(evil, evil, evil)]),
                components.icon_list([("❄", components.theme.TINT_SKY, evil)]), components.chip(evil, "sky"),
                components.hidden_title(evil)):
        assert "<script>" not in out and "&lt;script&gt;" in out and "&amp; co" in out

def test_fmt_ft_rounds_to_hundreds():
    assert components.fmt_ft(60176.4) == "60 200 Ft" and components.fmt_ft(49) == "0 Ft"

def test_stat_strip_has_one_cell_per_item():
    out = components.stat_strip([("Drives", "412", "this year"), ("Distance", "26 418 km", None)])
    assert out.count('class="wr-stat"') == 2 and "this year" in out
```

- [ ] **Step 2: Run the tests and see them fail**

Run `uv run pytest tests/dashboard/test_components.py -q`. Expected: FAIL (module missing).

- [ ] **Step 3: Implement the builders**

Use the class names `wr-stat`, `wr-card`, `wr-chip`, `wr-title`, styled in `ui.STYLE` (add them there), so the HTML carries classes, not inline colours. Exceptions are the data-driven widths and shades in later builders.

- [ ] **Step 4: Run the tests and see them pass**

Run `uv run pytest tests/dashboard/test_components.py -q`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kiatracker/dashboard/components.py src/kiatracker/dashboard/ui.py tests/dashboard/test_components.py
git commit -m "feat(dashboard): escaped HTML components for the Morning sections"
```

---

### Task 4: Chart house style on tokens

**Files:**
- Modify: `src/kiatracker/dashboard/charts.py`
- Test: `tests/dashboard/test_charts.py`
- Test: `tests/dashboard/test_theme.py` (remove the xfail)

**Interfaces:**
- Consumes: `theme`.
- Produces:
  - `charts.BLUE`, `ORANGE` and `AQUA` are replaced by `charts.SKY = theme.SKY`, `charts.CORAL = theme.CORAL` and `charts.PALE = theme.PALE`.
  - `charts.MUTED = theme.MUTED`.
  - `charts.ROUTE_COLOURS = [CORAL, SKY, PALE, SUN, SKY_INK]`.
  - `charts.CAUSE_COLOURS`: eight token-derived colours, ordered as `CAUSES`.
  - `house(chart)`: font `Hanken Grotesk`, no chart titles (`configure_title(fontSize=0)` is not allowed; builders take `title=None`), grid `RULE` solid at opacity 1, labels `MUTED` 12 px, bars `cornerRadiusEnd=6`.
  - Every builder keeps its signature, except that `title` becomes optional (`title: str | None = None`).

- [ ] **Step 1: Update the tests**

Replace `charts.BLUE` with `charts.SKY` in `test_bar_has_tooltip_one_axis_and_brand_color`. Add:

```python
def test_house_uses_tokens_and_no_title():
    spec = charts.bar(DF, "week:T", "km:Q", None, "km").to_dict()
    assert spec["config"]["font"] == "Hanken Grotesk" and "title" not in spec
    assert spec["config"]["axis"]["gridColor"] == charts.theme.RULE
```

- [ ] **Step 2: Run the tests and see them fail**

Run `uv run pytest tests/dashboard/test_charts.py tests/dashboard/test_theme.py -q`. Expected: FAIL.

- [ ] **Step 3: Restyle `house()` and the palette; make `title` optional in every builder (`alt.Chart(df)` when None)**

- [ ] **Step 4: Run the whole dashboard suite**

Run `uv run pytest tests/dashboard -q`. Expected: PASS, and the theme xfail now passes, so remove its mark.

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(dashboard): Altair house style on Morning tokens"
```

---

### Task 5: The range rule, 7-day forecast and sky icons

**Files:**
- Modify: `src/kiatracker/forecast/outlook.py`
- Modify: `src/kiatracker/db.py` (`ForecastHour`, `forecast_hours`)
- Modify: `src/kiatracker/synthetic.py` (`write_forecast` and the `DayWeather.hourly` keys)
- Modify: `src/kiatracker/dashboard/queries.py`
- Test: `tests/forecast/test_outlook.py`
- Test: `tests/dashboard/test_queries.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Produces:
  - `outlook.HOURLY = "temperature_2m,wind_speed_10m,wind_direction_10m,wind_gusts_10m,cloud_cover,precipitation_probability"`. `fetch_forecast` uses `"forecast_days": 7`.
  - `ForecastHour` gains `cloud_pct: float | None` and `rain_prob_pct: float | None`, read from `cloud_cover` and `precipitation_probability`, None when absent.
  - `outlook.sky(cloud_pct: float | None, rain_prob_pct: float | None) -> str`: one of `"rain"` (rain ≥ 50), `"cloud"` (cloud ≥ 70), `"part"` (cloud ≥ 30), `"sun"`. Missing values count as 0.
  - `queries.UsualCharge(level: int, sessions: int, at_level: int, assumed: bool)`, a dataclass.
  - `queries.usual_charge_level(con, latest_soc: float | None) -> UsualCharge`, as in Global Constraints. `at_level` counts sessions whose rounded end equals `level`.
  - `outlook.daily_outlook(hourly, model, soc_today, usual_soc, capacity_kwh, speed_kph, today) -> list[dict]`. Each row has these keys:
    - `day`, `temp_c` (daytime mean), `temp_min`, `temp_max`, `wind_kph`, `wind_dir_deg` (circular mean), `sky`;
    - `start_soc`: `soc_today` for today, `usual_soc` otherwise;
    - `range_lo`, `range_km`, `range_hi`;
    - `lost_cold_km`, `lost_wind_km`, `mild_km` (the A value).
  - `hourly` dicts carry `wind_direction_10m`, `cloud_cover` and `precipitation_probability` when present. `views/range.forecast_hourly` returns them.

- [ ] **Step 1: Write the outlook and usual-level tests**

```python
def test_today_uses_live_soc_later_days_the_usual(demo_model, hourly7):
    rows = daily_outlook(hourly7, demo_model, 76, 80, 78.0, 62, TODAY)
    assert rows[0]["start_soc"] == 76 and {r["start_soc"] for r in rows[1:]} == {80}
    assert len(rows) == 7

def test_cold_and_wind_split_adds_up(demo_model, hourly7):
    for r in daily_outlook(hourly7, demo_model, 76, 80, 78.0, 62, TODAY):
        assert r["mild_km"] >= r["range_km"] - 1e-6
        assert r["lost_cold_km"] >= 0 and r["lost_wind_km"] >= 0
        assert abs(r["mild_km"] - r["lost_cold_km"] - r["lost_wind_km"] - r["range_km"]) < 1e-6

def test_short_patchy_forecast_gives_the_days_it_can(demo_model, hourly7):
    patchy = {k: v[: 3 * 24] for k, v in hourly7.items()}
    patchy["wind_direction_10m"] = [None] * len(patchy["time"])
    rows = daily_outlook(patchy, demo_model, 76, 80, 78.0, 62, TODAY)
    assert 1 <= len(rows) <= 3 and all(r["wind_dir_deg"] is None for r in rows)

def test_sky_rules():
    assert sky(10, 60) == "rain" and sky(80, 0) == "cloud" and sky(40, None) == "part" and sky(None, None) == "sun"
```

`hourly7` is a new fixture in `tests/forecast/conftest.py`: 7 × 24 hours from `TODAY` midnight UTC, with temperature `2 + 6·sin`, wind 14, direction 270, cloud 50, rain 10. `demo_model` is the existing model fixture; reuse it if present, otherwise build one from `prior_coefficients`.

In `tests/dashboard/test_queries.py`, using the `tiny` factory pattern to insert sessions:

```python
def test_usual_level_is_median_of_slow_sessions_rounded(sessions_db):
    con = sessions_db(ends=[79, 80, 81, 80, 78, 100], kw=[7.4] * 6 + [] )
    u = queries.usual_charge_level(con, latest_soc=40)
    assert (u.level, u.assumed) == (80, False) and u.at_level == 4

def test_dc_sessions_are_ignored_and_few_sessions_fall_back(sessions_db):
    con = sessions_db(ends=[100, 100, 90, 80], kw=[96, 88, 7.4, 7.4])
    u = queries.usual_charge_level(con, latest_soc=40)
    assert (u.level, u.assumed) == (80, True)

def test_usual_level_never_below_latest_reading(sessions_db):
    con = sessions_db(ends=[80] * 6, kw=[7.4] * 6)
    assert queries.usual_charge_level(con, latest_soc=95).level == 95
```

`sessions_db` is a new factory fixture in `tests/dashboard/conftest.py`. It builds an empty database (as the `empty` fixture does) and inserts `charging_sessions` rows with consecutive start times, the given `soc_end` and `avg_kw`, and `soc_start` 30.

In `tests/test_db.py`: `forecast_hours` reads `cloud_cover` and `precipitation_probability`, and gives None when they are missing.

- [ ] **Step 2: Run the tests and see them fail**

Run `uv run pytest tests/forecast/test_outlook.py tests/dashboard/test_queries.py tests/test_db.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement**

- **`daily_outlook`:** evaluate `range_interval` three times per day at `start_soc`: A = (20 °C, 0 wind), B = (day temperature, 0 wind), C = (day temperature, day wind). Then `lost_cold_km = max(0, A−B)` and `lost_wind_km = max(0, B−C)`, with the interval from C.
  - If A < C because of model noise, set `mild_km = C + lost_cold + lost_wind`, so the parts always add up.
  - Document the cold-first order in the docstring.
- **Wind direction:** circular mean via the mean of sin and cos; None if every value is None.
- **Synthetic demo:** `DayWeather.hourly` emits `cloud_cover` (seasonal, 20–85) and `precipitation_probability` (0–70), so the demo shows varied icons. Keep it deterministic from the seed.
- **Callers:** update every caller of `daily_outlook`. The range view is rewritten in Task 6; for now pass `soc, usual.level`.

- [ ] **Step 4: Run the full suite**

Run `uv run pytest -q`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(forecast): 7-day outlook from today's charge then the usual level, with cold and wind split"
```

---

### Task 6: Range page

**Files:**
- Modify: `src/kiatracker/dashboard/views/range.py`
- Modify: `src/kiatracker/dashboard/components.py`
- Modify: `src/kiatracker/forecast/model.py` (`explain_items`)
- Test: `tests/dashboard/test_components.py`
- Test: `tests/forecast/test_model.py`

**Interfaces:**
- Consumes: `daily_outlook` and `usual_charge_level` (Task 5); `stat_strip`, `section_title`, `icon_list` and `hidden_title` (Task 3).
- Produces:
  - `components.forecast_rows(rows: list[dict], scale_km: float) -> str`: one row per outlook dict (Task 5 keys).
    - Left column: the day label ("Today" for index 0, else a weekday abbreviation) and "from N %".
    - Weather column: the sky icon, `temp_min–temp_max °C`, and a wind arrow rotated `wind_dir_deg + 180` with the compass label and km/h. The arrow is omitted when the direction is None.
    - The bar: `range_km` in `SKY` (`CORAL` for today), then `lost_cold_km` in `TINT_SKY` labelled "−N cold", then `lost_wind_km` in `WASH` labelled "−N" only if ≥ 8. Widths are `km / scale_km`.
    - Right column: the range number and "likely lo–hi". Today's row has the `TINT_CORAL` background.
  - `components.rule_line(soc_today: float, usual: UsualCharge, full: bool) -> str`:
    - **usual, not assumed:** "Today starts from what is in the battery now ({soc_today:.0f} %). The coming days assume you charge as usual: you stopped at {level} % in {at_level} of your last {sessions} charges. Switch to 100 % to plan a road trip."
    - **assumed:** the middle sentence becomes "The coming days assume an 80 % charge until there are enough charging sessions to learn yours."
    - **full:** "Today starts from what is in the battery now ({soc_today:.0f} %). The coming days assume a full charge."
  - `components.whatif_result(lo: float, mid: float, hi: float, best_km: float) -> str`: "On a full battery", the big number, "likely lo–hi km", and a bar of `mid / best_km`.
  - `model.RangeModel.explain_items(speed_kph) -> list[tuple[str, str]]`: (icon, sentence) pairs computed from the coefficients:
    - cold per degree below `T_BASE` ("❄");
    - climb per 100 m and the regen share ("↗");
    - headwind 20 km/h at 110 km/h, in kWh/100 km ("≋");
    - cooling per hour at 30 °C ("☀").

    The existing `explain()` stays for the CLI.

- [ ] **Step 1: Write the tests**

```python
def test_forecast_rows_marks_today_and_split():
    rows = [dict(day=date(2026,11,9), start_soc=76, sky="part", temp_min=2, temp_max=6, wind_kph=14, wind_dir_deg=270,
                 range_km=384, range_lo=352, range_hi=411, lost_cold_km=44, lost_wind_km=12, mild_km=440)]
    out = components.forecast_rows(rows, 490)
    assert "Today" in out and "from 76 %" in out and "−44 cold" in out and "likely 352–411" in out
    assert components.theme.TINT_CORAL in out

def test_forecast_rows_without_direction_has_no_arrow():
    row = dict(day=date(2026,11,10), start_soc=80, sky="sun", temp_min=1, temp_max=8, wind_kph=5, wind_dir_deg=None,
               range_km=420, range_lo=390, range_hi=450, lost_cold_km=30, lost_wind_km=2, mild_km=452)
    assert "rotate(" not in components.forecast_rows([row], 490)

def test_rule_line_variants():
    u = UsualCharge(level=80, sessions=20, at_level=14, assumed=False)
    assert "stopped at 80 % in 14 of your last 20" in components.rule_line(76, u, full=False)
    assert "assume an 80 % charge" in components.rule_line(76, UsualCharge(80, 2, 0, True), full=False)
    assert "full charge" in components.rule_line(76, u, full=True)
```

In `test_model.py`: `explain_items` returns 4 pairs, and the cold sentence contains `f"{coef['cold']:.2f}"`.

- [ ] **Step 2: Run the tests and see them fail**

Run `uv run pytest tests/dashboard/test_components.py tests/forecast/test_model.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement the builders, then rebuild `range.render`**

In this order:
1. `hidden_title("Range")`.
2. The stat strip: Range now (likely, speed), Battery (% and "N of M kWh usable"), Typical error ("per 100 km; temperature alone: X"), Learned from ("N drives", "retrained every night").
3. A card holding the section title "The next seven days, and what each one costs you", the `st.segmented_control(["Usual N %", "Full 100 %"])`, the `rule_line`, `forecast_rows` (scale = max `mild_km` × 1.05) and the wind note.
4. A What-if card: three `st.slider` in a left column, `whatif_result` on the right, with `best_km = EV3.best_range_km`.
5. Predicted vs actual (existing chart, no title) in a card next to an `icon_list(model.explain_items(speed))` card.

Remove the use of `bar_with_interval`; delete the builder from `charts.py` if nothing else uses it.

- [ ] **Step 4: Run the tests and look at the page**

Run `uv run pytest -q` and expect PASS. Then open `/range` in the demo and compare it with the MorningRange mockup.

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(dashboard): Range page in Morning, forecast rows with the usual-charge rule"
```

---

### Task 7: Overview page

**Files:**
- Modify: `src/kiatracker/dashboard/views/overview.py`
- Modify: `src/kiatracker/dashboard/components.py`
- Modify: `src/kiatracker/dashboard/queries.py`
- Modify: `src/kiatracker/dashboard/charts.py`
- Test: `tests/dashboard/test_components.py`
- Test: `tests/dashboard/test_queries.py`
- Test: `tests/dashboard/test_charts.py`

**Interfaces:**
- Consumes: `daily_outlook` and `usual_charge_level` (Task 5); `views.range.cached_train`, `forecast_hourly` and `weather_now`; `icon_list` (Task 3).
- Produces:
  - `components.greeting(local_hour: int) -> str`: "Good morning" (5–11), "Good afternoon" (12–17), "Good evening" (otherwise).
  - `components.hero(greeting_line: str, range_km: float | None, lo, hi, soc, comparison: str | None) -> str`.
    - Range known: "You can drive about <span class=coral-ink>N km</span> today."
    - Range unknown: "Your range appears once the model has enough drives."
  - `components.battery_card(soc: float | None, year_km: float, avg: float | None, saved_ft: float | None) -> str`.
  - `components.week_strip(rows: list[dict]) -> str`: seven columns (day, icon, `temp_max`°, range, "km range"). Today has the `TINT_CORAL` background.
  - `queries.commute_pair(con, period) -> tuple[str, str, float] | None`: the most frequent (start_zone, end_zone) pair among drives with distinct zones, and its median km. It feeds the hero's comparison sentence: "Enough for N round trips to work".
  - `queries.tips_facts(con, period, outlook: list[dict]) -> list[tuple[str, str, str]]`: up to three (icon, tint, sentence), each only when its condition holds (spec §5.1):
    - **cold:** min `temp_min` of the first 3 rows < 5 → "Below 5 °C, pre-heat while plugged in: about {x:.1f} kWh saved on your commute." Here x = 0.8 × commute km / 30, rounded to 0.1.
    - **same route:** among this week's drives, the pair with the same zones and the largest relative consumption difference ≥ 5 % → "{Day}'s {pair} used {p} % less than {other day}'s. Same road, {dT} °C warmer."
    - **home share:** the share of energy charged at zone `home` → "{s} % of your charging happened at home."
  - `charts.monthly_use(df: month, kwh_per_100km) -> Chart`: bars in `PALE`; months more than 10 % above the period's mean in `CORAL`; value labels on top.
  - `charts.weekly_distance(df: week, distance_km) -> Chart`: bars in `PALE`, the last week in `CORAL`.

- [ ] **Step 1: Write the tests**

```python
@pytest.mark.parametrize("hour,expected", [(6, "Good morning"), (12, "Good afternoon"), (21, "Good evening"), (2, "Good evening")])
def test_greeting(hour, expected):
    assert components.greeting(hour) == expected

def test_hero_without_range_says_why():
    assert "enough drives" in components.hero("Good morning.", None, None, None, 76, None)

def test_week_strip_highlights_today_only():
    rows = [dict(day=date(2026,11,9+i), sky="sun", temp_max=6, range_km=384 + i) for i in range(7)]
    out = components.week_strip(rows)
    assert out.count(components.theme.TINT_CORAL) == 1 and "Today" in out

def test_monthly_use_highlights_months_10pct_above_mean():
    df = pd.DataFrame({"month": ["2026-01", "2026-06"], "kwh_per_100km": [21.4, 14.9]})
    assert charts.CORAL in str(charts.monthly_use(df).to_dict())

def test_tips_skip_conditions_that_do_not_hold(demo, all_time):
    warm = [dict(temp_min=12)] * 3
    assert all("pre-heat" not in t for _, _, t in queries.tips_facts(demo, all_time, warm))
```

- [ ] **Step 2: Run the tests and see them fail**

Run `uv run pytest tests/dashboard -q`. Expected: FAIL.

- [ ] **Step 3: Implement, then rebuild `overview.render`**

In this order:
1. A two-column hero (`hero` and `battery_card`).
2. A card: "Range this week, with the forecast" with the note "today from N %, then from your usual M % · typical commute speeds", then `week_strip(daily_outlook(...))`.
3. Two columns: a card with `monthly_use` and "kWh per 100 km · coral months are the cold ones"; a "Worth knowing" card with `icon_list(tips_facts(...))`, hidden when the list is empty.
4. A card with `weekly_distance`.

Saved Ft comes from Task 10's `queries.savings`; until Task 10 lands, take the year total from `queries.costs(...)` (petrol_huf − ev_huf).

- [ ] **Step 4: Run the tests and look at the page**

Run `uv run pytest -q` and expect PASS. Then compare the demo Overview with the MorningOverview mockup.

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(dashboard): Overview in Morning with greeting, week strip and tips"
```

---

### Task 8: Drives page

**Files:**
- Modify: `src/kiatracker/dashboard/views/drives.py`
- Modify: `src/kiatracker/dashboard/components.py`
- Modify: `src/kiatracker/dashboard/queries.py`
- Modify: `src/kiatracker/dashboard/charts.py`
- Test: `tests/dashboard/test_queries.py`
- Test: `tests/dashboard/test_components.py`
- Test: `tests/dashboard/test_charts.py`

**Interfaces:**
- Consumes: `condition_effects` and `drives` (existing); `range_grid` (existing, `forecast/scenarios.py`).
- Produces:
  - `queries.briefing_facts(con, today: date) -> list[tuple[str, str, str, str]]`: (icon, tint, title, sentence), up to three, over the 7 local days ending today, compared with the 7 before:
    - **"Cold costs you most"** (or whichever factor has the largest `pct` among `enough` rows): "{pct:.0%} more energy {harder_label} than {easier_label}. {n} of this week's {total} drives were {harder_label}."
    - **"A better week" or "A harder week"** (by the sign of the change; only when both weeks have measured drives): "{n} drives, {km:.0f} km at {kwh:.1f} kWh/100 km: {abs(change):.0%} {less|more} than last week."
    - **"Best drive":** the lowest kWh/100 km among this week's drives of 5 km or more: "{weekday}'s drive from {start_zone} to {end_zone}: {kwh:.1f} kWh/100 km at {temp:.0f} °C."
  - `components.briefing(facts, date_label: str) -> str`: the warm-tinted card, "Your briefing", and "{date_label} · from the last 7 days". With no facts it says "No drives in the last 7 days."
  - `components.effect_rows(effects: DataFrame) -> str`: one row per factor, a rounded bar (`CORAL`, or `PALE` when not `enough`), "+N %" and "harder vs easier". Replaces `charts.effect_bars` on this page.
  - `components.range_grid(grid: DataFrame[temp_c, wind_kph, range_km]) -> str`: temperatures as columns, winds as rows ("Calm", "Breezy · 15 km/h", "Windy · 30 km/h"), cells shaded in `SKY` at alpha 0.10–0.65 by range, numbers rounded to 5 km.
  - `queries.recent_drives(con, n: int = 8) -> DataFrame`: the latest drives with columns `day_label` ("Today", "Yesterday", or a weekday name; a date for older drives), `time`, `start_zone`, `end_zone`, `distance_km`, `kwh_per_100km`, `temp_c`, `sky` (from `drive_weather` cloud when present, else None).
  - `components.drive_list(df) -> str`: grouped by `day_label`; the chip is `coral` when kWh/100 ≥ 19, else `sky`; zone labels are capitalised ("Home → Work").
  - `charts.drives_over_year(df[start_local, kwh_per_100km]) -> Chart`: dots (`CORAL` ≥ 19, else `SKY`, opacity 0.55) with a LOESS line in `INK` at opacity 0.6.

- [ ] **Step 1: Write the tests**

```python
def test_briefing_facts_empty_week_gives_nothing(empty):
    assert queries.briefing_facts(empty, date.today()) == []

def test_briefing_skips_comparison_without_last_week(tiny):
    con = tiny()  # two November drives only
    titles = [t for _, _, t, _ in queries.briefing_facts(con, date(2026, 11, 12))]
    assert "A better week" not in titles and "A harder week" not in titles

def test_briefing_card_without_facts():
    assert "No drives in the last 7 days" in components.briefing([], "Monday 9 November")

def test_range_grid_rounds_to_5_and_labels_wind():
    grid = pd.DataFrame({"temp_c": [-10, 20], "wind_kph": [0, 0], "range_km": [323.4, 418.9]})
    out = components.range_grid(grid)
    assert "325" in out and "420" in out and "Calm" in out

def test_drive_list_escapes_zone_names():
    df = pd.DataFrame([dict(day_label="Today", time="07:42", start_zone="<b>home</b>", end_zone="other",
                            distance_km=31.4, kwh_per_100km=18.9, temp_c=4, sky=None)])
    assert "<b>" not in components.drive_list(df)
```

- [ ] **Step 2: Run the tests and see them fail**

Run `uv run pytest tests/dashboard -q`. Expected: FAIL.

- [ ] **Step 3: Implement, then rebuild `drives.render`**

In this order:
1. `hidden_title`, then `briefing`.
2. The stat strip (existing tiles content).
3. A card with "What makes a drive cost more" and `effect_rows`, plus the existing caption, reworded.
4. A card with "How far a full battery goes", the existing speed segmented control, and `range_grid`.
5. A card with "Every drive of the year" and `drives_over_year`.
6. A card with "Recent drives" and `drive_list`.
7. The existing analyst expander, unchanged.

- [ ] **Step 4: Run the tests and look at the page**

Run `uv run pytest -q` and expect PASS. Then compare with the MorningDrives mockup.

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(dashboard): Drives page with briefing, effect rows, range grid and recent drives"
```

---

### Task 9: Charging page

**Files:**
- Modify: `src/kiatracker/dashboard/views/charging.py`
- Modify: `src/kiatracker/dashboard/components.py`
- Modify: `src/kiatracker/dashboard/queries.py`
- Modify: `src/kiatracker/dashboard/charts.py`
- Test: `tests/dashboard/test_queries.py`
- Test: `tests/dashboard/test_components.py`
- Test: `tests/dashboard/test_charts.py`

**Interfaces:**
- Consumes: `charging_sessions` and `weekly_charging` (existing).
- Produces:
  - `queries.plug_hours(con, period) -> DataFrame[hour: int 0–23, sessions: int]`: all 24 hours are present, with zero counts.
  - `charts.plug_hours(df) -> Chart`: bars in `PALE`, except the 4-hour window with the most sessions, which is in `SUN`. The x labels are every 3 h.
  - `components.peak_window(df) -> tuple[int, int, float]`: (start_hour, end_hour_exclusive, share), shared by the chart and the sentence. The sentence reads "{share_words} of your sessions start between {start}:00 and {end}:00. If your tariff has a cheaper night rate, a charging timer for 22:00 would use it." Here share_words is "More than half" when share > 0.5, "About a third" for 0.28–0.4, and otherwise "{share:.0%}".
  - `components.typical_charge(start_median: float, end_median: float) -> str`: the battery bar, labelled "+N % per session, typically", "plug in at S %" and "stop at E %".
  - `components.session_list(df) -> str`: the latest 5 sessions: date, time, zone, a from → to bar (`CORAL` when `avg_kw > 22`, else `SKY`), kWh and kW.
  - `charts.histogram` gains a `colour` parameter (default `SKY`).
  - `charts.bar` gains `highlight_last: bool = False`, which draws the last bar in `CORAL` and the others in `PALE`.

- [ ] **Step 1: Write the tests**

```python
def test_plug_hours_has_all_24_hours(demo, all_time):
    df = queries.plug_hours(demo, all_time)
    assert list(df["hour"]) == list(range(24)) and df["sessions"].sum() == len(queries.charging_sessions(demo, all_time))

def test_peak_window_finds_the_busiest_four_hours():
    df = pd.DataFrame({"hour": range(24), "sessions": [0]*17 + [5, 9, 8, 6] + [0]*3})
    assert components.peak_window(df)[:2] == (17, 21)

def test_session_list_marks_fast_charges():
    df = pd.DataFrame([dict(start_local=pd.Timestamp("2026-10-31 13:22"), zone="other", soc_start=12, soc_end=78,
                            energy_kwh=51.6, avg_kw=96.0)])
    assert components.theme.CORAL in components.session_list(df)
```

- [ ] **Step 2: Run the tests and see them fail**

Run `uv run pytest tests/dashboard -q`. Expected: FAIL.

- [ ] **Step 3: Implement, then rebuild `charging.render`**

In this order:
1. `hidden_title`.
2. The stat strip: Sessions, Energy charged, At home (share of kWh at zone home), Charged to full.
3. A card with "A typical charge" (median session) and `typical_charge`.
4. Two columns with histogram cards ("Battery when you plug in" in `SKY`, "Battery when you stop" in `CORAL`), each with one sentence naming the most common 10 % bins.
5. A card with "When you plug in" and the chart, plus the peak sentence.
6. A card with "Energy charged per week" and `bar(..., highlight_last=True)`.
7. A card with "Latest sessions" and `session_list`.
8. The existing full table in an expander.

- [ ] **Step 4: Run the tests and look at the page**

Run `uv run pytest -q` and expect PASS. Then compare with the MorningCharging mockup.

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(dashboard): Charging page with typical charge, plug-in hours and session list"
```

---

### Task 10: Costs page and savings buckets

**Files:**
- Modify: `src/kiatracker/dashboard/queries.py`
- Modify: `src/kiatracker/dashboard/views/costs.py`
- Modify: `src/kiatracker/dashboard/components.py`
- Modify: `src/kiatracker/dashboard/charts.py`
- Test: `tests/dashboard/test_queries.py`
- Test: `tests/dashboard/test_components.py`
- Test: `tests/dashboard/test_charts.py`

**Interfaces:**
- Consumes: `queries.costs` (existing).
- Produces:
  - `queries.costs(con, period, assume, freq: Literal["week", "month", "year"] = "month")`: the bucket column is renamed from `month` to `bucket`, and `freq` picks `%G-W%V`, `%Y-%m` or `%Y`. Fuel prices are looked up per drive month in every mode (sum per drive, then group), so the totals are identical across `freq`. Update `views/costs.py` and the Overview (Task 7) to use `bucket`.
  - `queries.savings(df) -> DataFrame[bucket, distance_km, ev_huf, petrol_huf, saved_huf, complete: bool]`. `complete` is False for the current, unfinished bucket.
  - `components.savings_figures(row, label: str) -> str`: "Saved in {label}" (big, `CORAL_INK`), "You paid for electricity" (`SKY_INK`) with "{km} km, home charging", and "Petrol would have cost" with the L/100 km note. Money goes through `fmt_ft`.
  - `components.compare_bars(items: list[tuple[str, float, str, str]], unit: Callable[[float], str]) -> str`: the horizontal rounded bars for per 100 km.
  - `charts.savings_bars(df) -> Chart`: one bar per bucket, the last complete bucket in `CORAL` with its "{k}k" label, the others in `PALE` with muted labels.
  - `charts.grouped_bar` is deleted.

- [ ] **Step 1: Write the tests**

```python
@pytest.mark.parametrize("freq", ["week", "month", "year"])
def test_cost_buckets_sum_to_the_same_total(demo, all_time, assume, freq):
    month = queries.costs(demo, all_time, assume, "month")
    other = queries.costs(demo, all_time, assume, freq)
    assert other["petrol_huf"].sum() == pytest.approx(month["petrol_huf"].sum())
    assert other["ev_huf"].sum() == pytest.approx(month["ev_huf"].sum())

def test_current_bucket_is_marked_incomplete(demo, all_time, assume):
    s = queries.savings(queries.costs(demo, all_time, assume, "month"))
    assert not s["complete"].iloc[-1] and s["complete"].iloc[:-1].all()

def test_savings_figures_round_and_colour():
    row = pd.Series(dict(bucket="2026-10", distance_km=2150, ev_huf=14644.0, petrol_huf=74820.0, saved_huf=60176.0, complete=True))
    out = components.savings_figures(row, "October")
    assert "60 200 Ft" in out and components.theme.CORAL_INK in out
```

`assume` is the existing cost-assumptions fixture; create it in `conftest.py` from `CostAssumptions()` defaults if absent.

- [ ] **Step 2: Run the tests and see them fail**

Run `uv run pytest tests/dashboard -q`. Expected: FAIL.

- [ ] **Step 3: Implement, then rebuild `costs.render`**

In this order:
1. `hidden_title`.
2. A card: "Saved compared with a petrol car" with `st.segmented_control(["Week", "Month", "Year"], default="Month")`.
   - Figures for the last complete bucket. Its label is "the week of 2 Nov", "October" or "2025".
   - The last 12 buckets (Year shows all) as `savings_bars`.
   - The caption "Each bar is one {unit}'s saving … Last 12 {units}: {fmt_ft(total)}."
3. A card with "Per 100 km in Hungary" and `compare_bars`, plus the pump-week note.
4. A card with "The same driving in Austria" and `compare_bars` in €.

Keep the existing empty states (no fuel prices, no drives).

- [ ] **Step 4: Run the tests and look at the page**

Run `uv run pytest -q` and expect PASS. Then compare with the MorningCosts mockup.

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(dashboard): Costs page with week, month and year savings"
```

---

### Task 11: Routes page (cards, heights, difference)

**Files:**
- Modify: `src/kiatracker/route_energy.py`
- Modify: `src/kiatracker/dashboard/views/routes.py`
- Modify: `src/kiatracker/dashboard/components.py`
- Modify: `src/kiatracker/dashboard/charts.py`
- Test: `tests/test_route_energy.py`
- Test: `tests/dashboard/test_components.py`
- Test: `tests/dashboard/test_charts.py`

**Interfaces:**
- Consumes: `RouteEstimate` (existing, with `draws` of the same simulated days for every route).
- Produces:
  - `route_energy.win_shares(estimates: list[RouteEstimate]) -> list[float]`: the share of simulated days on which each route uses the least energy. Ties split evenly; the shares sum to 1. When `draws` is None, the lowest `kwh_p50` gets 1.0.
  - `components.route_cards(estimates, shares, colours) -> str`: per route, a dot, the label, "wins {round(100·share)} of 100", "{kwh_p50:.1f} kWh", "{minutes:.0f} min · {km:.0f} km · arrive at {arrival_soc_p50:.0f} %" and "{roads} · climbs {climb_m:.0f} m". Every string is escaped.
  - `charts.route_heights(profile: DataFrame[route, km, height]) -> Chart`:
    - Shared km axis. The first route is a `CORAL` area at opacity 0.16 with a 3 px line, the second a `SKY` area at 0.10 with a 2.5 px line, the rest `PALE` dashed lines.
    - A point and label at the first route's maximum: "+{h:.0f} m · highest point, km {k:.0f}". A label at the second route's maximum: "{label}: never above +{h:.0f} m".
    - Heights stay relative to the start ("m above the start"): the estimate carries no absolute elevation, so the spec's "559 m · Wienerwald" becomes a relative figure without a place name.
  - `charts.route_difference(parts: DataFrame[route, cause, kwh], first: str, second: str) -> Chart`: per cause, kWh(first) − kWh(second) as diverging bars (`CORAL` > 0, `SKY` < 0), labelled ±N.N, with a text mark "Net: {first} uses {abs(net):.1f} kWh {less|more}". Causes with |Δ| < 0.05 are dropped.

- [ ] **Step 1: Write the tests**

```python
def test_win_shares_sum_to_one_and_follow_draws(estimates_with_draws):
    shares = win_shares(estimates_with_draws)
    assert sum(shares) == pytest.approx(1) and shares[0] > shares[1]

def test_win_shares_without_draws_picks_lowest_median(estimates_without_draws):
    assert win_shares(estimates_without_draws) == [0.0, 1.0]

def test_route_cards_escape_typed_names(sample_estimate):
    e = replace(sample_estimate, route=replace(sample_estimate.route, label="<img src=x>", roads="A2 & S6"))
    out = components.route_cards([e], [1.0], ["#E07A73"])
    assert "<img" not in out and "A2 &amp; S6" in out and "wins 100 of 100" in out

def test_route_difference_net_and_signs():
    parts = pd.DataFrame({"route": ["A","A","B","B"], "cause": ["distance","climb","distance","climb"],
                          "kwh": [20.0, 4.0, 22.9, 1.6]})
    spec = str(charts.route_difference(parts, "A", "B").to_dict())
    assert "Net: A uses 0.5 kWh less" in spec
```

Build the estimate fixtures in `tests/test_route_energy.py` from the existing helpers there. `draws` are arrays of shape (n_days,) with route 0 lower on most days.

- [ ] **Step 2: Run the tests and see them fail**

Run `uv run pytest tests/test_route_energy.py tests/dashboard -q`. Expected: FAIL.

- [ ] **Step 3: Implement, then rebuild `routes.render`**

In this order:
1. `hidden_title("Routes")`.
2. The form inside a card. Keep every existing field, and restyle the submit button as the `INK` "Compare" pill.
3. The map: keep `route_map` for now; Task 12 replaces it.
4. `route_cards` in three columns.
5. A card with "Up and down along the way", `route_heights` and the climb sentence. It uses `energy_breakdown` of the first route: "The climb costs about {climb:.1f} kWh; rolling down gives {regen:.1f} back."
6. A card with "Why they end up even", `route_difference` of the first two routes, and one callout sentence from `differences(...)[0]`.
7. The "How this is calculated" expander, unchanged.

Remove the `st.dataframe` table and the "Energy used along the way" chart; the cards and the difference chart carry that information.

- [ ] **Step 4: Run the tests and look at the page**

Run `uv run pytest -q` and expect PASS. Then run the default comparison in the demo and compare it with the MorningRoutes mockup (cards, heights, difference).

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(routes): route cards with win odds, height profile and cause-by-cause difference"
```

---

### Task 12: Map on MapLibre and OpenFreeMap

**Files:**
- Create: `scripts/make_map_style.py`
- Create: `src/kiatracker/dashboard/static/map-style.json` (generated, committed)
- Create: `src/kiatracker/dashboard/static/maplibre/maplibre-gl.js`, `maplibre-gl.css` and `LICENSE.txt` (v4.7.1)
- Create: `src/kiatracker/dashboard/map.py`
- Create: `docs/decisions/0013-maplibre-openfreemap.md`
- Modify: `docs/decisions/0005-privacy-by-construction.md`
- Modify: `docs/decisions/README.md`
- Modify: `src/kiatracker/dashboard/views/routes.py`
- Modify: `src/kiatracker/dashboard/requirements.txt` (drop pydeck)
- Test: `tests/dashboard/test_map.py`

**Interfaces:**
- Consumes: `theme` tokens; `charts.ROUTE_COLOURS`.
- Produces:
  - `scripts/make_map_style.py`: fetches `https://tiles.openfreemap.org/styles/positron` and recolours paint properties by layer id:
    - `background` → `PAPER`;
    - `water` and `waterway` → `#C7DDF0`;
    - `park` → `#E1ECDD`;
    - `landcover_wood` → `#D8E6D3`;
    - `landuse_residential` and `building` → `#EBEFF3`;
    - `highway_minor` and `highway_path` → `#E1E6EC`;
    - `highway_major*` and boundaries → `#CCD6E0`;
    - `highway_motorway*` inner → `#AFC0D1`, casing → `#CCD6E0`;
    - `railway*` → `#D3DAE2`;
    - every symbol: `text-color` → `INK`, `text-halo-color` → `PAPER`, `text-halo-width` 1.6.

    It writes `static/map-style.json`. These map-only colours live in the script as a `MAP_COLOURS` dict next to the tokens. They are basemap shades, not UI tokens.
  - `map.map_html(routes: list[dict], *, height: int = 560) -> str`: a full HTML page. Each route dict has `label`, `colour` and `coords` (`[[lon, lat], …]`); the first route is the chosen one.
    - Loads `app/static/maplibre/maplibre-gl.js` and `.css`, and the style from `app/static/map-style.json`.
    - Fits the bounds of all coordinates with 40 px padding.
    - Adds each route below the first symbol layer as a white casing (width + 4) and a coloured line (6 px for the chosen route, 4 px for others), drawn others first, chosen last.
    - Start and end circles.
    - A hover popup with the route label.
    - An `error` listener: on a tile or style failure it sets the background to `PAPER`, keeps the GeoJSON layers (re-adding them to a blank style if the style failed), and shows "Map tiles unavailable; showing the routes only."
    - A visible attribution: "© OpenStreetMap contributors · OpenFreeMap".
    - The route data is embedded with `json.dumps`, and the labels are escaped for the popup through `textContent`, never `innerHTML`.

- [ ] **Step 1: Write the tests**

```python
def test_map_html_embeds_routes_and_attribution():
    out = map_html([{"label": "Fastest", "colour": "#E07A73", "coords": [[15.6, 48.4], [16.2, 47.8]]}])
    assert "app/static/maplibre/maplibre-gl.js" in out and "map-style.json" in out
    assert "© OpenStreetMap contributors · OpenFreeMap" in out and "[15.6, 48.4]" in out

def test_map_html_has_tile_error_fallback():
    out = map_html([{"label": "A", "colour": "#000000", "coords": [[0, 0], [1, 1]]}])
    assert "on('error'" in out and "Map tiles unavailable; showing the routes only." in out

def test_route_labels_never_reach_innerhtml():
    out = map_html([{"label": "</script><script>alert(1)</script>", "colour": "#000000", "coords": [[0, 0], [1, 1]]}])
    assert "</script><script>" not in out and "innerHTML" not in out

def test_committed_style_only_uses_openfreemap_tiles():
    style = json.loads((STATIC / "map-style.json").read_text(encoding="utf-8"))
    urls = [s.get("url", "") for s in style["sources"].values()] + [style.get("glyphs", ""), style.get("sprite", "")]
    assert all(u.startswith("https://tiles.openfreemap.org") for u in urls if u)
```

To keep a closing script tag in a label inert, embed the JSON with `<`, `>` and `&` replaced by `<`, `>` and `&`.

- [ ] **Step 2: Run the tests and see them fail**

Run `uv run pytest tests/dashboard/test_map.py -q`. Expected: FAIL.

- [ ] **Step 3: Vendor MapLibre, generate the style, implement `map.py`, and switch `routes.route_map`**

- **Vendoring:** download `maplibre-gl@4.7.1/dist/maplibre-gl.js` and `maplibre-gl.css` from `https://unpkg.com/` and its `LICENSE.txt` from the GitHub tag `v4.7.1`.
- **Style:** run `uv run python scripts/make_map_style.py`.
- **Routes view:** `route_map` calls `st.components.v1.html(map_html(...), height=560)` inside a card, with route colours from `ROUTE_COLOURS` in estimate order. Remove the `pydeck` import.

- [ ] **Step 4: Write ADR 0013 and update ADR 0005 and the decisions index**

- **ADR 0013:** context (CARTO now needs a key; pydeck draws over labels), decision (vendored MapLibre and OpenFreeMap with a recoloured committed style), consequences (tiles from openfreemap.org, viewport only; offline fallback).
- **ADR 0005:** one sentence naming OpenFreeMap as the tile host.

- [ ] **Step 5: Run the tests and look at the map**

Run `uv run pytest -q` and expect PASS. Then, in the demo, run the default comparison:
- the map shows towns, roads and the Danube in the Morning colours;
- town names sit above the tracks;
- hovering a track shows its name.

Then block `tiles.openfreemap.org` (browser devtools request blocking) and reload: the tracks and the notice appear.

- [ ] **Step 6: Commit**

```bash
git add -A scripts/make_map_style.py src/kiatracker/dashboard/static src/kiatracker/dashboard/map.py src/kiatracker/dashboard/views/routes.py src/kiatracker/dashboard/requirements.txt docs/decisions tests/dashboard/test_map.py
git commit -m "feat(routes): MapLibre map on recoloured OpenFreeMap tiles, labels above the tracks"
```

---

### Task 13: Screenshots, docs and Pi deployment

**Files:**
- Create: `scripts/capture_screenshots.py`
- Modify: `pyproject.toml` (a `dev` dependency group gains `playwright`)
- Modify: `docs/images/*.png`
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/roadmap.md`
- Test: `tests/dashboard/test_theme.py` (cleanup)

**Interfaces:**
- Consumes: everything above.
- Produces: `scripts/capture_screenshots.py OUT_DIR`. It drives the system's Edge with Playwright against a demo dashboard on `http://localhost:8503`, at a 1400 × 900 viewport, `color_scheme="light"`, full page. It writes `overview.png`, `drives.png`, `charging.png`, `costs.png`, `range.png` and `routes.png`. For Routes it submits the default form first, then waits for the map's `idle` event, using `window.__mapReady` set by `map.py`.

- [ ] **Step 1: Remove the leftovers**

Delete `ui.page_header`, `ui.tiles`, `ui.sidebar_brand`, `charts.effect_bars`, `charts.bar_with_interval` and `charts.grouped_bar` if unused (`rg` to confirm), with their tests. Run `uv run pytest -q && uv run ruff check .` and expect PASS and clean.

- [ ] **Step 2: Write the screenshot script and add Playwright to the dev group**

Add `window.__mapReady = true` on `map.once('idle')` in `map.py`.

- [ ] **Step 3: Capture**

Run `KIATRACKER_DEMO=1 uv run streamlit run src/kiatracker/dashboard/app.py --server.port 8503` in the background, then `uv run --group dev python scripts/capture_screenshots.py docs/images`.

Expected: six PNGs. Open each and check against the mockups: no sidebar, cards, Morning colours, and real map tiles on routes.png.

- [ ] **Step 4: Mobile check**

Rerun the capture at a 390 × 844 viewport into a scratch folder, not committed. Expected: cards stack, and no page is wider than 390 px (`document.documentElement.scrollWidth <= 390`, asserted in the script under `--mobile`).

- [ ] **Step 5: Update the docs**

- **README:** screenshots and wording ("light Morning theme", the top navigation).
- **`docs/architecture.md`:** the dashboard section gains `theme.py`, `components.py` and `map.py` and drops pydeck.
- **`docs/roadmap.md`:** tick the redesign.

Rescan before committing: `rg -n "VIN|tailnet|100\.[0-9]+\.[0-9]+\.[0-9]+" docs README.md src` must show nothing personal.

- [ ] **Step 6: Commit**

```bash
git add -A scripts/capture_screenshots.py pyproject.toml uv.lock docs README.md src tests
git commit -m "docs: Morning screenshots, architecture and roadmap; screenshot script in the repo"
```

- [ ] **Step 7: Deploy to the Pi and verify (only after the owner approves pushing)**

1. Push the branch.
2. On the Pi, pull and rebuild the dashboard container, as in the README's Pi section (detached build, as before).
3. Open the dashboard over Tailscale Serve and check that every page loads and first load stays within today's time. Fonts and MapLibre are served locally.
4. Compare the Range page's "from N %" against the car's real SoC.
