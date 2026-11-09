"""Altair chart builders: a DataFrame in, a chart out. No Streamlit, so they are unit-tested.

Visual rules: one series per chart in the brand blue, thin marks with rounded bar ends, tooltips on every
mark, a single y-axis, recessive grid. Two measures never share a chart. Every builder returns its chart in
the Windrose house style (`house`): the app's fonts, a soft dashed grid, no frame, no axis lines.
"""

import functools

import altair as alt
import pandas as pd

from kiatracker.dashboard import theme
from kiatracker.route_energy import CAUSES

SKY = theme.SKY  # the main series
CORAL = theme.CORAL  # the one highlight per chart, or a second series
PALE = theme.PALE  # secondary bars
WHISKER = theme.MUTED  # interval whiskers
REFERENCE = theme.CORAL  # reference lines such as the perfect-prediction diagonal
HEIGHT = 280
MUTED = theme.MUTED  # axis labels


def house(chart):
    """Morning look: Hanken Grotesk, a quiet solid grid, no frame or axis lines, rounded bar ends.
    Section titles are HTML around the chart, so charts carry no title of their own."""
    return (
        chart.configure(font=theme.SANS, background="transparent")
        .configure_view(stroke=None)
        .configure_axis(
            domain=False,
            ticks=False,
            labelColor=MUTED,
            labelFontSize=12,
            labelPadding=8,
            titleColor=MUTED,
            titleFontSize=12,
            titleFontWeight=500,
            titlePadding=12,
            gridColor=theme.RULE,
            gridOpacity=1,
        )
        .configure_title(
            font=theme.SERIF, fontSize=18, fontWeight=400, anchor="start", offset=14, color=theme.INK
        )
        .configure_bar(cornerRadiusEnd=6)
        .configure_legend(
            labelFont=theme.SANS,
            titleFont=theme.SANS,
            labelColor=MUTED,
            titleColor=MUTED,
            symbolType="circle",
            symbolSize=90,
        )
    )


def styled(builder):
    """Return the builder's chart in the house style."""

    @functools.wraps(builder)
    def wrapper(*args, **kwargs):
        return house(builder(*args, **kwargs))

    return wrapper


def _title(title: str | None):
    return alt.Title(title, anchor="start") if title else alt.Undefined


def _base(df: pd.DataFrame, title: str | None) -> alt.Chart:
    return alt.Chart(df, title=_title(title)).properties(height=HEIGHT)


def _x(field: str, title: str | None):
    if field.endswith(":T"):
        # One band per week at its Monday; Vega's "yearweek" would snap to Sundays.
        return alt.X(
            field.replace(":T", ":O"),
            timeUnit="yearmonthdate",
            title=title,
            axis=alt.Axis(format="%d %b", grid=False, labelAngle=0, labelOverlap="greedy", labelSeparation=8),
        )
    # sort=None keeps the data's order, so bands like "5 to 10" come before "10 to 15"
    return alt.X(field, title=title, sort=None, axis=alt.Axis(grid=False, labelAngle=0))


def _tip(field: str, title: str | None = None):
    if field.startswith("week") and field.endswith(":T"):
        return alt.Tooltip(field, title=title or "Week of", timeUnit="yearmonthdate", format="%d %b %Y")
    if field.endswith(":T"):
        return alt.Tooltip(field, title=title or "Start", format="%d %b %Y %H:%M")
    return (
        alt.Tooltip(field, title=title, format=",.1f")
        if field.endswith(":Q")
        else alt.Tooltip(field, title=title)
    )


@styled
def bar(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str | None,
    y_title: str,
    color: str = SKY,
    x_title=None,
    highlight_last: bool = False,
) -> alt.Chart:
    """One series of bars; `highlight_last` draws the latest bar in coral and the rest in pale."""
    field = x.split(":")[0]
    data = df.assign(_last=df[field] == df[field].max()) if highlight_last and not df.empty else df
    colour = (
        alt.condition("datum._last", alt.value(CORAL), alt.value(PALE))
        if highlight_last
        else alt.value(color)
    )
    return (
        _base(data, title)
        .mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
        .encode(
            x=_x(x, x_title),
            y=alt.Y(y, title=y_title),
            color=colour,
            tooltip=[_tip(x, x_title), _tip(y, y_title)],
        )
    )


