# 0008. Terrain from SRTM tiles stored locally, not an elevation API

**Status:** Accepted, November 2026

## Context

Climbing and descending matter (lifting 1.95 t by 100 m costs about 0.6 kWh). The car reports altitude as 0,
so heights must come from a terrain model. Elevation APIs (Open-Meteo, Google) take exact points, which means
sending every recorded route, starting at home, to a third party.

## Decision

Use the public SRTM 1-arc-second tiles from the AWS open terrain bucket
(`elevation-tiles-prod/skadi/N47/N47E018.hgt.gz`). `refresh` downloads each 1° × 1° tile a drive or route
touches, once, into `data/dem/`; lookups (`elevation.Terrain`) read the samples they need from a memory map.
If the folder is read-only (the dashboard container), a downloaded tile is kept in memory instead.

## Consequences

- The only thing revealed is which ~100 km squares are driven in. Private, offline after the first download,
  no rate limit.
- About 25 MB per tile; a region of a few hundred km needs a handful.
- SRTM is a surface model with ~30 m cells: bridges and tunnels show the valley or the hill, not the road.
  Using one height per ~1 km piece end smooths most of it.

## Alternatives considered

- **Open-Meteo Elevation API:** free and simple (it was the first plan), rejected for privacy.
- **Copernicus GLO-30:** similar quality, less convenient distribution; possible later swap.
