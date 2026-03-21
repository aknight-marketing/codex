from __future__ import annotations

import argparse
from pathlib import Path

from monitor.config import OUTPUT_DIR, load_config
from monitor.emailer import maybe_send_email
from monitor.pipeline import run_monitor, save_state
from monitor.reporting import build_full_summary, publish_docs, write_run_outputs
from monitor.utils import configure_logging, ensure_dir, utc_now_iso


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full refurbished MacBook Pro sweep")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--test-mode", action="store_true", help="Use explicit local fixtures for smoke testing")
    args = parser.parse_args()

    configure_logging(args.verbose)
    config = load_config(args.config) if args.config else load_config()
    ensure_dir(OUTPUT_DIR)
    result = run_monitor(config, mode="full", test_mode=args.test_mode)
    ts = utc_now_iso().replace(":", "-")
    base_path = OUTPUT_DIR / f"full_sweep_{ts}"
    summary = build_full_summary(result)
    outputs = write_run_outputs(base_path, result, summary)
    docs = publish_docs(Path(config.get("defaults", {}).get("docs_dir", "docs")), result, summary, "full_sweep", "Refurb-monitor-26")
    save_state(OUTPUT_DIR / "latest_state.json", result.shortlist)
    try:
        maybe_send_email(
            subject=f"MacBook monitor full sweep: {'BUY NOW' if result.shortlist and result.shortlist[0].buy_now else 'WAIT'}",
            body=f"Generated: {result.generated_at}\nTop result: {(result.shortlist[0].title + ' ' + str(result.shortlist[0].price_gbp)) if result.shortlist else 'No shortlist results'}\nReport: index.html",
        )
    except Exception as exc:
        print(f"Email notification failed: {exc}")
    print("Wrote outputs:")
    for key, value in {**outputs, **docs}.items():
        print(f"- {key}: {value}")
    print(f"- shortlist: {len(result.shortlist)}")
    print(f"- needs_review: {len(result.needs_review)}")


if __name__ == "__main__":
    main()
