from kiatracker.dashboard import queries
from kiatracker.dashboard.views.costs import current_assumptions


def test_assumptions_come_from_the_widgets_state():
    state = {
        "cost-petrol": 7.5,
        "cost-diesel": 6.0,
        "cost-loss": 15,
        "cost-band": "Within average consumption",
    }
    a = current_assumptions(state)
    assert (a.petrol_l_per_100km, a.diesel_l_per_100km, a.charging_loss_pct) == (7.5, 6.0, 15.0)
    assert a.hu_electricity_huf != queries.CostAssumptions().hu_electricity_huf


def test_assumptions_default_before_any_widget_exists():
    assert current_assumptions({}) == queries.CostAssumptions()
