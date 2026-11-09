from datetime import date

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
