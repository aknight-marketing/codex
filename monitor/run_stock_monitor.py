from __future__ import annotations

import argparse
from pathlib import Path

from monitor.config import OUTPUT_DIR, load_config
from monitor.emailer import maybe_send_email
from monitor.pipeline import diff_state, load_state, run_monitor, save_state
from monitor.reporting import build_stock_monitor_summary, publish_docs, write_run_outputs
from monitor.utils import configure_logging, ensure_dir, utc_now_iso


def main() -> None:
    parser = argparse.ArgumentParser(description="Run stock monitor")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--test-mode", action="store_true", help="Use explicit local fixtures for smoke testing")
    args = parser.parse_args()

    configure_logging(args.verbose)
    config = load_config(args.config) if args.config else load_config()
    ensure_dir(OUTPUT_DIR)
    result = run_monitor(config, mode="stock", test_mode=args.test_mode, vendor_filter=set(config.get("watchlist_vendors", [])) or None)
    previous = load_state(OUTPUT_DIR / "stock_monitor_state.json")
    changes = diff_state(previous, result.shortlist, result.generated_at)
    ts = utc_now_iso().replace(":", "-")
    base_path = OUTPUT_DIR / f"stock_monitor_{ts}"
    summary = build_stock_monitor_summary(result, changes)
    outputs = write_run_outputs(base_path, result, summary)
    docs = publish_docs(Path(config.get("defaults", {}).get("docs_dir", "docs")), result, summary, "stock_monitor", "stock-monitor", config.get("defaults", {}).get("pages_site_url", "https://aknight-marketing.github.io/codex/"))
    save_state(OUTPUT_DIR / "stock_monitor_state.json", result.shortlist)
    if changes:
        try:
            maybe_send_email(subject="MacBook monitor stock update", body=(f"Generated: {result.generated_at}\n"
                f"Trust label: {result.trust_label}\n"
                f"Changes: {len(changes)}\n"
                f"Degraded: {result.degraded}\n"
                "Report: stock-monitor/index.html"))
        except Exception as exc:
            print(f"Email notification failed: {exc}")
    print("Wrote outputs:")
    for key, value in {**outputs, **docs}.items():
        print(f"- {key}: {value}")
    print(f"- shortlist: {len(result.shortlist)}")
    print(f"- needs_review: {len(result.needs_review)}")
    print(f"- changes: {len(changes)}")
    print(f"- degraded: {result.degraded}")
    print(f"- trust_label: {result.trust_label}")


if __name__ == "__main__":
    main()
