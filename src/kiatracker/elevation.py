"""Terrain height from SRTM tiles kept on disk, so routes never leave the machine.

An online elevation API would need precise points, which means sending exact routes (home included) to a
third party. Instead the public 1° x 1° SRTM tiles are downloaded once (the request reveals only which
~100 km square is driven in) and read locally: private, offline, no rate limit.
"""

import gzip
import math
from collections.abc import Callable
from pathlib import Path

import httpx
import numpy as np

TILE_URL = "https://elevation-tiles-prod.s3.amazonaws.com/skadi/{folder}/{name}.hgt.gz"
VOID = -32768


def tile_name(lat: float, lon: float) -> str:
    """SRTM naming: the tile's south-west corner, e.g. N47E018 for 47.x N, 18.x E."""
    south, west = math.floor(lat), math.floor(lon)
    return f"{'N' if south >= 0 else 'S'}{abs(south):02d}{'E' if west >= 0 else 'W'}{abs(west):03d}"


def download_tile(name: str, http: httpx.Client | None = None) -> bytes:
    """The gzipped tile from the public AWS terrain bucket."""
    client = http or httpx.Client()
    response = client.get(TILE_URL.format(folder=name[:3], name=name), timeout=120)
    response.raise_for_status()
    return response.content


class Terrain:
    """Elevation lookups from a folder of .hgt tiles; missing tiles are fetched by `download` if given."""

    def __init__(self, folder: Path, download: Callable[[str], bytes] | None = download_tile):
        self.folder = folder
        self.download = download
        self.tiles: dict[str, np.ndarray | None] = {}

    def _tile(self, name: str) -> np.ndarray | None:
        if name not in self.tiles:
            path = self.folder / f"{name}.hgt"
            if not path.exists() and self.download is not None:
                try:
                    data = gzip.decompress(self.download(name))
                except (httpx.HTTPError, OSError):
                    data = None
                if data:
                    try:
                        self.folder.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(data)
                    except OSError:  # read-only data folder (the dashboard container): keep it in memory
                        raw = np.frombuffer(data, dtype=">i2")
                        self.tiles[name] = raw.reshape(math.isqrt(raw.size), -1)
                        return self.tiles[name]
            if path.exists():
                raw = np.memmap(path, dtype=">i2", mode="r")  # 26 MB per tile: read only the samples used
                size = math.isqrt(raw.size)
                self.tiles[name] = raw.reshape(size, size)
            else:
                self.tiles[name] = None
        return self.tiles[name]

    def prefetch(self, names: set[str]) -> int:
        """Download the tiles not on disk yet; returns how many are now available."""
        return sum(self._tile(n) is not None for n in sorted(names))

    def elevation(self, lat: float, lon: float) -> float | None:
        grid = self._tile(tile_name(lat, lon))
        if grid is None:
            return None
        steps = grid.shape[0] - 1  # samples per degree; edges are shared with the neighbouring tile
        row = round((math.floor(lat) + 1 - lat) * steps)
        col = round((lon - math.floor(lon)) * steps)
        value = int(grid[min(max(row, 0), steps), min(max(col, 0), steps)])
        return None if value == VOID else float(value)

    def climb_descent(self, points: list[tuple[float, float]]) -> tuple[float, float]:
        """Metres climbed and descended along a path; unknown heights are skipped."""
        heights = [h for p in points if (h := self.elevation(*p)) is not None]
        steps = np.diff(heights) if len(heights) > 1 else np.array([])
        return float(steps[steps > 0].sum()), float(-steps[steps < 0].sum())
