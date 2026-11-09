from datetime import date

import pandas as pd
import pytest

from kiatracker.dashboard import components
from kiatracker.dashboard.queries import UsualCharge

EVIL = "<script>x</script> & co"


def test_every_builder_escapes_markup():
    outputs = (
        components.section_title(EVIL, EVIL),
        components.stat_strip([(EVIL, EVIL, EVIL)]),
        components.icon_list([("❄", components.theme.TINT_SKY, EVIL)]),
        components.chip(EVIL, "sky"),
        components.hidden_title(EVIL),
    )
    for out in outputs:
        assert "<script>" not in out and "&lt;script&gt;" in out and "&amp; co" in out


def test_fmt_ft_rounds_to_hundreds():
    assert components.fmt_ft(60176.4) == "60 200 Ft" and components.fmt_ft(49) == "0 Ft"


def test_stat_strip_has_one_cell_per_item():
    out = components.stat_strip([("Drives", "412", "this year"), ("Distance", "26 418 km", None)])
    assert out.count('class="wr-stat"') == 2 and "this year" in out


def test_hidden_title_is_an_h1():
    assert components.hidden_title("Range").startswith('<h1 class="wr-hidden">')


TODAY_ROW = dict(
    day=date(2026, 11, 9),
    start_soc=76,
    sky="part",
    temp_min=2,
    temp_max=6,
    wind_kph=14,
    wind_dir_deg=270,
    range_km=384,
    range_lo=352,
    range_hi=411,
    lost_cold_km=44,
    lost_wind_km=12,
    mild_km=440,
)
LATER_ROW = dict(
    day=date(2026, 11, 10),
    start_soc=80,
    sky="sun",
    temp_min=1,
    temp_max=8,
    wind_kph=5,
    wind_dir_deg=None,
    range_km=420,
    range_lo=390,
    range_hi=450,
    lost_cold_km=30,
    lost_wind_km=2,
    mild_km=452,
)


def test_forecast_rows_marks_today_and_split():
    out = components.forecast_rows([TODAY_ROW, LATER_ROW], 490, today=date(2026, 11, 9))
    assert "Today" in out and "from 76 %" in out and "−44 cold" in out and "likely 352–411" in out
    assert out.count(components.theme.TINT_CORAL) == 1 and "Tue" in out and "from 80 %" in out


def test_forecast_rows_without_direction_has_no_arrow():
    assert "rotate(" not in components.forecast_rows([LATER_ROW], 490, today=date(2026, 11, 9))


def test_forecast_rows_hide_small_wind_labels():
    out = components.forecast_rows([LATER_ROW], 490, today=date(2026, 11, 9))
    assert "−2<" not in out and "−30 cold" in out


def test_rule_line_variants():
    u = UsualCharge(level=80, sessions=20, at_level=14, assumed=False)
    assert "stopped at 80 % in 14 of your last 20" in components.rule_line(76, u, full=False)
    assert "assume an 80 % charge" in components.rule_line(76, UsualCharge(80, 2, 0, True), full=False)
    assert "full charge" in components.rule_line(76, u, full=True)
    assert "(76 %)" in components.rule_line(76, u, full=True)


def test_whatif_result_bar_against_best_case():
    out = components.whatif_result(272, 298, 321, 672)
    assert "298 km" in out and "likely 272–321 km" in out and "width: 44%" in out


def test_rule_line_when_no_session_ended_exactly_at_the_median():
    out = components.rule_line(70, UsualCharge(level=85, sessions=20, at_level=0, assumed=False), full=False)
    assert "in 0 of" not in out and "usually stop around 85 %" in out and "last 20 charges" in out


@pytest.mark.parametrize(
    "hour,expected", [(6, "Good morning"), (12, "Good afternoon"), (21, "Good evening"), (2, "Good evening")]
)
def test_greeting(hour, expected):
    assert components.greeting(hour) == expected


def test_hero_with_and_without_range():
    out = components.hero(
        "Good morning. It's 6 °C with a light west wind.", 384, 352, 411, 76, "Enough for 6 trips."
    )
    assert (
        "384 km" in out and "between 352 and 411" in out and "76 %" in out and components.theme.CORAL in out
    )
    assert "enough drives" in components.hero("Good morning.", None, None, None, 76, None)


def test_battery_card_shows_missing_values_as_dashes():
    out = components.battery_card(None, 26418, None, None)
    assert "26 418 km" in out and "–" in out


def test_week_strip_highlights_today_only():
    rows = [dict(day=date(2026, 11, 9 + i), sky="sun", temp_max=6, range_km=384 + i) for i in range(7)]
    out = components.week_strip(rows, today=date(2026, 11, 9))
    assert out.count(components.theme.TINT_CORAL) == 1 and "Today" in out and "390" in out


def test_briefing_card_without_facts():
    assert "No drives in the last 7 days" in components.briefing([], "Monday 9 November")


def test_briefing_card_lists_facts():
    out = components.briefing([("❄", components.theme.TINT_SKY, "Cold costs you most", "31 % more")], "Mon")
    assert "Your briefing" in out and "Cold costs you most" in out and "from the last 7 days" in out


def test_range_grid_rounds_to_5_and_labels_wind():
    grid = pd.DataFrame(
        {"temp_c": [-10, 20, -10, 20], "wind_kph": [0, 0, 15, 15], "range_km": [323.4, 418.9, 310.0, 400.0]}
    )
    out = components.range_grid(grid)
    assert "325" in out and "420" in out and "Calm" in out and "Breezy · 15 km/h" in out and "−10 °C" in out


