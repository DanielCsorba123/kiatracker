"""Entry point for the public demo on Streamlit Community Cloud: generated data only, never personal data.

Community Cloud runs this file directly without installing the package, so `src/` goes on the import path,
and installs the packages in the requirements.txt next to it. It sits beside `static/` so the fonts and logo
are served. KIATRACKER_DEMO forces the simulator's data whatever else is configured.
"""

import os
import runpy
import sys
from pathlib import Path

os.environ["KIATRACKER_DEMO"] = "1"
SRC = str(Path(__file__).resolve().parents[2])
if SRC not in sys.path:
    sys.path.insert(0, SRC)

runpy.run_module("kiatracker.dashboard.app", run_name="__main__")