@styled
def predicted_vs_actual(df: pd.DataFrame, unit: str) -> alt.LayerChart:
    """Backtest predictions against what happened, on equal axes with a dashed perfect-prediction line."""
    values = pd.concat([df["predicted"], df["actual"]])
    domain = [float(values.min()), float(values.max())]
    scale = alt.Scale(domain=domain, zero=False)
    base = _base(df, None)
    points = base.mark_circle(color=SKY, size=70, opacity=0.75, strokeWidth=0).encode(
        x=alt.X("predicted:Q", title=f"Predicted {unit}", scale=scale),
        y=alt.Y("actual:Q", title=f"Actual {unit}", scale=scale),
        tooltip=[_tip("predicted:Q", "Predicted"), _tip("actual:Q", "Actual")],
    )
    line_df = pd.DataFrame({"predicted": domain, "actual": domain})
    diagonal = (
        alt.Chart(line_df)
        .mark_line(color=REFERENCE, strokeDash=[4, 4], strokeWidth=1)
        .encode(x=alt.X("predicted:Q", scale=scale), y=alt.Y("actual:Q", scale=scale))
    )
    return alt.layer(points, diagonal)


@styled
def points_with_bands(
    drives: pd.DataFrame,
    x: str,
    bands: pd.DataFrame,
    title: str,
    x_title: str,
    y: str = "kwh_per_100km",
    y_title: str = "kWh/100 km",
) -> alt.LayerChart:
    """Every drive as a dot, with each band's distance-weighted average drawn across the band."""
    lo, hi = float(drives[x].min()), float(drives[x].max())
    lines = bands.assign(x_lo=bands["lo"].clip(lower=lo), x_hi=bands["hi"].clip(upper=hi))  # catch-all edges
    chart_title = _title(title)  # explain dots and lines in a themed caption, not here
    points = (
        alt.Chart(drives, title=chart_title)
        .mark_circle(color=SKY, size=70, opacity=0.65)
        .encode(
            x=alt.X(f"{x}:Q", title=x_title, scale=alt.Scale(zero=False)),
            y=alt.Y(f"{y}:Q", title=y_title, scale=alt.Scale(zero=False)),
            tooltip=[
                _tip("start_local:T"),
                _tip("distance_km:Q", "km"),
                _tip(f"{x}:Q", x_title),
                _tip(f"{y}:Q", y_title),
            ],
        )
    )
    averages = (
        alt.Chart(lines)
        .mark_rule(color=CORAL, strokeWidth=3)
        .encode(
            x=alt.X("x_lo:Q"),
            x2="x_hi:Q",
            y=alt.Y(f"{y}:Q"),
            tooltip=[
                _tip("band:N", x_title),
                _tip(f"{y}:Q", "Average"),
                alt.Tooltip("drives:Q", title="Drives"),
            ],
        )
    )
    return alt.layer(points, averages).properties(height=HEIGHT)


@styled
def combined_scatter(drives: pd.DataFrame) -> alt.Chart:
    """Temperature, wind and trip length at once: x temperature, colour wind, dot size trip length."""
    return (
        _base(drives, "Temperature, wind and trip length together")
        .mark_circle(opacity=0.8)
        .encode(
            x=alt.X("temp_c:Q", title="Outside temperature (°C)", scale=alt.Scale(zero=False)),
            y=alt.Y("kwh_per_100km:Q", title="kWh/100 km", scale=alt.Scale(zero=False)),
            color=alt.Color(
                "wind_kph:Q",
                title="Wind (km/h)",
                scale=alt.Scale(range=["#cde2fb", "#0d366b"]),
                legend=alt.Legend(title="Wind (km/h)"),
            ),
            size=alt.Size(
                "distance_km:Q", scale=alt.Scale(range=[30, 420]), legend=alt.Legend(title="Trip (km)")
            ),
            tooltip=[
                _tip("start_local:T"),
                _tip("temp_c:Q", "°C"),
                _tip("wind_kph:Q", "Wind km/h"),
                _tip("distance_km:Q", "km"),
                _tip("kwh_per_100km:Q", "kWh/100 km"),
            ],
        )
        .properties(height=360)
    )


