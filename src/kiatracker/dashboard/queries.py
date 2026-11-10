"""Everything the dashboard shows, as plain functions: DuckDB connection + period in, pandas out.

No Streamlit here, so it is unit-tested directly. Queries select zones, never coordinates or the VIN.
Database timestamps are naive UTC; results are converted to local wall-clock time.
"""

import statistics
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
    sql = """select start_ts, end_ts, distance_km, energy_kwh, kwh_per_100km, start_zone, end_zone, quality
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
        "quality",
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


BUCKETS = {"week": "%G-W%V", "month": "%Y-%m", "year": "%Y"}


def costs(con, period: Period, assume: CostAssumptions, freq: str = "month") -> pd.DataFrame:
    """Per week, month or year (`bucket`): what the EV's energy cost, against a petrol and a diesel car over
    the same distance, at Hungarian prices (forint) and, for comparison, Austrian prices (euro). Fuel prices
    are those of each drive's month, so the totals are the same whichever bucket is chosen."""
    columns = [
        "bucket",
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
    prices = {m: fuel_price_for_month(con, m) for m in d["month"].unique()}
    grid_kwh = d["battery_kwh"] / (1 - assume.charging_loss_pct / 100)
    petrol_l = d["distance_km"] * assume.petrol_l_per_100km / 100
    diesel_l = d["distance_km"] * assume.diesel_l_per_100km / 100

    def price(name: str) -> pd.Series:
        return d["month"].map(lambda m: prices[m][name])

    d["ev_huf"] = grid_kwh * assume.hu_electricity_huf
    d["petrol_huf"] = petrol_l * price("hu_petrol_huf")
    d["diesel_huf"] = diesel_l * price("hu_diesel_huf")
    d["ev_at_eur"] = grid_kwh * assume.at_electricity_eur
    d["petrol_at_eur"] = petrol_l * price("at_petrol_eur")
    d["diesel_at_eur"] = diesel_l * price("at_diesel_eur")
    d["bucket"] = d["start_local"].dt.strftime(BUCKETS[freq])
    return d.groupby("bucket", as_index=False)[columns[1:]].sum()[columns]


def bucket_label(bucket: str, freq: str) -> str:
    """'the week of 2 Nov', 'October' or '2025'."""
    if freq == "week":
        monday = date.fromisocalendar(int(bucket[:4]), int(bucket[6:]), 1)
        return f"the week of {monday.day} {monday:%b}"
    if freq == "month":
        return f"{date.fromisoformat(bucket + '-01'):%B}"
    return bucket


def savings(df: pd.DataFrame, freq: str, today: date) -> pd.DataFrame:
    """Saved against petrol per bucket; `complete` is False for the bucket today falls in."""
    current = today.strftime(BUCKETS[freq])
    out = df[["bucket", "distance_km", "ev_huf", "petrol_huf"]].copy()
    out["saved_huf"] = out["petrol_huf"] - out["ev_huf"]
    out["complete"] = out["bucket"] != current
    return out


# (factor, column, harder condition, its label, easier condition, its label)
CONDITIONS = [
    ("Cold", "temp_c", lambda v: v < 5, "below 5 °C", lambda v: v >= 10, "10 °C or warmer"),
    ("Wind", "wind_kph", lambda v: v >= 20, "20 km/h or more", lambda v: v < 10, "under 10 km/h"),
    ("Motorway speed", "speed_kph", lambda v: v >= 70, "average 70 km/h+", lambda v: v < 50, "under 50 km/h"),
    ("Short trips", "distance_km", lambda v: v < 10, "5-10 km", lambda v: v >= 30, "30 km or longer"),
]
MIN_PER_SIDE = 3


def condition_effects(con, period: Period) -> pd.DataFrame:
    """How much more energy per km harder conditions took than easier ones, straight from the drives."""
    d = drives(con, period)
    d = d[d["kwh_per_100km"].notna()]
    rows = []
    for factor, column, harder, harder_label, easier, easier_label in CONDITIONS:
        values = d[column]
        hard, easy = d[values.notna() & harder(values)], d[values.notna() & easier(values)]
        hard_kwh = consumption(hard["energy_kwh"], hard["distance_km"])
        easy_kwh = consumption(easy["energy_kwh"], easy["distance_km"])
        enough = len(hard) >= MIN_PER_SIDE and len(easy) >= MIN_PER_SIDE
        diff = hard_kwh - easy_kwh if hard_kwh is not None and easy_kwh is not None else None
        rows.append(
            {
                "factor": factor,
                "harder_label": harder_label,
                "easier_label": easier_label,
                "harder_kwh": hard_kwh,
                "easier_kwh": easy_kwh,
                "diff_kwh": diff,
                "pct": diff / easy_kwh if diff is not None and easy_kwh else None,
                "n_harder": len(hard),
                "n_easier": len(easy),
                "enough": enough,
            }
        )
    return pd.DataFrame(rows)


@dataclass(frozen=True)
class UsualCharge:
    level: int  # %
    sessions: int  # slow sessions it was learned from
    at_level: int  # of those, how many ended at `level`
    assumed: bool  # too few sessions: 80 % is assumed
    clamped: bool = False  # the battery already holds more than the usual level: today's reading is used


USUAL_FALLBACK = 80
USUAL_LOOKBACK = 20
USUAL_MIN_SESSIONS = 5
FAST_KW = 22.0  # above this a session is DC fast charging, which says nothing about the daily habit


def usual_charge_level(con, latest_soc: float | None) -> UsualCharge:
    """The level you usually charge to: the median end of the last 20 slow sessions, rounded to 5 %.

    Fewer than 5 sessions: 80 %, marked assumed. Never below the latest reading, never above 100 %."""
    ends: list[float] = []
    if has_table(con, "charging_sessions"):
        ends = [
            end
            for (end,) in con.execute(
                "select soc_end from charging_sessions where not in_progress and soc_end is not null "
                "and (avg_kw is null or avg_kw <= ?) order by start_ts desc limit ?",
                [FAST_KW, USUAL_LOOKBACK],
            ).fetchall()
        ]
    rounded = [int(5 * round(end / 5)) for end in ends]
    if len(rounded) < USUAL_MIN_SESSIONS:
        level, at_level, assumed = USUAL_FALLBACK, 0, True
    else:
        level = int(5 * round(statistics.median(ends) / 5))
        at_level, assumed = rounded.count(level), False
    clamped = latest_soc is not None and round(latest_soc) > level
    if clamped:
        level, at_level, assumed = round(latest_soc), 0, False
    return UsualCharge(min(level, 100), len(rounded), at_level, assumed, clamped)


def monthly(con, period: Period) -> pd.DataFrame:
    """Distance and distance-weighted consumption per local month (drives with a measured consumption)."""
    d = _drives(con, period)
    d["month"] = d["start_local"].dt.strftime("%Y-%m")
    d["measured_km"] = d["distance_km"].where(d["kwh_per_100km"].notna(), 0)
    d["measured_kwh"] = d["energy_kwh"].where(d["kwh_per_100km"].notna(), 0)
    g = d.groupby("month", as_index=False)[["distance_km", "measured_km", "measured_kwh"]].sum()
    g["kwh_per_100km"] = (g["measured_kwh"] / g["measured_km"] * 100).where(g["measured_km"] > 0)
    return g[["month", "distance_km", "kwh_per_100km"]]


def commute_pair(con, period: Period) -> tuple[str, str, float] | None:
    """The most frequent trip between two different zones, and its median distance in km."""
    d = _drives(con, period)
    d = d[d["start_zone"].notna() & d["end_zone"].notna() & (d["start_zone"] != d["end_zone"])]
    if d.empty:
        return None
    counts = d.groupby(["start_zone", "end_zone"]).size().sort_values(ascending=False)
    start, end = counts.index[0]
    km = d[(d["start_zone"] == start) & (d["end_zone"] == end)]["distance_km"].median()
    return start, end, float(km)


def _zones(start: str, end: str) -> str:
    return f"{start.capitalize()} → {end.capitalize()}"


def tips_facts(con, period: Period, outlook: list[dict], today: date) -> list[tuple[str, str, str]]:
    """Up to three 'worth knowing' tips, each only when its condition holds: (icon, tint, sentence)."""
    from kiatracker.dashboard import theme

    tips = []
    soon = [r["temp_min"] for r in outlook[:3] if r.get("temp_min") is not None]
    if soon and min(soon) < 5:
        pair = commute_pair(con, period)
        saving = round(0.8 * (pair[2] / 30 if pair else 1), 1)
        tips.append(
            (
                "❄",
                theme.TINT_SKY,
                f"Below 5 °C, pre-heat while plugged in: about {saving:.1f} kWh saved on your commute.",
            )
        )
    week = Period(today - timedelta(days=6), today)
    d = drives(con, week)
    d = d[d["kwh_per_100km"].notna() & d["start_zone"].notna() & d["end_zone"].notna()]
    best = None
    for (start, end), group in d.groupby(["start_zone", "end_zone"]):
        if len(group) < 2:
            continue
        lo, hi = group.loc[group["kwh_per_100km"].idxmin()], group.loc[group["kwh_per_100km"].idxmax()]
        similar = abs(lo["distance_km"] - hi["distance_km"]) <= 0.15 * hi["distance_km"]
        gap = 1 - lo["kwh_per_100km"] / hi["kwh_per_100km"]
        if similar and gap >= 0.05 and (best is None or gap > best[0]):
            best = (gap, start, end, lo, hi)
    if best:
        gap, start, end, lo, hi = best
        warmer = ""
        if pd.notna(lo["temp_c"]) and pd.notna(hi["temp_c"]) and lo["temp_c"] > hi["temp_c"]:
            warmer = f" Same trip, {lo['temp_c'] - hi['temp_c']:.0f} °C warmer."
        tips.append(
            (
                "↯",
                theme.TINT_CORAL,
                f"{lo['start_local']:%A}'s {_zones(start, end)} drive used {gap:.0%} less than "
                f"{hi['start_local']:%A}'s.{warmer}",
            )
        )
    s = _sessions(con, period)
    total = s["energy_kwh"].sum()
    if total > 0 and s["zone"].notna().any():
        home = s.loc[s["zone"] == "home", "energy_kwh"].sum() / total
        tips.append(("⌂", theme.TINT_SUN, f"{home:.0%} of your charging happened at home."))
    return tips[:3]


def _measured(d: pd.DataFrame) -> pd.DataFrame:
    return d[d["kwh_per_100km"].notna() & (d["distance_km"] >= 5)]


def _from_to(drive) -> str:
    if pd.isna(drive["start_zone"]) or pd.isna(drive["end_zone"]):
        return ""
    return f" from {drive['start_zone']} to {drive['end_zone']}"


def briefing_facts(con, period: Period, today: date) -> list[tuple[str, str, str, str]]:
    """Up to three items for the Drives briefing, over the 7 days ending today: (icon, tint, title, text)."""
    from kiatracker.dashboard import theme

    week = drives(con, Period(today - timedelta(days=6), today))
    if week.empty:
        return []
    facts = []
    effects = condition_effects(con, period)
    effects = effects[effects["enough"] & effects["pct"].notna() & (effects["pct"] > 0)]
    if not effects.empty:
        top = effects.loc[effects["pct"].idxmax()]
        factor, column, harder, *_ = next(c for c in CONDITIONS if c[0] == top["factor"])
        values = week[column].dropna()
        touched = int(harder(values).sum()) if not values.empty else 0
        title = "Cold costs you most" if factor == "Cold" else f"{factor} costs you most"
        facts.append(
            (
                "❄" if factor == "Cold" else "≋",
                theme.TINT_SKY,
                title,
                f"{top['pct']:.0%} more energy per km {top['harder_label']} than {top['easier_label']}. "
                f"{touched} of this week's {len(week)} drives were {top['harder_label']}.",
            )
        )
    this, last = (
        _measured(week),
        _measured(drives(con, Period(today - timedelta(days=13), today - timedelta(days=7)))),
    )
    this_kwh = consumption(this["energy_kwh"], this["distance_km"])
    last_kwh = consumption(last["energy_kwh"], last["distance_km"])
    if this_kwh is not None and last_kwh is not None:
        change = this_kwh / last_kwh - 1
        better = change <= 0
        facts.append(
            (
                "↘" if better else "↗",
                theme.TINT_GREEN if better else theme.TINT_CORAL,
                "A better week" if better else "A harder week",
                f"{len(week)} drives, {week['distance_km'].sum():.0f} km at {this_kwh:.1f} kWh/100 km: "
                f"{abs(change):.0%} {'less' if better else 'more'} than last week.",
            )
        )
    if not this.empty:
        best = this.loc[this["kwh_per_100km"].idxmin()]
        temp = f" at {best['temp_c']:.0f} °C" if pd.notna(best["temp_c"]) else ""
        facts.append(
            (
                "★",
                theme.TINT_SUN,
                "Best drive",
                f"{best['start_local']:%A}'s drive{_from_to(best)}: "
                f"{best['kwh_per_100km']:.1f} kWh/100 km{temp}.",
            )
        )
    return facts


def day_label(day: date, today: date) -> str:
    if day == today:
        return "Today"
    if day == today - timedelta(days=1):
        return "Yesterday"
    if today - day < timedelta(days=7):
        return f"{day:%A}"
    return f"{day:%a} {day.day} {day:%b}"


def recent_drives(con, today: date, n: int = 8) -> pd.DataFrame:
    """The latest drives with a day label (Today, Yesterday, a weekday, or a date) and local start time."""
    d = drives(con, Period(today - timedelta(days=60), today)).head(n).copy()
    d["day_label"] = [day_label(ts.date(), today) for ts in d["start_local"]]
    d["time"] = [f"{ts:%H:%M}" for ts in d["start_local"]]
    return d[["day_label", "time", "start_zone", "end_zone", "distance_km", "kwh_per_100km", "temp_c"]]


def plug_hours(con, period: Period) -> pd.DataFrame:
    """Finished charging sessions by local start hour, all 24 hours present."""
    s = _sessions(con, period)
    counts = s["start_local"].dt.hour.value_counts() if not s.empty else pd.Series(dtype=int)
    return pd.DataFrame({"hour": range(24), "sessions": [int(counts.get(h, 0)) for h in range(24)]})
