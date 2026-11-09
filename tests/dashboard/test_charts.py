import pandas as pd

from kiatracker.dashboard import charts

DF = pd.DataFrame(
    {
        "week": pd.to_datetime(["2026-10-05", "2026-10-12"]),
        "km": [120.0, 80.0],
        "temp": [3.0, 9.0],
        "cons": [18, 15],
    }
)


def encodings(chart) -> dict:
    spec = chart.to_dict()
    layers = spec.get("layer", [spec])
    return {k: v for layer in layers for k, v in layer.get("encoding", {}).items()}


def test_bar_has_tooltip_one_axis_and_brand_color():
    chart = charts.bar(DF, "week:T", "km:Q", "Distance per week", "km")
    enc = encodings(chart)
    assert "tooltip" in enc and "y" in enc and "y2" not in enc
    assert charts.SKY in str(chart.to_dict())


def test_histogram_bins_by_step():
    spec = charts.histogram(DF, "km", "Plug-in charge", step=10).to_dict()
    assert '"step": 10' in str(spec).replace("'", '"')


def test_weekly_bars_use_the_exact_monday_not_vega_sunday_weeks():
    spec = str(charts.bar(DF, "week:T", "km:Q", "Distance per week", "km").to_dict())
    assert "yearweek" not in spec and "yearmonthdate" in spec


def test_band_bars_keep_data_order_not_alphabetical():
    bands = pd.DataFrame({"band": ["-30 to 0", "5 to 10", "10 to 15"], "v": [20.0, 17.0, 15.0]})
    x = encodings(charts.bar(bands, "band:O", "v:Q", "t", "y"))["x"]
    assert x["sort"] is None


def test_histogram_axis_shows_whole_percent():
    x = encodings(charts.histogram(DF, "km", "t", step=10))["x"]
    assert x["axis"]["format"] == "d"


def test_histogram_can_fix_its_range():
    x = encodings(charts.histogram(DF, "km", "t", step=10, extent=(0, 100)))["x"]
    assert x["bin"]["extent"] == [0, 100] and x["scale"]["domain"] == [0, 100]


def test_predicted_vs_actual_has_equal_axes_and_a_diagonal():
    df = pd.DataFrame({"predicted": [12.0, 18.0, 22.5], "actual": [10.0, 19.0, 21.0]})
    spec = charts.predicted_vs_actual(df, "kWh/100 km").to_dict()
    points, diagonal = spec["layer"]
    x, y = points["encoding"]["x"], points["encoding"]["y"]
    assert x["scale"]["domain"] == y["scale"]["domain"] == [10.0, 22.5]
    assert diagonal["mark"]["type"] == "line" and diagonal["mark"]["strokeDash"]


DRIVES = pd.DataFrame(
    {
        "temp_c": [-2.0, 4.0, 12.0],
        "wind_kph": [5.0, 20.0, 35.0],
        "distance_km": [6.0, 20.0, 60.0],
        "kwh_per_100km": [21.0, 17.0, 15.0],
        "start_local": pd.to_datetime(["2026-11-01"] * 3),
    }
)
BANDS = pd.DataFrame(
    {
        "band": ["under 0", "0+"],
        "lo": [-30, 0],
        "hi": [0, 45],
        "kwh_per_100km": [21.0, 16.0],
        "drives": [1, 2],
    }
)


def test_points_with_band_averages_shows_every_drive_and_each_band_line():
    spec = charts.points_with_bands(DRIVES, "temp_c", BANDS, "Consumption vs temperature", "°C").to_dict()
    points, averages = spec["layer"]
    assert points["mark"]["type"] == "circle" and "tooltip" in points["encoding"]
    assert averages["mark"]["type"] == "rule"
    assert averages["encoding"]["x"]["field"] == "x_lo" and averages["encoding"]["x2"]["field"] == "x_hi"
    # catch-all outer edges are clipped to the data, so the line doesn't stretch the axis to -30 °C
    clipped = spec["layer"][1]["data"]["values"] if "values" in spec["layer"][1].get("data", {}) else None
    assert clipped is None or min(row["x_lo"] for row in clipped) >= -2.0


def all_charts():
    bands = BANDS
    yield charts.bar(DF, "week:T", "km:Q", "t", "km")
    yield charts.histogram(DF, "km", "t", step=10)
    yield charts.points_with_bands(DRIVES, "temp_c", bands, "t", "°C")
    yield charts.predicted_vs_actual(pd.DataFrame({"predicted": [1.0, 2.0], "actual": [1.5, 2.5]}), "kWh")


