from __future__ import annotations

import argparse
from pathlib import Path

from monitor.config import OUTPUT_DIR, load_config
from monitor.pipeline import run_monitor, save_state
from monitor.reporting import build_full_summary, write_outputs
from monitor.utils import configure_logging, ensure_dir, utc_now_iso


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full refurbished MacBook Pro sweep")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    configure_logging(args.verbose)
    config = load_config(args.config) if args.config else load_config()
    ensure_dir(OUTPUT_DIR)
    listings = run_monitor(config, mode="full")
    ts = utc_now_iso().replace(":", "-")
    base_path = OUTPUT_DIR / f"full_sweep_{ts}"
    summary = build_full_summary(listings, ts)
    outputs = write_outputs(base_path, listings, summary)
    save_state(OUTPUT_DIR / "latest_state.json", listings)
    print("Wrote outputs:")
    for key, value in outputs.items():
        print(f"- {key}: {value}")
    print(f"- listings: {len(listings)}")


if __name__ == "__main__":
    main()
