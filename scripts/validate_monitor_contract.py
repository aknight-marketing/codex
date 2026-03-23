#!/usr/bin/env python3
from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def require_import(module_name: str) -> None:
    importlib.import_module(module_name)
    print(f"import ok: {module_name}")


def require_reporting_contract() -> None:
    reporting = importlib.import_module("monitor.reporting")
    required_symbols = [
        "build_full_summary",
        "build_stock_monitor_summary",
        "build_live_verification_summary",
        "publish_docs",
        "write_run_outputs",
    ]
    missing = [name for name in required_symbols if not hasattr(reporting, name)]
    if missing:
        raise RuntimeError(f"monitor.reporting missing required symbols: {', '.join(missing)}")
    print("reporting contract ok")


def run_smoke(module_name: str, *args: str) -> None:
    cmd = [sys.executable, "-m", module_name, *args]
    print("running:", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=REPO_ROOT)


def main() -> None:
    for module_name in [
        "monitor.reporting",
        "monitor.run_full",
        "monitor.run_stock_monitor",
        "monitor.run_live_verification",
    ]:
        require_import(module_name)

    require_reporting_contract()

    run_smoke("monitor.run_full", "--test-mode")
    run_smoke("monitor.run_stock_monitor", "--test-mode")
    run_smoke("monitor.run_live_verification", "--test-mode")


if __name__ == "__main__":
    main()
