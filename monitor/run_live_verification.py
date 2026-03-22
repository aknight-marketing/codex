from __future__ import annotations

import argparse
from pathlib import Path

from monitor.config import OUTPUT_DIR, load_config
from monitor.pipeline import run_monitor
from monitor.reporting import build_live_verification_summary, publish_docs, write_run_outputs
from monitor.utils import configure_logging, ensure_dir, utc_now_iso

CORE_VENDORS = {
    "apple_refurb_uk",
    "macfinder",
    "hoxton_macs",
    "back_market_uk",
    "cex",
    "musicmagpie",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run live production verification probe")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    configure_logging(args.verbose)
    config = load_config(args.config) if args.config else load_config()
    ensure_dir(OUTPUT_DIR)
    result = run_monitor(config, mode="full", test_mode=False, vendor_filter=CORE_VENDORS)
    ts = utc_now_iso().replace(":", "-")
    base_path = OUTPUT_DIR / f"live_verification_{ts}"
    public_site_url = config.get("defaults", {}).get("pages_site_url", "https://aknight-marketing.github.io/codex/")
    summary = build_live_verification_summary(result, public_site_url)
    outputs = write_run_outputs(base_path, result, summary)
    docs_dir = Path(config.get("defaults", {}).get("docs_dir", "docs"))
    docs = publish_docs(
        docs_dir,
        result,
        summary,
        "live_verification",
        "live-verification",
        public_site_url,
        update_root_index=False,
    )
    print("Wrote outputs:")
    for key, value in {**outputs, **docs}.items():
        print(f"- {key}: {value}")
    print(f"- production_readiness: {result.production_readiness}")
    print(f"- degraded: {result.degraded}")
    print(f"- trust_label: {result.trust_label}")


if __name__ == "__main__":
    main()
