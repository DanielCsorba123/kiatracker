"""Energy prices for the cost comparison, so nobody has to type them in.

Fuel: the European Commission's Weekly Oil Bulletin, the official weekly average pump price per EU country
with all taxes, history back to 2005. One file covers Hungary and Austria, petrol (Euro-super 95) and diesel,
plus the forint exchange rate. It is fetched at most once a week and kept as a raw record.

Electricity has no comparable open feed, so household prices are documented defaults the page shows as
assumptions.
"""

import io
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
import openpyxl

from kiatracker.raw import append_record, read_records

OIL_BULLETIN_URL = (
    "https://energy.ec.europa.eu/document/download/906e60ca-8b6a-44e7-8589-652854d2fd3f_en"
    "?filename=Weekly_Oil_Bulletin_Prices_History_maticni_4web.xlsx"
)
SHEET = "Prices with taxes"
SINCE = date(2024, 1, 1)
REFETCH_AFTER = timedelta(days=7)

# Household electricity, gross per kWh. Hungary's regulated tariff has two bands: up to the average
# consumption (2,523 kWh/year) and above it. With yearly net metering ("szaldó") and solar, the car's
# extra kWh land above the band. Check your own bill; these are defaults, not data.
ELECTRICITY = {
    "hu_below_average_huf": 36.0,
    "hu_above_average_huf": 70.1,
    "at_household_eur": 0.30,  # E-Control: typically 25-35 cents per kWh
}


def parse_oil_bulletin(xlsx: bytes, since: date = SINCE) -> list[dict]:
    """Weekly Hungarian and Austrian petrol and diesel prices per litre, in euro and forint."""
    sheet = openpyxl.load_workbook(io.BytesIO(xlsx), read_only=True, data_only=True)[SHEET]
    rows = sheet.iter_rows(values_only=True)
    header = next(rows)
    col = {name: i for i, name in enumerate(header) if isinstance(name, str)}
    wanted = [
        "AT_price_with_tax_euro95",
        "AT_price_with_tax_diesel",
        "HU_exchange_rate",
        "HU_price_with_tax_euro95",
        "HU_price_with_tax_diesel",
    ]
    weeks = []
    for row in rows:
        day = row[0]
        if not isinstance(day, datetime) or day.date() < since:
            continue
        values = [row[col[name]] if name in col else None for name in wanted]
        if any(not isinstance(v, int | float) or v <= 0 for v in values):
            continue
        at95, atd, eur_per_huf, hu95, hud = values
        weeks.append(
            {
                "week": day.date().isoformat(),
                "at_petrol_eur": at95 / 1000,
                "at_diesel_eur": atd / 1000,
                "hu_petrol_eur": hu95 / 1000,
                "hu_diesel_eur": hud / 1000,
                "huf_per_eur": 1 / eur_per_huf,
                "hu_petrol_huf": hu95 / 1000 / eur_per_huf,
                "hu_diesel_huf": hud / 1000 / eur_per_huf,
            }
        )
    return sorted(weeks, key=lambda w: w["week"])


def download_oil_bulletin(http: httpx.Client) -> bytes:
    response = http.get(OIL_BULLETIN_URL, timeout=120, follow_redirects=True)
    response.raise_for_status()
    return response.content


def store_fuel_prices(raw_dir: Path, weeks: list[dict], now: datetime) -> None:
    append_record(
        raw_dir, "fuel", {"fetched_at": now.isoformat(), "source": OIL_BULLETIN_URL, "weeks": weeks}, now
    )


def _latest_record(raw_dir: Path) -> dict | None:
    latest = None
    for record in read_records(raw_dir, "fuel"):
        if record.get("weeks"):
            latest = record
    return latest


def load_fuel_prices(raw_dir: Path) -> list[dict]:
    record = _latest_record(raw_dir)
    return record["weeks"] if record else []


def fuel_is_stale(raw_dir: Path, now: datetime) -> bool:
    record = _latest_record(raw_dir)
    return record is None or now - datetime.fromisoformat(record["fetched_at"]) > REFETCH_AFTER
