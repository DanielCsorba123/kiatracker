import gzip

import numpy as np
import pytest

from kiatracker.elevation import Terrain, tile_name


def write_tile(folder, name, size, fill):
    """A miniature SRTM tile: big-endian int16, north row first, `size` x `size` samples."""
    folder.mkdir(parents=True, exist_ok=True)
    grid = np.asarray(fill(size), dtype=">i2")
    (folder / f"{name}.hgt").write_bytes(grid.tobytes())


def test_tile_names_follow_srtm_convention():
    assert tile_name(10.6, 18.2) == "N10E018"
    assert tile_name(47.0, 18.0) == "N47E018"
    assert tile_name(-0.5, -0.5) == "S01W001"


def test_lookup_reads_the_right_sample(tmp_path):
    # 11 x 11 samples over one degree: 100 m in the north-west, +10 m per sample east and south
    write_tile(tmp_path, "N47E018", 11, lambda n: [[100 + 10 * (r + c) for c in range(n)] for r in range(n)])
    terrain = Terrain(tmp_path, download=None)
    assert terrain.elevation(47.99999, 18.0) == 100  # north-west corner (48.0 itself is the next tile)
    assert terrain.elevation(47.0, 18.99999) == 300  # south-east corner
    assert terrain.elevation(47.5, 18.5) == 200  # middle


def test_voids_and_missing_tiles_are_none(tmp_path):
    write_tile(tmp_path, "N47E018", 3, lambda n: [[-32768] * n for _ in range(n)])
    terrain = Terrain(tmp_path, download=None)
    assert terrain.elevation(47.5, 18.5) is None
    assert terrain.elevation(10.0, 10.0) is None  # no tile and no downloader


def test_missing_tile_is_downloaded_once(tmp_path):
    calls = []
    raw = np.full((3, 3), 250, dtype=">i2").tobytes()

    def download(name):
        calls.append(name)
        return gzip.compress(raw)

    terrain = Terrain(tmp_path, download=download)
    assert terrain.elevation(47.2, 18.7) == 250
    assert terrain.elevation(47.8, 18.1) == 250
    assert calls == ["N47E018"] and (tmp_path / "N47E018.hgt").exists()


def test_climb_and_descent_over_a_path(tmp_path):
    write_tile(tmp_path, "N47E018", 11, lambda n: [[100 + 10 * c for c in range(n)] for _ in range(n)])
    terrain = Terrain(tmp_path, download=None)
    climb, descent = terrain.climb_descent([(47.5, 18.0), (47.5, 18.5), (47.5, 18.2)])
    assert (climb, descent) == pytest.approx((50, 30))
