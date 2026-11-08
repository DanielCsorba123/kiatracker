# 0002. Append-only raw JSONL as the source of truth, full rebuild into DuckDB

**Status:** Accepted, November 2026

## Context

The API returns only the latest reading, so anything not stored at poll time is lost forever. At the same
time the parsing and derivation rules were certain to change many times while the project was young (what a
drive is, how charging is detected, which drives to trust).

## Decision

A layered ("medallion") design:

- **Bronze:** every API response is appended, untouched except for compacting a large useless array, to
  monthly JSONL files in `data/raw/` (`snapshots-YYYY-MM.jsonl`, `trips-…`, `errors-…`, `weather-…`,
  `forecast-…`, `fuel-…`). Files are never edited.
- **Silver and gold:** `kiatracker build` parses all raw files into typed Python dataclasses, derives drives,
  charging sessions, stretches and so on, and writes a fresh DuckDB file. The new file replaces the old one
  atomically (`os.replace`, retried while a reader holds it).

There is no incremental state in the derived layer.

## Consequences

- Any fix to parsing or derivation applies to all history on the next build, in seconds (the data set is a
  few MB per month).
- External lookups (weather, forecast, fuel prices) are also cached as raw records, so a rebuild needs no
  network and is deterministic.
- Readers (the dashboard) open the database read-only and never block the writer for long.
- A full rebuild will eventually get slow; at the current size it would take decades. The switch would be
  incremental builds keyed on raw-file month.

## Alternatives considered

- **Insert into a database at poll time:** loses the original responses, and a parsing bug corrupts history.
- **SQLite:** fine for storage; DuckDB was chosen for analytical queries (window functions, fast scans) and a
  zero-setup columnar file.
- **A cloud warehouse:** unnecessary cost and a privacy liability for a personal data set.
