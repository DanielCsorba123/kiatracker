"""README screenshots of the demo dashboard, in the light Morning theme, with the system's Edge via Playwright.

Start the demo first, then capture:

    KIATRACKER_DEMO=1 uv run streamlit run src/kiatracker/dashboard/app.py --server.port 8503
    uv run --group screenshots python scripts/capture_screenshots.py docs/images

`--mobile` captures at phone width into the given folder instead and fails if any page scrolls sideways.
Screenshots come from demo mode only: never point this at a dashboard with personal data.
"""

import argparse
from pathlib import Path

from PIL import Image
from playwright.sync_api import Page, sync_playwright

BASE = "http://localhost:8503"
PAGES = ["overview", "drives", "charging", "costs", "range", "routes"]


def settle(page: Page, extra_ms: int) -> None:
    page.wait_for_selector("[data-testid='stMain']", timeout=180_000)
    page.wait_for_function(
        "() => !document.querySelector('[data-testid=\"stStatusWidget\"]')", timeout=180_000
    )
    page.wait_for_timeout(extra_ms)


def trim(path: Path, margin: int = 30) -> None:
    """Streamlit scrolls inside its own container, so the viewport is tall; cut the empty paper below."""
    image = Image.open(path)
    box = image.convert("L").point(lambda v: 0 if v > 240 else 255).getbbox()
    if box:
        image.crop((0, 0, image.width, min(image.height, box[3] + margin))).save(path)


def capture(out: Path, mobile: bool) -> None:
    width, height = (390, 4200) if mobile else (1400, 2800)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge")
        context = browser.new_context(viewport={"width": width, "height": height}, color_scheme="light")
        page = context.new_page()
        page.goto(BASE, wait_until="networkidle")
        settle(page, 8000)  # the first load generates the demo year
        for name in PAGES:
            page.goto(f"{BASE}/{name}" if name != "overview" else BASE, wait_until="networkidle")
            settle(page, 3000)
            if name == "routes":
                page.get_by_text("Compare", exact=True).click()
                page.wait_for_timeout(2000)
                settle(page, 2000)
                page.frame_locator("iframe").first.locator("canvas").wait_for(timeout=60_000)
                page.wait_for_timeout(6000)  # let the map tiles arrive
            if mobile:
                wide = page.evaluate("document.querySelector('[data-testid=\"stMain\"]').scrollWidth")
                assert wide <= width, f"{name} scrolls sideways at {width} px ({wide} px wide)"
            path = out / f"{name}.png"
            page.screenshot(path=str(path))
            trim(path)
            print("captured", path)
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    parser.add_argument("--mobile", action="store_true")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    capture(args.out, args.mobile)
