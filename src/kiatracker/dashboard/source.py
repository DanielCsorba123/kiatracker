"""Which database the dashboard shows: the owner's, or a generated demo. Fails closed.

The app shows demo data unless personal mode is switched on explicitly with KIATRACKER_PERSONAL=1, which
`kiatracker dashboard` sets and nothing else does. KIATRACKER_DEMO (any value but 0/false/empty) always
wins, so a public deployment can't reach personal data by accident, whatever files sit next to it.
"""

import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from kiatracker.config import Settings
from kiatracker.db import build_database
from kiatracker.synthetic import FAKE_HOME, FakeTerrain, generate

DEMO_ENV = "KIATRACKER_DEMO"
PERSONAL_ENV = "KIATRACKER_PERSONAL"
CONTAINER_ENV = "KIATRACKER_IN_CONTAINER"
OFF = {"", "0", "false", "no", "off"}
LOCAL_ADDRESSES = {"127.0.0.1", "localhost", "::1"}


@dataclass(frozen=True)
class DataSource:
    db_path: Path | None  # None for demo: the app builds its own private demo database
    demo: bool


def resolve_source(personal_db: Path, environ: Mapping[str, str] = os.environ) -> DataSource:
    demo_forced = environ.get(DEMO_ENV, "").strip().lower() not in OFF
    if environ.get(PERSONAL_ENV) == "1" and not demo_forced:
        return DataSource(personal_db, demo=False)
    return DataSource(None, demo=True)


def is_local_only(address: str | None) -> bool:
    """True if the server only listens on this computer. Streamlit's default (unset) means every interface."""
    return address in LOCAL_ADDRESSES


def may_show_personal(address: str | None, environ: Mapping[str, str] = os.environ) -> bool:
    """Personal data only when reachable from this computer alone.

    Inside a container Streamlit has to listen on 0.0.0.0; KIATRACKER_IN_CONTAINER=1 declares that the
    container's port is published on the host's 127.0.0.1 only (as docker-compose.yml does).
    """
    return is_local_only(address) or environ.get(CONTAINER_ENV) == "1"


def build_demo_database(target_dir: Path | None = None, days: int = 365, seed: int = 7) -> Path:
    """Generate fake raw data ending yesterday and build it, by default in a new private temp folder."""
    target_dir = target_dir or Path(tempfile.mkdtemp(prefix="kiatracker-demo-"))
    settings = Settings(None, None, target_dir, home=FAKE_HOME, home_radius_km=0.3)
    start = datetime.combine(date.today() - timedelta(days=days), datetime.min.time(), UTC)
    generate(settings.raw_dir, start, days, seed)
    build_database(settings, FakeTerrain())
    return settings.db_path
