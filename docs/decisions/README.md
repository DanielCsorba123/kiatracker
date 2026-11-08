# Architecture decision records

Short records of the decisions that shape kiatracker: the context at the time, what was decided, what it
costs, and what was considered instead. They are written to be read by someone who wants to change the
decision: if the context below no longer holds, the decision is open again.

| # | Decision | Status |
|---|---|---|
| [0001](0001-official-data-act-api.md) | Official Pleos (EU Data Act) API as the only car data source | Accepted |
| [0002](0002-raw-files-as-source-of-truth.md) | Append-only raw JSONL as the source of truth, full rebuild into DuckDB | Accepted |
| [0003](0003-derive-drives-from-polling.md) | Derive drives and charging from polling; adaptive 1 / 5 minute interval | Accepted |
| [0004](0004-data-quality-guardrails.md) | Flag drives whose energy is unknown or impossible instead of guessing | Accepted |
| [0005](0005-privacy-by-construction.md) | Privacy by construction: fail-closed demo, no coordinates past the build | Accepted |
| [0006](0006-physics-informed-model.md) | A physics-informed regression, not a generic ML model | Accepted |
| [0007](0007-specs-prior-and-backtest.md) | Car-spec prior, ridge pull chosen by a time-ordered backtest | Accepted |
| [0008](0008-local-terrain-tiles.md) | Terrain from SRTM tiles stored locally, not an elevation API | Accepted |
| [0009](0009-per-stretch-features.md) | Features per stretch between GPS readings, scaled to the odometer | Accepted |
| [0010](0010-route-comparison.md) | Route comparison with OSRM, ~1 km pieces and a common-random-numbers Monte Carlo | Accepted |
| [0011](0011-raspberry-pi-docker-tailscale.md) | Always-on collector on a Raspberry Pi in Docker, reached over Tailscale | Accepted |
| [0012](0012-streamlit-dashboard.md) | Streamlit dashboard with Streamlit-free query and chart layers | Accepted |

Format: Context, Decision, Consequences, Alternatives considered. New records get the next number; a
reversed decision is not deleted but marked *Superseded by NNNN*.