@styled
def effect_bars(effects: pd.DataFrame) -> alt.LayerChart:
    """Extra kWh/100 km in harder vs easier conditions, one bar per factor; grey until there's enough data."""
    df = effects.assign(
        condition=effects["factor"] + ": " + effects["harder_label"] + " vs " + effects["easier_label"],
        shown=effects["diff_kwh"].where(effects["enough"], 0).fillna(0),
        label_at=effects["diff_kwh"].where(effects["enough"], 0).fillna(0).clip(lower=0),  # never on the bar
        label=[
            f"{d:+.1f} kWh/100 km ({p:+.0%})" if ok and d is not None else "needs more drives"
            for d, p, ok in zip(effects["diff_kwh"], effects["pct"], effects["enough"], strict=True)
        ],
    )
    y = alt.Y("condition:N", sort=None, title=None, axis=alt.Axis(labelLimit=320, labelFontSize=12))
    base = alt.Chart(df, title=alt.Title("What changes your consumption", anchor="start"))
    bars = base.mark_bar(cornerRadiusEnd=6, height=22).encode(
        x=alt.X("shown:Q", title="Extra energy per 100 km (kWh), harder vs easier conditions"),
        y=y,
        color=alt.condition("datum.enough", alt.value(CORAL), alt.value(MUTED)),
        tooltip=[
            alt.Tooltip("condition:N", title="Comparison"),
            _tip("harder_kwh:Q", "Harder, kWh/100 km"),
            _tip("easier_kwh:Q", "Easier, kWh/100 km"),
            alt.Tooltip("n_harder:Q", title="Drives (harder)"),
            alt.Tooltip("n_easier:Q", title="Drives (easier)"),
        ],
    )
    labels = base.mark_text(align="left", dx=8, fontSize=12, color=MUTED).encode(
        x="label_at:Q", y=y, text="label:N"
    )
    return alt.layer(bars, labels).properties(height=46 * len(df))


@styled
def range_heatmap(grid: pd.DataFrame, title: str) -> alt.LayerChart:
    """Range in km for every temperature (columns) and wind speed (rows); darker means further."""
    mid = (grid["range_km"].min() + grid["range_km"].max()) / 2
    base = alt.Chart(grid, title=_title(title))
    gap = alt.Scale(paddingInner=0.08)  # even gaps between rounded tiles, so no background shows at corners
    x = alt.X(
        "temp_c:O", title="Outside temperature (°C)", scale=gap, axis=alt.Axis(labelAngle=0, grid=False)
    )
    y = alt.Y("wind_kph:O", title="Wind (km/h)", sort="descending", scale=gap, axis=alt.Axis(grid=False))
    cells = base.mark_rect(cornerRadius=6, stroke=None).encode(
        x=x,
        y=y,
        color=alt.Color("range_km:Q", scale=alt.Scale(range=["#cde2fb", "#104281"]), legend=None),
        tooltip=[
            _tip("temp_c:O", "°C"),
            _tip("wind_kph:O", "Wind km/h"),
            alt.Tooltip("range_km:Q", title="Range (km)", format=",.0f"),
        ],
    )
    labels = base.mark_text(fontSize=13, fontWeight=600, font="Space Grotesk").encode(
        x=x,
        y=y,
        text=alt.Text("range_km:Q", format=".0f"),
        color=alt.condition(f"datum.range_km > {mid}", alt.value("#ffffff"), alt.value("#16191f")),
    )
    return alt.layer(cells, labels).properties(height=300)


@styled
def drive_log(drives: pd.DataFrame) -> alt.Chart:
    """Every drive over time: consumption up the side, dot size for distance, colour for temperature."""
    return (
        alt.Chart(drives, title=alt.Title("Drive log", anchor="start"))
        .mark_circle(opacity=0.85, stroke="#ffffff", strokeWidth=0.6)
        .encode(
            x=alt.X("start_local:T", title=None, axis=alt.Axis(format="%d %b", labelAngle=0)),
            y=alt.Y("kwh_per_100km:Q", title="kWh/100 km", scale=alt.Scale(zero=False)),
            size=alt.Size("distance_km:Q", scale=alt.Scale(range=[40, 600]), legend=None),
            color=alt.Color(
                "temp_c:Q",
                title="°C",
                scale=alt.Scale(range=["#2a78d6", "#c3c2b7", "#eb6834"], domainMid=10),
                legend=alt.Legend(title="Outside °C"),
            ),
            tooltip=[
                _tip("start_local:T"),
                _tip("distance_km:Q", "km"),
                _tip("kwh_per_100km:Q", "kWh/100 km"),
                _tip("temp_c:Q", "°C"),
                _tip("wind_kph:Q", "Wind km/h"),
                _tip("speed_kph:Q", "Avg km/h"),
            ],
        )
        .properties(height=320)
    )


