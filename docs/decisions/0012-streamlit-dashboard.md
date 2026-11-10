# 0012. Streamlit dashboard with Streamlit-free query and chart layers

**Status:** Accepted, November 2026

## Context

The dashboard serves two audiences: non-technical readers who want answers ("how far will I get tomorrow?"),
and technical readers who want to see the model and its evidence. It is a one-person project, so the UI layer
must be cheap to build and change, and still testable.

## Decision

- **Streamlit** for the app, **Altair** (Vega-Lite) for charts, DuckDB queries into pandas.
- Three layers: `queries.py` (DuckDB → DataFrame) and `charts.py` (DataFrame → chart) import no Streamlit and
  are unit-tested; pages in `dashboard/views/` are thin `render(con, period)` functions, smoke-tested headless
  with Streamlit's `AppTest`.
- A house style applied by one decorator (`charts.styled`) and one stylesheet. *Revised November 2026:* the
  "Morning" identity replaced the first look (Inter, Space Grotesk, light and dark): one light theme, Young
  Serif and Hanken Grotesk, colour tokens in `dashboard/theme.py`, HTML sections from `dashboard/components.py`
  ([spec](../superpowers/specs/2026-11-09-morning-redesign-design.md)).
- Expensive work is cached by a fingerprint of the data (model training, route comparisons for an hour).
- Pages call external services only on an explicit action (the Routes page's Compare button).

## Consequences

- Fast to iterate; charts and queries have real tests.
- Streamlit reruns the script on each interaction, so caching discipline matters.
- Hosting the public showcase on Streamlit Community Cloud is straightforward (roadmap, phase C).

## Alternatives considered

- **Grafana / Superset:** good for time series, weak for model explanations and what-if inputs.
- **A custom front end (React + API):** much more code for a single user.
- **Jupyter only:** kept for the model walkthrough (`notebooks/`), not for day-to-day use.
