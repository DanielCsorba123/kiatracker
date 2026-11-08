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


def test_bar_with_interval_layers_whiskers_and_tooltip():
    df = pd.DataFrame(
        {"day": ["Mon", "Tue"], "km": [300.0, 280.0], "lo": [270.0, 250.0], "hi": [330.0, 310.0]}
    )
    spec = charts.bar_with_interval(df, "day:O", "km", "lo", "hi", "Range by day", "km").to_dict()
    assert len(spec["layer"]) == 2
    assert spec["layer"][1]["mark"]["type"] == "rule"
    assert "tooltip" in spec["layer"][0]["encoding"]


def test_predicted_vs_actual_has_equal_axes_and_a_diagonal():
    df = pd.DataFrame({"predicted": [12.0, 18.0, 22.5], "actual": [10.0, 19.0, 21.0]})
    spec = charts.predicted_vs_actual(df, "kWh/100 km").to_dict()
    points, diagonal = spec["layer"]
    x, y = points["encoding"]["x"], points["encoding"]["y"]
    assert x["scale"]["domain"] == y["scale"]["domain"] == [10.0, 22.5]
    assert diagonal["mark"]["type"] == "line" and diagonal["mark"]["strokeDash"]


def test_grouped_bars_keep_series_colours_fixed_and_show_a_legend():
    df = pd.DataFrame(
        {
            "month": ["2026-10", "2026-10", "2026-11"],
            "series": ["EV", "Petrol car", "EV"],
            "value": [5000.0, 30000.0, 6000.0],
        }
    )
    spec = charts.grouped_bar(
        df, "month", "series", "value", "Monthly cost", "Ft", ["EV", "Petrol car", "Diesel car"]
    )
    enc = spec.to_dict()["encoding"]
    assert enc["color"]["scale"]["domain"] == ["EV", "Petrol car", "Diesel car"]
    assert enc["color"]["scale"]["range"][:3] == [charts.BLUE, charts.ORANGE, charts.AQUA]
    assert "legend" not in enc["color"] or enc["color"]["legend"] is not None
    assert "tooltip" in enc and "xOffset" in enc


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


def test_combined_chart_encodes_temperature_wind_and_length():
    enc = charts.combined_scatter(DRIVES).to_dict()["encoding"]
    assert enc["x"]["field"] == "temp_c" and enc["y"]["field"] == "kwh_per_100km"
    assert enc["color"]["field"] == "wind_kph" and enc["size"]["field"] == "distance_km"
    assert enc["color"]["legend"]["title"] and enc["size"]["legend"]["title"]


def all_charts():
    bands = BANDS
    yield charts.bar(DF, "week:T", "km:Q", "t", "km")
    yield charts.line(DF, "week:T", "cons:Q", "t", "kWh")
    yield charts.scatter(DF, "temp:Q", "cons:Q", "t", "x", "y", ["temp:Q"])
    yield charts.histogram(DF, "km", "t", step=10)
    yield charts.points_with_bands(DRIVES, "temp_c", bands, "t", "°C")
    yield charts.combined_scatter(DRIVES)
    yield charts.predicted_vs_actual(pd.DataFrame({"predicted": [1.0, 2.0], "actual": [1.5, 2.5]}), "kWh")
    yield charts.bar_with_interval(
        pd.DataFrame({"d": ["a"], "v": [1.0], "l": [0.5], "h": [1.5]}), "d:O", "v", "l", "h", "t", "km"
    )
    yield charts.grouped_bar(
        pd.DataFrame({"m": ["x"], "s": ["EV"], "v": [1.0]}), "m", "s", "v", "t", "Ft", ["EV"]
    )


def test_every_chart_wears_the_house_style():
    for chart in all_charts():
        config = chart.to_dict()["config"]
        assert config["font"] == "Inter"
        assert config["title"]["font"] == "Space Grotesk"
        assert config["view"]["stroke"] is None
        assert config["axis"]["domain"] is False and config["axis"]["gridDash"]


def test_trend_line_has_a_gradient_area_under_it():
    spec = charts.line(DF, "week:T", "cons:Q", "t", "kWh").to_dict()
    area = next(layer for layer in spec["layer"] if layer["mark"]["type"] == "area")
    assert area["mark"]["color"]["gradient"] == "linear"


EFFECTS = pd.DataFrame(
    {
        "factor": ["Cold", "Wind"],
        "harder_label": ["below 5 °C", "20 km/h+"],
        "easier_label": ["10 °C+", "under 10"],
        "harder_kwh": [18.0, 16.0],
        "easier_kwh": [15.0, 15.5],
        "diff_kwh": [3.0, 0.5],
        "pct": [0.2, 0.03],
        "n_harder": [5, 2],
        "n_easier": [6, 4],
        "enough": [True, False],
    }
)


def test_effect_bars_grey_out_factors_without_enough_drives():
    spec = charts.effect_bars(EFFECTS).to_dict()
    bars = spec["layer"][0]
    assert bars["mark"]["type"] == "bar" and "tooltip" in bars["encoding"]
    assert bars["encoding"]["color"]["condition"]["value"] == charts.ORANGE  # enough data: brand accent
    assert spec["config"]["font"] == "Inter"


def test_range_heatmap_labels_every_cell_in_km():
    grid = pd.DataFrame(
        {"temp_c": [-10, -10, 20, 20], "wind_kph": [0, 30, 0, 30], "range_km": [300, 280, 420, 400]}
    )
    spec = charts.range_heatmap(grid, "Range on a full battery at 80 km/h").to_dict()
    cells, labels = spec["layer"]
    assert cells["mark"]["type"] == "rect" and labels["mark"]["type"] == "text"
    assert cells["encoding"]["color"]["field"] == "range_km"


def test_drive_log_puts_each_drive_on_a_timeline():
    enc = charts.drive_log(DRIVES).to_dict()["encoding"]
    assert enc["x"]["field"] == "start_local" and enc["y"]["field"] == "kwh_per_100km"
    assert enc["size"]["field"] == "distance_km" and enc["color"]["field"] == "temp_c"


def test_route_breakdown_stacks_causes_with_regen_below_zero():
    parts = pd.DataFrame(
        {"route": ["A", "A", "B"], "cause": ["base", "regen", "climb"], "kwh": [7.0, -2.0, 4.0]}
    )
    spec = charts.route_breakdown(parts).to_dict()
    assert spec["encoding"]["x"]["stack"] == "zero"
    assert "Downhill regen" in spec["encoding"]["color"]["scale"]["domain"]


def test_route_profile_has_one_colour_per_route():
    profile = pd.DataFrame({"route": ["A", "A", "B", "B"], "km": [0, 1, 0, 1], "kwh": [0, 0.2, 0, 0.3]})
    spec = charts.route_profile(profile, "kwh", "Energy", "kWh").to_dict()
    assert spec["encoding"]["color"]["scale"]["domain"] == ["A", "B"]