def test_every_chart_wears_the_house_style():
    for chart in all_charts():
        config = chart.to_dict()["config"]
        assert config["font"] == "Hanken Grotesk"
        assert config["title"]["font"] == "Young Serif"
        assert config["view"]["stroke"] is None
        assert config["axis"]["domain"] is False and config["axis"]["gridColor"] == charts.theme.RULE


def test_house_uses_tokens_and_no_title():
    spec = charts.bar(DF, "week:T", "km:Q", None, "km").to_dict()
    assert spec["config"]["background"] == "transparent"  # the white card shows through
    assert spec["config"]["font"] == "Hanken Grotesk" and "title" not in spec
    assert spec["config"]["axis"]["gridColor"] == charts.theme.RULE


def test_monthly_use_highlights_months_10pct_above_mean():
    df = pd.DataFrame({"month": ["2026-01", "2026-06", "2026-07"], "kwh_per_100km": [21.4, 14.9, 15.2]})
    spec = str(charts.monthly_use(df).to_dict())
    assert charts.CORAL in spec and charts.PALE in spec
    assert "timeFormat" in spec  # month names on the axis


def test_weekly_distance_highlights_the_last_week():
    spec = charts.weekly_distance(DF.rename(columns={"km": "distance_km"})).to_dict()
    assert charts.CORAL in str(spec) and "tooltip" in str(spec)


def test_drives_over_year_colours_costly_drives():
    df = pd.DataFrame(
        {
            "start_local": pd.to_datetime(["2026-01-05", "2026-06-05", "2026-07-05"]),
            "kwh_per_100km": [21.0, 15.0, 15.5],
        }
    )
    spec = str(charts.drives_over_year(df).to_dict())
    assert charts.CORAL in spec and charts.SKY in spec and "loess" in spec


def test_plug_hours_chart_marks_the_peak_in_sun():
    df = pd.DataFrame({"hour": range(24), "sessions": [0] * 17 + [5, 9, 8, 6] + [0] * 3})
    spec = str(charts.plug_hours(df).to_dict())
    assert charts.theme.SUN in spec and charts.PALE in spec


def test_bar_can_highlight_the_last_bar():
    spec = str(charts.bar(DF, "week:T", "km:Q", None, "km", highlight_last=True).to_dict())
    assert charts.CORAL in spec and charts.PALE in spec


def test_histogram_takes_a_colour():
    df = pd.DataFrame({"soc": [10, 20, 80]})
    assert charts.CORAL in str(
        charts.histogram(df, "soc", None, 10, "Battery %", (0, 100), colour=charts.CORAL).to_dict()
    )


def test_savings_bars_highlight_the_last_complete_bucket():
    df = pd.DataFrame(
        {
            "bucket": ["2026-09", "2026-10", "2026-11"],
            "saved_huf": [55000.0, 60000.0, 20000.0],
            "complete": [True, True, False],
        }
    )
    spec = charts.savings_bars(df).to_dict()
    text = str(spec)
    assert charts.CORAL in text and charts.PALE in text and "60k" in text


PROFILE = pd.DataFrame(
    {
        "route": ["Fastest"] * 3 + ["Through Vienna"] * 3 + ["Via Vösendorf"] * 3,
        "km": [0, 60, 122, 0, 70, 140, 0, 70, 147],
        "height": [0, 372, 80, 0, 130, 60, 0, 380, 70],
    }
)


def test_route_heights_label_the_highest_points():
    spec = str(charts.route_heights(PROFILE).to_dict())
    assert "+372 m · highest point, km 60" in spec and "Through Vienna: never above +130 m" in spec
    assert charts.CORAL in spec and charts.SKY in spec


def test_route_difference_net_and_signs():
    parts = pd.DataFrame(
        {
            "route": ["A", "A", "B", "B"],
            "cause": ["base", "climb", "base", "climb"],
            "kwh": [20.0, 4.0, 22.9, 1.6],
        }
    )
    spec = str(charts.route_difference(parts, "A", "B").to_dict())
    assert "Net: A uses 0.5 kWh less" in spec and charts.CORAL in spec and charts.SKY in spec


def test_route_colours_put_the_chosen_route_in_coral():
    assert charts.ROUTE_COLOURS[:3] == [charts.CORAL, charts.SKY, charts.PALE]