@styled
def bar_with_interval(
    df: pd.DataFrame, x: str, y: str, lo: str, hi: str, title: str, y_title: str
) -> alt.LayerChart:
    """Bars for the expected value with a whisker for the likely range (e.g. 10th-90th percentile)."""
    base = _base(df, title)
    bars = base.mark_bar(color=SKY, cornerRadiusTopLeft=6, cornerRadiusTopRight=6, opacity=0.5).encode(
        x=_x(x, None),
        y=alt.Y(f"{y}:Q", title=y_title),
        tooltip=[_tip(x), _tip(f"{y}:Q", "Expected"), _tip(f"{lo}:Q", "Low"), _tip(f"{hi}:Q", "High")],
    )
    whiskers = base.mark_rule(color=WHISKER, strokeWidth=2).encode(x=_x(x, None), y=f"{lo}:Q", y2=f"{hi}:Q")
    return alt.layer(bars, whiskers)


@styled
def line(df: pd.DataFrame, x: str, y: str, title: str, y_title: str, color: str = SKY) -> alt.LayerChart:
    """A trend line over a soft gradient area, with points to hover."""
    gradient = alt.Gradient(
        gradient="linear",
        x1=1,
        x2=1,
        y1=1,
        y2=0,
        stops=[
            alt.GradientStop(color=f"{color}00", offset=0),
            alt.GradientStop(color=f"{color}66", offset=1),
        ],
    )
    encoding = {"x": _x(x, None), "y": alt.Y(y, title=y_title, scale=alt.Scale(zero=False))}
    base = _base(df, title)
    area = base.mark_area(color=gradient, interpolate="monotone").encode(**encoding)
    trend = base.mark_line(color=color, strokeWidth=2.5, interpolate="monotone").encode(**encoding)
    points = base.mark_circle(color=color, size=70, opacity=1).encode(
        **encoding, tooltip=[_tip(x), _tip(y, y_title)]
    )
    return alt.layer(area, trend, points)


@styled
def scatter(
    df: pd.DataFrame, x: str, y: str, title: str, x_title: str, y_title: str, tooltip: list[str]
) -> alt.Chart:
    return (
        _base(df, title)
        .mark_circle(color=SKY, size=70, opacity=0.75, strokeWidth=0)
        .encode(
            x=alt.X(x, title=x_title, scale=alt.Scale(zero=False)),
            y=alt.Y(y, title=y_title, scale=alt.Scale(zero=False)),
            tooltip=[_tip(t) for t in tooltip],
        )
    )


