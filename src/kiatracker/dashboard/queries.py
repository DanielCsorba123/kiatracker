"""Everything the dashboard shows, as plain functions: DuckDB connection + period in, pandas out.

No Streamlit here, so it is unit-tested directly. Queries select zones, never coordinates or the VIN.
Database timestamps are naive UTC; results are converted to local wall-clock time.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import pandas as pd

LOCAL = ZoneInfo("Europe/Budapest")


@dataclass(frozen=True)
class Period:
    """Local calendar dates, both inclusive."""

    start: date
    end: date

    def utc_bounds(self) -> tuple[datetime, datetime]:
        def utc(d: date) -> datetime:
            return datetime.combine(d, time.min, LOCAL).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

        return utc(self.start), utc(self.end + timedelta(days=1))


def connect(db_path: Path) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(db_path), read_only=True)


def has_table(con: duckdb.DuckDBPyConnection, table: str) -> bool:
    sql = "select count(*) from information_schema.tables where table_name = ?"
    return con.execute(sql, [table]).fetchone()[0] > 0


def to_local(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series).dt.tz_localize("UTC").dt.tz_convert(LOCAL).dt.tz_localize(None)


def week_of(local: pd.Series) -> pd.Series:
    return (local - pd.to_timedelta(local.dt.day_of_week, unit="D")).dt.normalize()


def consumption(energy: pd.Series, distance: pd.Series) -> float | None:
    km = distance.sum()
    return float(energy.sum() / km * 100) if km else None


def _drives(con, period: Period) -> pd.DataFrame:
    sql = """select start_ts, end_ts, distance_km, energy_kwh, kwh_per_100km, start_zone, end_zone
             from drives where start_ts >= ? and start_ts < ? and distance_km is not null"""
    df = con.execute(sql, list(period.utc_bounds())).df()
    df["start_local"] = to_local(df["start_ts"])
    return df


def _sessions(con, period: Period) -> pd.DataFrame:
    sql = """select start_ts, zone, soc_start, soc_end, energy_kwh, hours, avg_kw from charging_sessions
             where start_ts >= ? and start_ts < ? and not in_progress"""
    df = con.execute(sql, list(period.utc_bounds())).df()
    df["start_local"] = to_local(df["start_ts"])
    return df


def _latest(con, table: str, column: str) -> float | None:
    if not has_table(con, table):
        return None
    row = con.execute(
        f"select {column} from {table} where {column} is not null order by ts desc limit 1"
    ).fetchone()
    return float(row[0]) if row else None


def kpis(con, period: Period) -> dict:
    d = _drives(con, period)
    measured = d[d["kwh_per_100km"].notna()]
    s = _sessions(con, period)
    return {
        "distance_km": float(d["distance_km"].sum()),
        "drives": len(d),
        "kwh_per_100km": consumption(measured["energy_kwh"], measured["distance_km"]),
        "energy_charged_kwh": float(s["energy_kwh"].sum()),
        "latest_soc": _latest(con, "readings_battery", "soc"),
        "latest_range_km": _latest(con, "readings_range", "range_km"),
    }


def weekly(con, period: Period) -> pd.DataFrame:
    d = _drives(con, period)
    d["week"] = week_of(d["start_local"])
    d["measured_km"] = d["distance_km"].where(d["kwh_per_100km"].notna(), 0)
    d["measured_kwh"] = d["energy_kwh"].where(d["kwh_per_100km"].notna(), 0)
    g = d.groupby("week", as_index=False)[["distance_km", "measured_km", "measured_kwh"]].sum()
    g["kwh_per_100km"] = (g["measured_kwh"] / g["measured_km"] * 100).where(g["measured_km"] > 0)
    return g[["week", "distance_km", "kwh_per_100km"]]


def drives(con, period: Period) -> pd.DataFrame:
    d = _drives(con, period)
    if has_table(con, "drive_weather"):
        sql = """select d.start_ts, w.temp_c, w.wind_kph from drives d join drive_weather w using (drive_id)
                 where d.start_ts >= ? and d.start_ts < ?"""
        d = d.merge(con.execute(sql, list(period.utc_bounds())).df(), on="start_ts", how="left")
    else:
        d["temp_c"] = d["wind_kph"] = None
    d["minutes"] = (pd.to_datetime(d["end_ts"]) - pd.to_datetime(d["start_ts"])).dt.total_seconds() / 60
    columns = [
        "start_local",
        "distance_km",
        "minutes",
        "kwh_per_100km",
        "energy_kwh",
        "temp_c",
        "wind_kph",
        "start_zone",
        "end_zone",
    ]
    return d.sort_values("start_local", ascending=False)[columns].reset_index(drop=True)


def consumption_by_band(con, period: Period, column: str, edges: list[float]) -> pd.DataFrame:
    """Distance-weighted consumption per band of temperature, wind or trip length."""
    d = drives(con, period)
    d = d[d["kwh_per_100km"].notna() & d[column].notna()]
    labels = [f"{a:g} to {b:g}" for a, b in zip(edges, edges[1:], strict=False)]
    labels[0], labels[-1] = f"under {edges[1]:g}", f"{edges[-2]:g}+"  # outer edges are only catch-alls
    d["band"] = pd.cut(d[column], edges, labels=labels, right=False)
    rows = []
    for band, group in d.groupby("band", observed=True):
        rows.append(
            {
                "band": str(band),
                "kwh_per_100km": consumption(group["energy_kwh"], group["distance_km"]),
                "drives": len(group),
            }
        )
    return pd.DataFrame(rows, columns=["band", "kwh_per_100km", "drives"])


def charging_sessions(con, period: Period) -> pd.DataFrame:
    s = _sessions(con, period)
    columns = ["start_local", "zone", "soc_start", "soc_end", "energy_kwh", "hours", "avg_kw"]
    return s.sort_values("start_local", ascending=False)[columns].reset_index(drop=True)


def weekly_charging(con, period: Period) -> pd.DataFrame:
    s = _sessions(con, period)
    s["week"] = week_of(s["start_local"])
    g = s.groupby("week", as_index=False).agg(
        energy_kwh=("energy_kwh", "sum"), sessions=("energy_kwh", "size")
    )
    return g[["week", "energy_kwh", "sessions"]]


def costs(
    con,
    period: Period,
    electricity_per_kwh: float,
    petrol_per_litre: float,
    petrol_l_per_100km: float,
    charging_loss_pct: float,
) -> pd.DataFrame:
    """Monthly cost of the electricity charged vs the petrol the same distance would have needed."""
    d, s = _drives(con, period), _sessions(con, period)
    d["month"] = d["start_local"].dt.strftime("%Y-%m")
    s["month"] = s["start_local"].dt.strftime("%Y-%m")
    distance = d.groupby("month")["distance_km"].sum()
    charged = s.groupby("month")["energy_kwh"].sum()
    out = pd.DataFrame({"distance_km": distance, "charged_kwh": charged}).fillna(0).sort_index()
    out["electricity_cost"] = out["charged_kwh"] / (1 - charging_loss_pct / 100) * electricity_per_kwh
    out["petrol_cost"] = out["distance_km"] * petrol_l_per_100km / 100 * petrol_per_litre
    out["savings"] = out["petrol_cost"] - out["electricity_cost"]
    out = out.rename_axis("month").reset_index()
    return out[["month", "distance_km", "electricity_cost", "petrol_cost", "savings"]]
