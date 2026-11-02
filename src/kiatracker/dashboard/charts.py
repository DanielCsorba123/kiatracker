"""Altair chart builders: a DataFrame in, a chart out. No Streamlit, so they are unit-tested.

Visual rules: one series per chart in the brand blue, thin marks with rounded bar ends, tooltips on every
mark, a single y-axis, recessive grid. Two measures never share a chart.
"""

import altair as alt
import pandas as pd

BLUE = "#2a78d6"  # categorical slot 1
ORANGE = "#eb6834"  # categorical slot 2, for a second series when one is needed
INK = "#8a8985"  # whiskers: mid grey reads on both the light and the dark surface
REFERENCE = "#9a9994"  # reference lines such as the perfect-prediction diagonal
HEIGHT = 260


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


def bar(
    df: pd.DataFrame, x: str, y: str, title: str, y_title: str, color: str = BLUE, x_title=None
) -> alt.Chart:
    return (
        _base(df, title)
        .mark_bar(color=color, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(x=_x(x, x_title), y=alt.Y(y, title=y_title), tooltip=[_tip(x, x_title), _tip(y, y_title)])
    )


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


def bar_with_interval(
    df: pd.DataFrame, x: str, y: str, lo: str, hi: str, title: str, y_title: str
) -> alt.LayerChart:
    """Bars for the expected value with a whisker for the likely range (e.g. 10th-90th percentile)."""
    base = _base(df, title)
    bars = base.mark_bar(color=BLUE, cornerRadiusTopLeft=4, cornerRadiusTopRight=4, opacity=0.5).encode(
        x=_x(x, None),
        y=alt.Y(f"{y}:Q", title=y_title),
        tooltip=[_tip(x), _tip(f"{y}:Q", "Expected"), _tip(f"{lo}:Q", "Low"), _tip(f"{hi}:Q", "High")],
    )
    whiskers = base.mark_rule(color=INK, strokeWidth=2).encode(x=_x(x, None), y=f"{lo}:Q", y2=f"{hi}:Q")
    return alt.layer(bars, whiskers)


def line(df: pd.DataFrame, x: str, y: str, title: str, y_title: str, color: str = BLUE) -> alt.Chart:
    return (
        _base(df, title)
        .mark_line(color=color, strokeWidth=2, point=alt.OverlayMarkDef(color=color, size=64))
        .encode(
            x=_x(x, None),
            y=alt.Y(y, title=y_title, scale=alt.Scale(zero=False)),
            tooltip=[_tip(x), _tip(y, y_title)],
        )
    )


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
        .mark_bar(color=BLUE, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X(f"{column}:Q", bin=bins, scale=scale, title=x_title or column, axis=alt.Axis(format="d")),
            y=alt.Y("count():Q", title="Sessions"),
            tooltip=[alt.Tooltip(f"{column}:Q", bin=bins, title=x_title), "count():Q"],
        )
    )
