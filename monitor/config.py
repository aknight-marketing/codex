from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "vendors.json"
OUTPUT_DIR = BASE_DIR / "output"
STATE_PATH = BASE_DIR / "state.json"
STOCK_STATE_PATH = OUTPUT_DIR / "stock_state.json"
FULL_SWEEP_STATE_PATH = OUTPUT_DIR / "full_sweep_state.json"


def load_config(path: Path = CONFIG_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