def test_effect_rows_grey_without_enough_drives():
    effects = pd.DataFrame(
        [
            dict(
                factor="Cold",
                harder_label="below 5 °C",
                easier_label="10 °C or warmer",
                pct=0.31,
                enough=True,
            ),
            dict(
                factor="Wind",
                harder_label="20 km/h or more",
                easier_label="under 10 km/h",
                pct=0.09,
                enough=False,
            ),
        ]
    )
    out = components.effect_rows(effects)
    assert "+31 %" in out and components.theme.CORAL in out and components.theme.PALE in out


def test_drive_list_escapes_zone_names_and_groups_days():
    df = pd.DataFrame(
        [
            dict(
                day_label="Today",
                time="07:42",
                start_zone="<b>home</b>",
                end_zone="other",
                distance_km=31.4,
                kwh_per_100km=18.9,
                temp_c=4,
            ),
            dict(
                day_label="Today",
                time="17:20",
                start_zone="other",
                end_zone="home",
                distance_km=31.9,
                kwh_per_100km=17.6,
                temp_c=9,
            ),
        ]
    )
    out = components.drive_list(df)
    assert "<b>" not in out and out.count("Today") == 1 and "18.9 kWh/100" in out
    assert "wr-chip coral" not in out.split("17:20")[1] and "wr-chip sky" in out


def test_peak_window_finds_the_busiest_four_hours():
    df = pd.DataFrame({"hour": range(24), "sessions": [0] * 17 + [5, 9, 8, 6] + [0] * 3})
    start, end, share = components.peak_window(df)
    assert (start, end) == (17, 21) and share == 1.0
    assert "All of your sessions start between 17:00 and 21:00" in components.peak_sentence(df)


def test_peak_sentence_wording():
    df = pd.DataFrame({"hour": range(24), "sessions": [1] * 17 + [6, 6, 6, 6] + [1] * 3})
    assert components.peak_sentence(df).startswith("More than half of your sessions")


def test_typical_charge_bar():
    out = components.typical_charge(34.6, 80.2)
    assert "+46 % per session, typically" in out and "plug in at 35 %" in out and "stop at 80 %" in out


def test_session_list_marks_fast_charges():
    df = pd.DataFrame(
        [
            dict(
                start_local=pd.Timestamp("2026-10-31 13:22"),
                zone="other",
                soc_start=12,
                soc_end=78,
                energy_kwh=51.6,
                avg_kw=96.0,
            ),
            dict(
                start_local=pd.Timestamp("2026-11-08 18:12"),
                zone="<i>home</i>",
                soc_start=34,
                soc_end=80,
                energy_kwh=36.1,
                avg_kw=7.4,
            ),
        ]
    )
    out = components.session_list(df)
    assert components.theme.CORAL in out and components.theme.SKY in out and "<i>" not in out
    assert "Sat 31 Oct" in out and "51.6 kWh" in out and "96 kW" in out


def test_peak_sentence_says_midnight():
    df = pd.DataFrame({"hour": range(24), "sessions": [0] * 20 + [5, 9, 8, 6]})
    assert "between 20:00 and midnight" in components.peak_sentence(df)


def test_common_bins_never_pass_100():
    from kiatracker.dashboard.views.charging import common_bins

    assert (
        common_bins(pd.Series([82.0, 88.0, 100.0, 100.0, 100.0])) == "between 90 and 100 %"
    )  # like the chart


def test_savings_figures_round_and_colour():
    row = pd.Series(
        dict(
            bucket="2026-10",
            distance_km=2150,
            ev_huf=14644.0,
            petrol_huf=74820.0,
            saved_huf=60176.0,
            complete=True,
        )
    )
    out = components.savings_figures(row, "October", 6.5)
    assert "60 200 Ft" in out and "14 600 Ft" in out and "74 800 Ft" in out
    assert components.theme.CORAL_INK in out and "Saved in October" in out and "2 150 km" in out


def test_compare_bars_scale_to_the_largest():
    out = components.compare_bars(
        [
            ("Your EV", 693, "home", components.theme.SKY),
            ("Petrol car", 3480, "6.5 L", components.theme.CORAL),
        ],
        lambda v: f"{v:.0f} Ft",
    )
    assert "width: 20%" in out and "width: 100%" in out and "3480 Ft" in out


def test_route_cards_escape_typed_names():
    from types import SimpleNamespace

    route = SimpleNamespace(label="<img src=x>", roads="A2 & S6")
    e = SimpleNamespace(route=route, kwh_p50=26.4, minutes=84, km=122, arrival_soc_p50=56, climb_m=772)
    out = components.route_cards([e], [1.0], ["#DC756D"])
    assert "<img" not in out and "A2 &amp; S6" in out and "wins 100 of 100" in out
    assert "26.4 kWh" in out and "arrive at 56 %" in out and "climbs 772 m" in out


def test_rule_line_when_clamped_to_todays_charge():
    u = UsualCharge(level=89, sessions=6, at_level=0, assumed=False, clamped=True)
    out = components.rule_line(89, u, full=False)
    assert "at least today&#x27;s 89 %" in out and "stopped at" not in out


def test_battery_card_labels_the_period():
    out = components.battery_card(80, 1200, 17.7, 30000, "Last 30 days")
    assert "Last 30 days" in out and "This year" not in out


def test_drive_list_without_zones_does_not_print_none():
    df = pd.DataFrame(
        [
            dict(
                day_label="Today",
                time="07:42",
                start_zone=None,
                end_zone=None,
                distance_km=31.4,
                kwh_per_100km=18.9,
                temp_c=4,
            )
        ]
    )
    out = components.drive_list(df)
    assert "None" not in out and "Drive" in out
