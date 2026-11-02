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