@styled
def histogram(
    df: pd.DataFrame,
    column: str,
    title: str,
    step: float,
    x_title: str | None = None,
    extent: tuple[float, float] | None = None,
    colour: str = SKY,
) -> alt.Chart:
    bins = alt.Bin(step=step, extent=list(extent)) if extent else alt.Bin(step=step)
    scale = alt.Scale(domain=list(extent)) if extent else alt.Undefined
    return (
        _base(df, title)
        .mark_bar(color=colour, cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
        .encode(
            x=alt.X(f"{column}:Q", bin=bins, scale=scale, title=x_title or column, axis=alt.Axis(format="d")),
            y=alt.Y("count():Q", title="Sessions"),
            tooltip=[alt.Tooltip(f"{column}:Q", bin=bins, title=x_title), "count():Q"],
        )
    )


ROUTE_COLOURS = [CORAL, SKY, PALE, theme.SUN, theme.SKY_INK]  # the chosen route first, in coral
CAUSE_COLOURS = ["#6f8fb5", "#9aa6b8", SKY, "#5bc0eb", CORAL, "#e34948", "#8a63d2", PALE]


@styled
def route_breakdown(parts: pd.DataFrame) -> alt.Chart:
    """kWh per cause and route, stacked; regeneration goes left of zero. Columns: route, cause, kwh."""
    df = parts.assign(label=parts["cause"].map(CAUSES))
    return (
        alt.Chart(df, title=alt.Title("Where the energy goes", anchor="start"))
        .mark_bar(height=26, cornerRadius=3)
        .encode(
            x=alt.X("kwh:Q", title="kWh over the route (regeneration below zero)", stack="zero"),
            y=alt.Y("route:N", sort=None, title=None, axis=alt.Axis(labelLimit=260, labelFontSize=12)),
            color=alt.Color(
                "label:N",
                sort=list(CAUSES.values()),
                scale=alt.Scale(domain=list(CAUSES.values()), range=CAUSE_COLOURS),
                legend=alt.Legend(title=None, orient="bottom", columns=4, labelLimit=220),
            ),
            order=alt.Order("order:Q"),
            tooltip=[
                alt.Tooltip("route:N", title="Route"),
                alt.Tooltip("label:N", title="Cause"),
                _tip("kwh:Q", "kWh"),
            ],
        )  # fmt: skip
        .transform_calculate(order=f"indexof({list(CAUSES.values())!r}, datum.label)")
        # Streamlit fits title, axis and legend into this height too, so leave room for them
        .properties(height=46 * df["route"].nunique() + 150)
    )


@styled
def route_profile(profile: pd.DataFrame, y: str, title: str, y_title: str) -> alt.Chart:
    """One line per route along the distance driven. Columns: route, km, and `y`."""
    routes = list(dict.fromkeys(profile["route"]))
    return (
        alt.Chart(profile, title=_title(title))
        .mark_line(strokeWidth=2.5, interpolate="monotone")
        .encode(
            x=alt.X("km:Q", title="km from the start", axis=alt.Axis(grid=False)),
            y=alt.Y(f"{y}:Q", title=y_title, scale=alt.Scale(zero=False)),
            color=alt.Color(
                "route:N",
                sort=routes,
                scale=alt.Scale(domain=routes, range=ROUTE_COLOURS),
                legend=alt.Legend(title=None, orient="bottom"),
            ),
            tooltip=[alt.Tooltip("route:N", title="Route"), _tip("km:Q", "km"), _tip(f"{y}:Q", y_title)],
        )  # fmt: skip
        .properties(height=HEIGHT - 40)
    )


@styled
def monthly_use(df: pd.DataFrame) -> alt.LayerChart:
    """kWh/100 km per month; months more than 10 % above the period's mean in coral. Columns: month, kwh."""
    data = df.dropna(subset=["kwh_per_100km"]).assign(
        high=lambda d: d["kwh_per_100km"] > 1.1 * d["kwh_per_100km"].mean(),
    )
    month_names = alt.Axis(
        labelAngle=0, labelExpr="timeFormat(toDate(datum.value + '-01'), '%b')", grid=False
    )
    base = alt.Chart(data).encode(x=alt.X("month:O", title=None, sort=None, axis=month_names))
    bars = base.mark_bar(size=34).encode(
        y=alt.Y("kwh_per_100km:Q", title=None, axis=None),
        color=alt.condition("datum.high", alt.value(CORAL), alt.value(PALE)),
        tooltip=[alt.Tooltip("month:O", title="Month"), _tip("kwh_per_100km:Q", "kWh/100 km")],
    )
    values = base.mark_text(dy=-8, fontSize=12, color=theme.INK).encode(
        y="kwh_per_100km:Q", text=alt.Text("kwh_per_100km:Q", format=".1f")
    )
    return (bars + values).properties(height=HEIGHT - 60)


@styled
def weekly_distance(df: pd.DataFrame) -> alt.Chart:
    """km per week; the latest week in coral. Columns: week, distance_km."""
    data = df.assign(last=df["week"] == df["week"].max())
    return (
        alt.Chart(data)
        .mark_bar()
        .encode(
            x=alt.X("week:T", title=None, axis=alt.Axis(grid=False, format="%d %b", labelAngle=0)),
            y=alt.Y("distance_km:Q", title="km"),
            color=alt.condition("datum.last", alt.value(CORAL), alt.value(PALE)),
            tooltip=[_tip("week:T"), _tip("distance_km:Q", "km")],
        )
        .properties(height=HEIGHT - 100)
    )


@styled
def drives_over_year(df: pd.DataFrame) -> alt.LayerChart:
    """Every drive by date and kWh/100 km (coral at 19 or more), with a smooth seasonal average."""
    data = df.dropna(subset=["kwh_per_100km"]).assign(costly=lambda d: d["kwh_per_100km"] >= 19)
    base = alt.Chart(data).encode(
        x=alt.X(
            "start_local:T",
            title=None,
            axis=alt.Axis(grid=False, format="%b", labelAngle=0, tickCount="month"),
        )
    )
    dots = base.mark_circle(size=40, opacity=0.55).encode(
        y=alt.Y("kwh_per_100km:Q", title="kWh/100 km", scale=alt.Scale(zero=False)),
        color=alt.condition("datum.costly", alt.value(CORAL), alt.value(SKY)),
        tooltip=[_tip("start_local:T"), _tip("kwh_per_100km:Q", "kWh/100 km")],
    )
    trend = (
        base.transform_loess("start_local", "kwh_per_100km", bandwidth=0.3)
        .mark_line(color=theme.INK, opacity=0.6, strokeWidth=2)
        .encode(y="kwh_per_100km:Q")
    )
    return (dots + trend).properties(height=HEIGHT - 50)


@styled
def plug_hours(df: pd.DataFrame) -> alt.Chart:
    """Sessions by local start hour; the busiest four hours in sun yellow. Columns: hour, sessions."""
    total = df["sessions"].tolist()
    start = max(range(21), key=lambda h: sum(total[h : h + 4]))
    data = df.assign(peak=df["hour"].between(start, start + 3))
    return (
        alt.Chart(data)
        .mark_bar()
        .encode(
            x=alt.X(
                "hour:O",
                title=None,
                axis=alt.Axis(labelAngle=0, labelExpr="datum.value % 3 ? '' : datum.value"),
            ),
            y=alt.Y("sessions:Q", title=None, axis=None),
            color=alt.condition("datum.peak", alt.value(theme.SUN), alt.value(PALE)),
            tooltip=[alt.Tooltip("hour:O", title="Hour"), alt.Tooltip("sessions:Q", title="Sessions")],
        )
        .properties(height=130)
    )


@styled
def savings_bars(df: pd.DataFrame) -> alt.LayerChart:
    """Saved against petrol per bucket; the last complete bucket in coral with its value. Columns: bucket,
    saved_huf, complete."""
    data = df.copy()
    complete = data.index[data["complete"]]
    data["highlight"] = data.index == (complete[-1] if len(complete) else -1)
    data["label"] = [f"{v / 1000:.0f}k" for v in data["saved_huf"]]
    base = alt.Chart(data).encode(x=alt.X("bucket:O", title=None, sort=None, axis=alt.Axis(labelAngle=0)))
    bars = base.mark_bar(size=40).encode(
        y=alt.Y("saved_huf:Q", title=None, axis=None),
        color=alt.condition("datum.highlight", alt.value(CORAL), alt.value(PALE)),
        tooltip=[
            alt.Tooltip("bucket:O", title="Period"),
            alt.Tooltip("saved_huf:Q", title="Saved (Ft)", format=",.0f"),
        ],
    )
    labels = base.mark_text(dy=-8, fontSize=12).encode(
        y="saved_huf:Q",
        text="label:N",
        color=alt.condition("datum.highlight", alt.value(theme.INK), alt.value(MUTED)),
    )
    return (bars + labels).properties(height=HEIGHT - 70)


@styled
def route_heights(profile: pd.DataFrame) -> alt.LayerChart:
    """Height above the start along each route on one distance axis. The first route is a coral area,
    the second a sky area, the rest dashed; the two highest points are labelled.
    Columns: route, km, height."""
    routes = list(dict.fromkeys(profile["route"]))
    x = alt.X("km:Q", title="km from the start", axis=alt.Axis(grid=False))
    y = alt.Y("height:Q", title="m above the start")
    layers = []
    for i, name in enumerate(routes):
        part = profile[profile["route"] == name]
        tip = [
            alt.Tooltip("route:N", title="Route"),
            _tip("km:Q", "km"),
            _tip("height:Q", "m above the start"),
        ]
        if i < 2:
            colour, opacity, width = (CORAL, 0.16, 3) if i == 0 else (SKY, 0.10, 2.5)
            area = alt.Chart(part).mark_area(color=colour, opacity=opacity, interpolate="monotone")
            layers.append(area.encode(x=x, y=y))
            line = alt.Chart(part).mark_line(color=colour, strokeWidth=width, interpolate="monotone")
        else:
            line = alt.Chart(part).mark_line(
                color=PALE, strokeWidth=1.5, strokeDash=[4, 4], interpolate="monotone"
            )
        layers.append(line.encode(x=x, y=y, tooltip=tip))
    notes = []
    for i, name in enumerate(routes[:2]):
        top = profile[profile["route"] == name].sort_values("height").iloc[-1]
        text = (
            f"+{top['height']:.0f} m · highest point, km {top['km']:.0f}"
            if i == 0
            else f"{name}: never above +{top['height']:.0f} m"
        )
        notes.append({"km": top["km"], "height": top["height"], "text": text, "first": i == 0})
    marks = pd.DataFrame(notes)
    if not marks.empty:
        layers.append(
            alt.Chart(marks[marks["first"]])
            .mark_point(filled=True, size=70, color=theme.CARD, stroke=CORAL, strokeWidth=2.5)
            .encode(x="km:Q", y="height:Q")
        )
        layers.append(
            alt.Chart(marks)
            .mark_text(
                align="left", dx=10, dy=alt.ExprRef("datum.first ? -10 : -26"), fontSize=13, fontWeight=600
            )
            .encode(
                x="km:Q",
                y="height:Q",
                text="text:N",
                color=alt.condition("datum.first", alt.value(theme.INK), alt.value(theme.SKY_INK)),
            )
        )
    top = float(profile["height"].max()) if not profile.empty else 0.0
    chart = alt.layer(*layers).resolve_scale(y="shared").properties(height=HEIGHT - 20)
    return chart.encode(y=alt.Y("height:Q", scale=alt.Scale(domainMax=top * 1.2 + 20)))


@styled
def route_difference(parts: pd.DataFrame, first: str, second: str) -> alt.LayerChart:
    """Cause by cause, kWh of `first` minus `second`: coral costs more, sky saves; the net underneath.
    Columns: route, cause, kwh."""
    a = parts[parts["route"] == first].groupby("cause")["kwh"].sum()
    b = parts[parts["route"] == second].groupby("cause")["kwh"].sum()
    diff = a.subtract(b, fill_value=0)
    diff = diff[diff.abs() >= 0.05]
    data = pd.DataFrame(
        {
            "cause": [CAUSES.get(c, c) for c in diff.index],
            "kwh": diff.values,
            "label": [f"{v:+.1f}" for v in diff.values],
        }
    )
    net = float(a.sum() - b.sum())
    y = alt.Y("cause:N", title=None, sort=None, axis=alt.Axis(labelLimit=220, labelFontSize=13))
    bars = (
        alt.Chart(data)
        .mark_bar(height=18)
        .encode(
            x=alt.X("kwh:Q", title=f"kWh, {first} minus {second}"),
            y=y,
            color=alt.condition("datum.kwh > 0", alt.value(CORAL), alt.value(SKY)),
            tooltip=[alt.Tooltip("cause:N", title="Cause"), alt.Tooltip("kwh:Q", title="kWh", format="+.1f")],
        )
    )
    labels = (
        alt.Chart(data)
        .mark_text(fontSize=12, color=MUTED, dx=alt.ExprRef("datum.kwh > 0 ? 18 : -18"))
        .encode(x="kwh:Q", y=y, text="label:N")
    )
    zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color=theme.INK).encode(x="x:Q")
    title = f"Net: {first} uses {abs(net):.1f} kWh {'less' if net < 0 else 'more'}"
    return alt.layer(bars, labels, zero).properties(
        title=alt.Title(title, anchor="start", fontSize=14, font=theme.SANS, fontWeight=600),
        height=40 * max(1, len(data)),
    )
