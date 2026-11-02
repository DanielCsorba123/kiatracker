"""Altair chart builders: a DataFrame in, a chart out. No Streamlit, so they are unit-tested.

Visual rules: one series per chart in the brand blue, thin marks with rounded bar ends, tooltips on every
mark, a single y-axis, recessive grid. Two measures never share a chart.
"""

import altair as alt
import pandas as pd

BLUE = "#2a78d6"  # categorical slot 1
ORANGE = "#eb6834"  # categorical slot 2, for a second series when one is needed
HEIGHT = 260


def _base(df: pd.DataFrame, title: str) -> alt.Chart:
    return alt.Chart(df, title=alt.Title(title, anchor="start")).properties(height=HEIGHT)


def _x(field: str, title: str | None):
    if field.endswith(":T"):
        return alt.X(field, timeUnit="yearweek", title=title, axis=alt.Axis(format="%d %b", grid=False))
    return alt.X(field, title=title, axis=alt.Axis(grid=False, labelAngle=0))


def _tip(field: str, title: str | None = None):
    if field.endswith(":T"):
        return alt.Tooltip(field, title=title or "Week of", timeUnit="yearweek", format="%d %b %Y")
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
        .mark_circle(color=BLUE, size=70, opacity=0.75, stroke="white", strokeWidth=1)
        .encode(
            x=alt.X(x, title=x_title, scale=alt.Scale(zero=False)),
            y=alt.Y(y, title=y_title, scale=alt.Scale(zero=False)),
            tooltip=[_tip(t) for t in tooltip],
        )
    )


def histogram(
    df: pd.DataFrame, column: str, title: str, step: float, x_title: str | None = None
) -> alt.Chart:
    return (
        _base(df, title)
        .mark_bar(color=BLUE, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X(f"{column}:Q", bin=alt.Bin(step=step), title=x_title or column),
            y=alt.Y("count():Q", title="Sessions"),
            tooltip=[alt.Tooltip(f"{column}:Q", bin=alt.Bin(step=step), title=x_title), "count():Q"],
        )
    )
