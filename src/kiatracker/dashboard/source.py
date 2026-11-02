"""Which database the dashboard shows: the personal one, or a generated demo.

KIATRACKER_DEMO=1 (set on any public deployment) forces the demo, so a public instance has no path to
personal data, whatever files happen to be next to it.
"""

import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from kiatracker.config import Settings
from kiatracker.db import build_database
from kiatracker.synthetic import FAKE_HOME, generate

DEMO_ENV = "KIATRACKER_DEMO"
DEMO_DIR = Path(tempfile.gettempdir()) / "kiatracker-demo"


@dataclass(frozen=True)
class DataSource:
    db_path: Path
    demo: bool


def resolve_source(
    personal_db: Path, demo_requested: bool, environ: Mapping[str, str] = os.environ
) -> DataSource:
    if demo_requested or environ.get(DEMO_ENV) == "1":
        return DataSource(DEMO_DIR / "kiatracker.duckdb", demo=True)
    return DataSource(personal_db, demo=False)


def build_demo_database(target_dir: Path = DEMO_DIR, days: int = 60, seed: int = 7) -> Path:
    """Generate fake raw data ending yesterday and build it. Rebuilds from scratch each call."""
    settings = Settings(None, None, target_dir, home=FAKE_HOME, home_radius_km=0.3)
    for old in settings.raw_dir.glob("*.jsonl"):
        old.unlink()
    start = datetime.combine(date.today() - timedelta(days=days), datetime.min.time(), UTC)
    generate(settings.raw_dir, start, days, seed)
    build_database(settings)
    return settings.db_path
