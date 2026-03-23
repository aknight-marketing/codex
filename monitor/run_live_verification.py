from __future__ import annotations

import argparse
import inspect
from pathlib import Path

from monitor.config import OUTPUT_DIR, load_config
from monitor.pipeline import run_monitor
from monitor import reporting
from monitor.utils import configure_logging, ensure_dir, utc_now_iso

CORE_VENDORS = {
    "apple_refurb_uk",
    "macfinder",
    "hoxton_macs",
    "back_market_uk",
    "cex",
    "musicmagpie",
}


def _fallback_live_verification_summary(result, public_site_url: str) -> str:
    lines = [
        "# Live production verification\n",
        f"Generated: {result.generated_at}\n",
        f"Production readiness: **{result.production_readiness}**\n",
        f"Trust label: **{result.trust_label}**\n",
        f"Degraded: **{'yes' if result.degraded else 'no'}**\n",
        f"\nPublic site base: {public_site_url}\n",
    ]
    if getattr(result, "readiness_reasons", None):
        lines.append("\n## Readiness reasons\n")
        for reason in result.readiness_reasons:
            lines.append(f"- {reason}")
    if getattr(result, "vendor_status", None):
        lines.append("\n## Core vendor health\n")
        for status in result.vendor_status:
            lines.append(
                f"- **{status['vendor']}**: {status['status']} "
                f"(candidates={status['candidates_found']}, observed={status['observed_listings']}, "
                f"actionable={status['actionable']}, review={status['needs_review']}, "
                f"unavailable={status['unavailable']}, errors={status['errors']})"
            )
    if getattr(result, "vendor_errors", None):
        lines.append("\n## Vendor errors\n")
        for issue in result.vendor_errors:
            lines.append(f"- **{issue.get('vendor')}**: {issue.get('error')} {issue.get('url', '')}")
    return "\n".join(lines) + "\n"


def _build_live_verification_summary(result, public_site_url: str) -> str:
    builder = getattr(reporting, "build_live_verification_summary", None)
    if callable(builder):
        return builder(result, public_site_url)
    return _fallback_live_verification_summary(result, public_site_url)


def _publish_live_verification_docs(docs_dir: Path, result, summary: str, public_site_url: str):
    publish_docs = reporting.publish_docs
    parameters = inspect.signature(publish_docs).parameters
    if "section_slug" in parameters:
        return publish_docs(
            docs_dir,
            result,
            summary,
            "live_verification",
            "live-verification",
            public_site_url,
            update_root_index=True,
        )
    if "site_slug" in parameters:
        return publish_docs(
            docs_dir,
            result,
            summary,
            "live_verification",
            "live-verification",
            public_site_url,
        )
    return publish_docs(docs_dir, result, summary, "live_verification")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run live production verification probe")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--test-mode", action="store_true", help="Use explicit fixtures for local verification smoke testing")
    args = parser.parse_args()

    configure_logging(args.verbose)
    config = load_config(args.config) if args.config else load_config()
    ensure_dir(OUTPUT_DIR)
    result = run_monitor(config, mode="full", test_mode=args.test_mode, vendor_filter=CORE_VENDORS)
    ts = utc_now_iso().replace(":", "-")
    base_path = OUTPUT_DIR / f"live_verification_{ts}"
    public_site_url = config.get("defaults", {}).get("pages_site_url", "https://aknight-marketing.github.io/codex/")
    summary = _build_live_verification_summary(result, public_site_url)
    outputs = reporting.write_run_outputs(base_path, result, summary)
    docs_dir = Path(config.get("defaults", {}).get("docs_dir", "docs"))
    docs = _publish_live_verification_docs(docs_dir, result, summary, public_site_url)
    print("Wrote outputs:")
    for key, value in {**outputs, **docs}.items():
        print(f"- {key}: {value}")
    print(f"- production_readiness: {result.production_readiness}")
    print(f"- degraded: {result.degraded}")
    print(f"- trust_label: {result.trust_label}")


if __name__ == "__main__":
    main()
