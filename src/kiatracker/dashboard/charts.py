"""Altair chart builders: a DataFrame in, a chart out. No Streamlit, so they are unit-tested.

Visual rules: one series per chart in the brand blue, thin marks with rounded bar ends, tooltips on every
mark, a single y-axis, recessive grid. Two measures never share a chart. Every builder returns its chart in
the Windrose house style (`house`): the app's fonts, a soft dashed grid, no frame, no axis lines.
"""

import functools

import altair as alt
import pandas as pd

BLUE = "#2a78d6"  # categorical slot 1
ORANGE = "#eb6834"  # categorical slot 2, for a second series when one is needed
AQUA = "#1baf7a"  # categorical slot 3; the first three slots stay distinguishable for colour-blind readers
INK = "#8a8985"  # whiskers: mid grey reads on both the light and the dark surface
REFERENCE = "#9a9994"  # reference lines such as the perfect-prediction diagonal
HEIGHT = 280
MUTED = "#8a8985"  # axis labels and grid: mid grey reads on both the light and the dark surface


def house(chart):
    """Windrose look: brand fonts, recessive dashed grid, no frame or axis lines, generous title spacing."""
    return (
        chart.configure(font="Inter")
        .configure_view(stroke=None)
        .configure_axis(
            domain=False,
            ticks=False,
            labelColor=MUTED,
            labelFontSize=11,
            labelPadding=8,
            titleColor=MUTED,
            titleFontSize=11,
            titleFontWeight=500,
            titlePadding=12,
            gridColor=MUTED,
            gridOpacity=0.22,
            gridDash=[2, 4],
        )
        .configure_title(font="Space Grotesk", fontSize=16, fontWeight=600, anchor="start", offset=14)
        .configure_legend(
            labelFont="Inter",
            titleFont="Inter",
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


def _base(df: pd.DataFrame, title: str) -> alt.Chart:
    return alt.Chart(df, title=alt.Title(title, anchor="start")).properties(height=HEIGHT)


def _x(field: str, title: str | None):
    if field.endswith(":T"):
        # One band per week at its Monday; Vega's "yearweek" would snap to Sundays.
        return alt.X(
            field.replace(":T", ":O"),
            timeUnit="yearmonthdate",
            title=title,
            axis=alt.Axis(format="%d %b", grid=False, labelAngle=0),
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
    df: pd.DataFrame, x: str, y: str, title: str, y_title: str, color: str = BLUE, x_title=None
) -> alt.Chart:
    return (
        _base(df, title)
        .mark_bar(color=color, cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
        .encode(x=_x(x, x_title), y=alt.Y(y, title=y_title), tooltip=[_tip(x, x_title), _tip(y, y_title)])
    )


@styled
def predicted_vs_actual(df: pd.DataFrame, unit: str) -> alt.LayerChart:
    """Backtest predictions against what happened, on equal axes with a dashed perfect-prediction line."""
    values = pd.concat([df["predicted"], df["actual"]])
    domain = [float(values.min()), float(values.max())]
    scale = alt.Scale(domain=domain, zero=False)
    base = _base(df, "Predicted vs actual consumption")
    points = base.mark_circle(color=BLUE, size=70, opacity=0.75, strokeWidth=0).encode(
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
def grouped_bar(
    df: pd.DataFrame, x: str, series: str, y: str, title: str, y_title: str, order: list[str]
) -> alt.Chart:
    """Bars side by side per x value; each series keeps its colour whatever is filtered (legend shown)."""
    colors = alt.Scale(domain=order, range=[BLUE, ORANGE, AQUA][: len(order)])
    return (
        _base(df, title)
        .mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
        .encode(
            x=alt.X(f"{x}:O", title=None, axis=alt.Axis(labelAngle=0, grid=False)),
            xOffset=alt.XOffset(f"{series}:N", sort=order),
            y=alt.Y(f"{y}:Q", title=y_title),
            color=alt.Color(
                f"{series}:N", scale=colors, sort=order, legend=alt.Legend(title=None, orient="top")
            ),
            tooltip=[
                _tip(f"{x}:O", "Month"),
                _tip(f"{series}:N", "Car"),
                alt.Tooltip(f"{y}:Q", title=y_title, format=",.0f"),
            ],
        )
    )


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
    chart_title = alt.Title(title, anchor="start")  # explain dots and lines in a themed caption, not here
    points = (
        alt.Chart(drives, title=chart_title)
        .mark_circle(color=BLUE, size=70, opacity=0.65)
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
        .mark_rule(color=ORANGE, strokeWidth=3)
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
        color=alt.condition("datum.enough", alt.value(ORANGE), alt.value(MUTED)),
        tooltip=[
            alt.Tooltip("condition:N", title="Comparison"),
            _tip("harder_kwh:Q", "Harder, kWh/100 km"),
            _tip("easier_kwh:Q", "Easier, kWh/100 km"),
            alt.Tooltip("n_harder:Q", title="Drives (harder)"),
            alt.Tooltip("n_easier:Q", title="Drives (easier)"),
        ],
    )
    labels = base.mark_text(align="left", dx=8, fontSize=12, color=MUTED).encode(
        x="shown:Q", y=y, text="label:N"
    )
    return alt.layer(bars, labels).properties(height=46 * len(df))


@styled
def range_heatmap(grid: pd.DataFrame, title: str) -> alt.LayerChart:
    """Range in km for every temperature (columns) and wind speed (rows); darker means further."""
    mid = (grid["range_km"].min() + grid["range_km"].max()) / 2
    base = alt.Chart(grid, title=alt.Title(title, anchor="start"))
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
    bars = base.mark_bar(color=BLUE, cornerRadiusTopLeft=6, cornerRadiusTopRight=6, opacity=0.5).encode(
        x=_x(x, None),
        y=alt.Y(f"{y}:Q", title=y_title),
        tooltip=[_tip(x), _tip(f"{y}:Q", "Expected"), _tip(f"{lo}:Q", "Low"), _tip(f"{hi}:Q", "High")],
    )
    whiskers = base.mark_rule(color=INK, strokeWidth=2).encode(x=_x(x, None), y=f"{lo}:Q", y2=f"{hi}:Q")
    return alt.layer(bars, whiskers)


@styled
def line(df: pd.DataFrame, x: str, y: str, title: str, y_title: str, color: str = BLUE) -> alt.LayerChart:
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
        .mark_circle(color=BLUE, size=70, opacity=0.75, strokeWidth=0)
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
) -> alt.Chart:
    bins = alt.Bin(step=step, extent=list(extent)) if extent else alt.Bin(step=step)
    scale = alt.Scale(domain=list(extent)) if extent else alt.Undefined
    return (
        _base(df, title)
        .mark_bar(color=BLUE, cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
        .encode(
            x=alt.X(f"{column}:Q", bin=bins, scale=scale, title=x_title or column, axis=alt.Axis(format="d")),
            y=alt.Y("count():Q", title="Sessions"),
            tooltip=[alt.Tooltip(f"{column}:Q", bin=bins, title=x_title), "count():Q"],
        )
    )
