"""Streamlit entry point. Start it with `kiatracker dashboard` (your data, this computer only) or
`kiatracker dashboard --demo`. Started any other way, e.g. `streamlit run`, it shows demo data only.
"""

from datetime import date

import streamlit as st

from kiatracker.config import load_settings
from kiatracker.dashboard.queries import connect
from kiatracker.dashboard.source import build_demo_database, may_show_personal, resolve_source
from kiatracker.dashboard.ui import BRAND, LOGO, demo_strip, inject_style, period_control
from kiatracker.dashboard.views import charging, costs, drives, overview, routes
from kiatracker.dashboard.views import range as range_page
from kiatracker.showcase import load_status

PAGES = [
    (overview, "Overview", ":material/dashboard:"),
    (drives, "Drives", ":material/directions_car:"),
    (charging, "Charging", ":material/ev_station:"),
    (costs, "Costs", ":material/savings:"),
    (range_page, "Range", ":material/battery_charging_full:"),
    (routes, "Routes", ":material/route:"),
]


@st.cache_resource(show_spinner="Generating demo data…")
def demo_database():
    return build_demo_database()


def demo_banner(status: dict | None) -> str:
    """Simulated data, said plainly, with where the real collection stands."""
    text = (
        "**Simulated data.** A year of driving, charging, weather and hills from the project's simulator, "
        "calibrated to the EV3's measured real-world consumption. Routes are real, priced with the demo "
        "model."
    )
    if not status or not status.get("collecting_since"):
        return text
    since = date.fromisoformat(status["collecting_since"])
    expected = status.get("expected_real_data")
    when = f"{date.fromisoformat(expected + '-01'):%B %Y}" if expected else "later"
    updated = date.fromisoformat(status["updated"])
    return (
        f"{text}\n\n**The real tracker** has been collecting since {since.day} {since:%B %Y}"
        f": {status['trustworthy_drives']} trustworthy drives and {status['km']:,} km so far. This site "
        f"switches to real, anonymised data after {status['target_drives']} drives including "
        f"{status['target_cold_drives']} cold ones, expected around **{when}** "
        f"(as of {updated.day} {updated:%b})."
    )


def page_runner(module, db_path, period):
    def run():
        with connect(db_path) as con:
            module.render(con, period)

    return run


def main() -> None:
    st.set_page_config(page_title=f"{BRAND} · EV3", page_icon=str(LOGO), layout="wide")
    inject_style()
    source = resolve_source(load_settings().db_path)
    if source.demo:
        db_path = demo_database()
        demo_strip(demo_banner(load_status()))
    elif not may_show_personal(st.get_option("server.address")):
        st.error("Personal data is only shown when the dashboard listens on this computer alone (127.0.0.1).")
        st.stop()
    elif source.db_path.exists():
        db_path = source.db_path
    else:
        st.warning(
            "No database yet. Run `kiatracker build` first, or start with `kiatracker dashboard --demo`."
        )
        st.stop()

    st.logo(str(LOGO), size="large")
    period = period_control(365 if source.demo else 30)  # the demo has a whole year to show

    pages = [
        st.Page(
            page_runner(module, db_path, period),
            title=title,
            url_path=module.__name__.split(".")[-1],
        )
        for module, title, _icon in PAGES
    ]
    st.navigation(pages, position="top").run()


main()
