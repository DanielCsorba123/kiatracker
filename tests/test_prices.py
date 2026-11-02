import io
from datetime import UTC, date, datetime

import openpyxl
import pytest

from kiatracker.prices import fuel_is_stale, load_fuel_prices, parse_oil_bulletin, store_fuel_prices


def bulletin_xlsx(weeks) -> bytes:
    """A miniature of the EU Weekly Oil Bulletin history file, same layout."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Prices with taxes"
    ws.append(
        [
            "Consumer prices...",
            "CTR",
            "AT_price_with_tax_euro95",
            "AT_price_with_tax_diesel",
            "HU_exchange_rate",
            "HU_price_with_tax_euro95",
            "HU_price_with_tax_diesel",
        ]
    )
    ws.append([None, None, "Euro-super 95  (I)", "Gas oil", None, "Euro-super 95  (I)", "Gas oil"])
    ws.append(["Date", None, "1000 l", "1000 l", None, "1000 l", "1000 l"])
    for day, at95, atd, rate, hu95, hud in weeks:
        ws.append([datetime.combine(day, datetime.min.time()), "AT_", at95, atd, rate, hu95, hud])
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


WEEKS = [
    (date(2026, 10, 26), 1772, 2132, 0.0027214587, 1754.02, 1929.57),
    (date(2026, 10, 19), 1817, 2140, 0.0027517887, 1770.79, 1951.18),
    (date(2022, 1, 3), 1300, 1250, 0.0027, 1200, 1250),
]


def test_parse_gives_litre_prices_in_euro_and_forint():
    rows = parse_oil_bulletin(bulletin_xlsx(WEEKS), since=date(2024, 1, 1))
    assert [r["week"] for r in rows] == ["2026-10-19", "2026-10-26"]  # sorted, old weeks dropped
    latest = rows[-1]
    assert latest["at_petrol_eur"] == pytest.approx(1.772) and latest["at_diesel_eur"] == pytest.approx(2.132)
    assert latest["hu_petrol_eur"] == pytest.approx(1.75402)
    assert latest["huf_per_eur"] == pytest.approx(1 / 0.0027214587)
    assert latest["hu_petrol_huf"] == pytest.approx(1.75402 / 0.0027214587)


def test_store_and_load_keeps_only_the_latest_fetch(tmp_path):
    now = datetime(2026, 11, 2, tzinfo=UTC)
    store_fuel_prices(tmp_path, parse_oil_bulletin(bulletin_xlsx(WEEKS[1:2]), date(2024, 1, 1)), now)
    store_fuel_prices(tmp_path, parse_oil_bulletin(bulletin_xlsx(WEEKS), date(2024, 1, 1)), now)
    assert [r["week"] for r in load_fuel_prices(tmp_path)] == ["2026-10-19", "2026-10-26"]


def test_weekly_file_is_fetched_at_most_once_a_week(tmp_path):
    assert fuel_is_stale(tmp_path, datetime(2026, 11, 2, tzinfo=UTC))
    store_fuel_prices(
        tmp_path,
        parse_oil_bulletin(bulletin_xlsx(WEEKS), date(2024, 1, 1)),
        datetime(2026, 11, 2, tzinfo=UTC),
    )
    assert not fuel_is_stale(tmp_path, datetime(2026, 11, 8, tzinfo=UTC))
    assert fuel_is_stale(tmp_path, datetime(2026, 11, 10, tzinfo=UTC))


def test_build_has_a_fuel_prices_table(tmp_path):
    from kiatracker.config import Settings
    from kiatracker.db import build_database

    settings = Settings(None, None, tmp_path, home=None)
    store_fuel_prices(
        settings.raw_dir,
        parse_oil_bulletin(bulletin_xlsx(WEEKS), date(2024, 1, 1)),
        datetime(2026, 11, 2, tzinfo=UTC),
    )
    assert build_database(settings)["fuel_prices"] == 2


def test_demo_data_includes_fuel_prices(tmp_path):
    from kiatracker.synthetic import generate

    generate(tmp_path, datetime(2026, 1, 5, tzinfo=UTC), days=20)
    weeks = load_fuel_prices(tmp_path)
    assert len(weeks) >= 3 and all(w["hu_petrol_huf"] > 300 for w in weeks)


def test_refresh_fetches_fuel_prices_when_stale(tmp_path, monkeypatch, capsys):
    from kiatracker import cli

    monkeypatch.setattr(cli, "fetch_weather", lambda *a, **k: 0)
    monkeypatch.setattr(cli, "fetch_forecast", lambda *a, **k: 200)
    monkeypatch.setattr(cli, "download_oil_bulletin", lambda http: bulletin_xlsx(WEEKS))
    assert cli.main(["--data-dir", str(tmp_path), "refresh"]) == 0
    assert "Fuel prices: 2 weeks" in capsys.readouterr().out
    monkeypatch.setattr(cli, "download_oil_bulletin", lambda http: pytest.fail("fetched twice in a week"))
    assert cli.main(["--data-dir", str(tmp_path), "refresh"]) == 0
