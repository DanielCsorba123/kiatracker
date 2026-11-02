"""Small display helpers shared by the pages."""

import streamlit as st

MISSING = "–"


def number(value: float | None, unit: str = "", digits: int = 0) -> str:
    if value is None:
        return MISSING
    return f"{value:,.{digits}f}{' ' + unit if unit else ''}"


def tiles(items: list[tuple[str, str, str | None]]) -> None:
    """A row of stat tiles: (label, formatted value, help text)."""
    for column, (label, value, help_text) in zip(st.columns(len(items)), items, strict=True):
        column.metric(label, value, help=help_text)


def empty(message: str = "No data in this period yet.") -> None:
    st.info(message)
