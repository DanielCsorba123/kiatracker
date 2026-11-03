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

from kiatracker.prices import ELECTRICITY

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
             from drives where start_ts >= ? and start_ts < ? and distance_km is not null
               and not in_progress"""  # a drive still under way has no end, energy or weather yet
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
    d["speed_kph"] = (d["distance_km"] / d["minutes"] * 60).where(d["minutes"] > 0)
    columns = [
        "start_local",
        "distance_km",
        "minutes",
        "speed_kph",
        "kwh_per_100km",
        "energy_kwh",
        "temp_c",
        "wind_kph",
        "start_zone",
        "end_zone",
    ]
    return d.sort_values("start_local", ascending=False)[columns].reset_index(drop=True)


def consumption_by_band(con, period: Period, column: str, edges: list[float]) -> pd.DataFrame:
    """Distance-weighted consumption per band of temperature, wind, trip length or speed.

    `lo` and `hi` are the band's numeric edges, for drawing the average across the band's width.
    """
    d = drives(con, period)
    d = d[d["kwh_per_100km"].notna() & d[column].notna()]
    labels = [f"{a:g} to {b:g}" for a, b in zip(edges, edges[1:], strict=False)]
    labels[0], labels[-1] = f"under {edges[1]:g}", f"{edges[-2]:g}+"  # outer edges are only catch-alls
    d["band"] = pd.cut(d[column], edges, labels=labels, right=False)
    rows = []
    edge = dict(zip(labels, zip(edges, edges[1:], strict=False), strict=True))
    for band, group in d.groupby("band", observed=True):
        rows.append(
            {
                "band": str(band),
                "lo": edge[str(band)][0],
                "hi": edge[str(band)][1],
                "kwh_per_100km": consumption(group["energy_kwh"], group["distance_km"]),
                "drives": len(group),
            }
        )
    return pd.DataFrame(rows, columns=["band", "lo", "hi", "kwh_per_100km", "drives"])


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


@dataclass(frozen=True)
class CostAssumptions:
    """What the comparison assumes; the page shows these and lets you change them."""

    petrol_l_per_100km: float = 6.5  # a comparable compact petrol SUV
    diesel_l_per_100km: float = 5.5  # the same car with a diesel engine
    charging_loss_pct: float = 10.0  # wall to battery, home AC charging
    hu_electricity_huf: float = ELECTRICITY["hu_above_average_huf"]
    at_electricity_eur: float = ELECTRICITY["at_household_eur"]


FUEL_COLUMNS = ["at_petrol_eur", "at_diesel_eur", "hu_petrol_huf", "hu_diesel_huf", "huf_per_eur"]


def fuel_price_for_month(con, month: str) -> dict | None:
    """Average weekly pump prices in a month; for a month without data, the latest earlier month's."""
    if not has_table(con, "fuel_prices"):
        return None
    averages = ", ".join(f"avg({c}) as {c}" for c in FUEL_COLUMNS)
    rows = con.execute(
        f"""select substr(week, 1, 7) as month, {averages} from fuel_prices
            where substr(week, 1, 7) <= ? group by month order by month desc limit 1""",
        [month],
    ).fetchall()
    return dict(zip(["month", *FUEL_COLUMNS], rows[0], strict=True)) if rows else None


def latest_fuel_week(con) -> str | None:
    if not has_table(con, "fuel_prices"):
        return None
    return con.execute("select max(week) from fuel_prices").fetchone()[0]


def costs(con, period: Period, assume: CostAssumptions) -> pd.DataFrame:
    """Per month: what the EV's energy cost, against a petrol and a diesel car over the same distance,
    at Hungarian prices (forint) and, for comparison, Austrian prices (euro)."""
    columns = [
        "month",
        "distance_km",
        "battery_kwh",
        "ev_huf",
        "petrol_huf",
        "diesel_huf",
        "ev_at_eur",
        "petrol_at_eur",
        "diesel_at_eur",
    ]
    d = _drives(con, period)
    if d.empty or latest_fuel_week(con) is None:
        return pd.DataFrame(columns=columns)
    # energy of each drive from its charge used; drives too short to measure get the period's average
    measured = d[d["energy_kwh"].notna() & (d["energy_kwh"] > 0)]
    per_km = measured["energy_kwh"].sum() / measured["distance_km"].sum() if not measured.empty else 0.17
    d["battery_kwh"] = d["energy_kwh"].where(d["energy_kwh"] > 0, d["distance_km"] * per_km)
    d["month"] = d["start_local"].dt.strftime("%Y-%m")
    monthly = d.groupby("month", as_index=False)[["distance_km", "battery_kwh"]].sum()
    rows = []
    for m in monthly.itertuples():
        price = fuel_price_for_month(con, m.month)
        grid_kwh = m.battery_kwh / (1 - assume.charging_loss_pct / 100)
        petrol_l = m.distance_km * assume.petrol_l_per_100km / 100
        diesel_l = m.distance_km * assume.diesel_l_per_100km / 100
        rows.append(
            {
                "month": m.month,
                "distance_km": m.distance_km,
                "battery_kwh": m.battery_kwh,
                "ev_huf": grid_kwh * assume.hu_electricity_huf,
                "petrol_huf": petrol_l * price["hu_petrol_huf"],
                "diesel_huf": diesel_l * price["hu_diesel_huf"],
                "ev_at_eur": grid_kwh * assume.at_electricity_eur,
                "petrol_at_eur": petrol_l * price["at_petrol_eur"],
                "diesel_at_eur": diesel_l * price["at_diesel_eur"],
            }
        )
    return pd.DataFrame(rows, columns=columns)
