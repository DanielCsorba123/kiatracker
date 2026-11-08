# 0011. Always-on collector on a Raspberry Pi in Docker, reached over Tailscale

**Status:** Accepted, November 2026

## Context

The collector first ran from Windows Task Scheduler on a desktop PC. Whenever the PC was off, readings were
lost, and a night of unseen charging made a whole day of driving unusable
([0004](0004-data-quality-guardrails.md)). The dashboard should be reachable from a phone, without exposing
personal data to the internet or the home network.

## Decision

- **One image, two services** (`docker-compose.yml`): `collector` runs `kiatracker scheduler` (collect,
  hourly refresh) with `.env` and a read-write `./data` volume; `dashboard` runs Streamlit with `./data`
  mounted read-only and its port published on `127.0.0.1` only. Both restart unless stopped. The image builds
  for x86 and arm64; `data/` and `.env` never enter it.
- **Host:** a Raspberry Pi (arm64, 64 GB storage, Europe/Budapest time zone for log times; stored data stays
  in UTC).
- **Remote access:** `tailscale serve --bg 8501` publishes the dashboard as an HTTPS address inside the
  owner's tailnet only. No router port, no password page, no public exposure.

## Consequences

- Continuous collection since the move; the PC's scheduled tasks are disabled.
- The whole state is `data/` (a few MB per month plus terrain tiles), so moving or restoring means copying one
  folder. A nightly backup off the Pi is still to do (roadmap).
- Deploys are `git pull` and `docker compose up -d --build`. The Pi's connection to PyPI is slow, so the
  Dockerfile allows long downloads and installs dependencies in a layer that only `pyproject.toml` and
  `uv.lock` invalidate.

## Alternatives considered

- **Keep the PC:** gaps whenever it sleeps.
- **A cloud VM** (an Oracle free-tier VM was available): always on, but puts personal location data on a
  provider's machine and needs hardening of a public host.
- **Port forwarding or binding to the LAN:** anyone on the Wi-Fi or the internet could reach personal data.
