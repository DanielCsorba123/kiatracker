"""Settings from environment variables, falling back to a .env (or Notepad's .env.txt) file."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

ENV_FILES = (".env", ".env.txt")


@dataclass(frozen=True)
class Settings:
    client_id: str | None
    client_secret: str | None
    data_dir: Path
    home: tuple[float, float] | None
    home_radius_km: float = 0.3

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "kiatracker.duckdb"


def read_env_file(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("\"'")
    return values


def load_settings(cwd: Path | None = None, environ: Mapping[str, str] = os.environ) -> Settings:
    cwd = cwd or Path.cwd()
    values: dict[str, str] = {}
    for name in ENV_FILES:
        if (cwd / name).exists():
            values = read_env_file(cwd / name)
            break
    values.update(environ)

    lat, lon = values.get("KIATRACKER_HOME_LAT"), values.get("KIATRACKER_HOME_LON")
    data_dir = Path(values.get("KIATRACKER_DATA_DIR", "data"))
    return Settings(
        client_id=values.get("PLEOS_API_KEY_CLIENT_ID") or None,
        client_secret=values.get("PLEOS_API_KEY_CLIENT_SECRET") or None,
        data_dir=data_dir if data_dir.is_absolute() else cwd / data_dir,
        home=(float(lat), float(lon)) if lat and lon else None,
        home_radius_km=float(values.get("KIATRACKER_HOME_RADIUS_KM", "0.3")),
    )
