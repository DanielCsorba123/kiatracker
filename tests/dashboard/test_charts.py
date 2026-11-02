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
    assert charts.BLUE in str(chart.to_dict())


def test_line_has_points_and_tooltip():
    enc = encodings(charts.line(DF, "week:T", "cons:Q", "Consumption", "kWh/100 km"))
    assert "tooltip" in enc


def test_scatter_tooltip_lists_fields():
    chart = charts.scatter(
        DF, "temp:Q", "cons:Q", "Consumption vs temperature", "°C", "kWh/100 km", tooltip=["temp:Q", "cons:Q"]
    )
    assert len(encodings(chart)["tooltip"]) == 2


def test_histogram_bins_by_step():
    spec = charts.histogram(DF, "km", "Plug-in charge", step=10).to_dict()
    assert '"step": 10' in str(spec).replace("'", '"')


def test_weekly_bars_use_the_exact_monday_not_vega_sunday_weeks():
    spec = str(charts.bar(DF, "week:T", "km:Q", "Distance per week", "km").to_dict())
    assert "yearweek" not in spec and "yearmonthdate" in spec


def test_drive_time_tooltip_is_not_called_week():
    df = DF.assign(start_local=DF["week"])
    chart = charts.scatter(df, "temp:Q", "cons:Q", "t", "x", "y", tooltip=["start_local:T"])
    tip = encodings(chart)["tooltip"][0]
    assert tip["title"] == "Start" and "%H:%M" in tip["format"]


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
