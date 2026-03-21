from __future__ import annotations

import json
import logging
from pathlib import Path

from monitor.browser import BrowserConfig, BrowserSession
from monitor.discovery import discover_vendor_candidates
from monitor.extractors import extract_listing
from monitor.models import Listing, MonitorResult
from monitor.scoring import score_listing
from monitor.utils import utc_now_iso

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ["price_gbp", "chip", "ram_gb", "ssd_gb", "screen_size_in"]


def _validate_listing(listing: Listing) -> Listing:
    missing = [field for field in REQUIRED_FIELDS if getattr(listing, field) in (None, "")]
    if listing.screen_size_in and not (13.8 <= listing.screen_size_in <= 14.3):
        missing.append("screen_size_in_not_14")
    if listing.stock_status != "in_stock":
        missing.append("stock_status")
    if missing:
        listing.review_reason = ", ".join(missing)
    return listing


def _dedupe(listings: list[Listing]) -> list[Listing]:
    deduped: dict[tuple[str, str | None, int | None, int | None, str | None], Listing] = {}
    for item in sorted(listings, key=lambda x: x.total_score, reverse=True):
        key = (item.vendor_key, (item.title or "").lower(), item.ram_gb, item.ssd_gb, item.chip)
        deduped.setdefault(key, item)
    return list(deduped.values())


def run_monitor(config: dict, mode: str = "full", test_mode: bool = False, vendor_filter: set[str] | None = None) -> MonitorResult:
    generated_at = utc_now_iso()
    shortlist: list[Listing] = []
    needs_review: list[Listing] = []
    vendor_errors: list[dict[str, str]] = []
    fixture_path = config.get("test_mode", {}).get("fixture_path") if test_mode else None
    browser_config = BrowserConfig(headless=True, timeout_ms=config.get("defaults", {}).get("timeout_ms", 30000), fixture_path=fixture_path)
    with BrowserSession(browser_config) as browser:
        for vendor in config["vendors"]:
            if vendor_filter and vendor["key"] not in vendor_filter:
                continue
            logger.info("Checking vendor: %s", vendor["name"])
            candidates = discover_vendor_candidates(vendor, browser, mode=mode)
            limit = vendor.get("stock_monitor_max_candidates", 6) if mode == "stock" else vendor.get("full_sweep_max_candidates", 12)
            if not candidates:
                vendor_errors.append({"vendor": vendor["name"], "error": "No discovery candidates found"})
            for candidate in candidates[:limit]:
                try:
                    html = browser.get_html(candidate.url)
                    listing = extract_listing(vendor, candidate.url, html, candidate.source_url, generated_at)
                    if not listing:
                        continue
                    listing.notes = vendor.get("notes")
                    score_listing(listing, vendor_quality=float(vendor.get("trust_score", 10)))
                    listing = _validate_listing(listing)
                    if listing.review_reason:
                        needs_review.append(listing)
                    else:
                        shortlist.append(listing)
                except Exception as exc:
                    vendor_errors.append({"vendor": vendor["name"], "url": candidate.url, "error": str(exc)})
                    logger.warning("Vendor %s candidate %s failed: %s", vendor["name"], candidate.url, exc)
    shortlist = sorted(_dedupe(shortlist), key=lambda x: x.total_score, reverse=True)
    needs_review = sorted(_dedupe(needs_review), key=lambda x: x.vendor)
    return MonitorResult(generated_at=generated_at, mode=mode, shortlist=shortlist, needs_review=needs_review, vendor_errors=vendor_errors, used_test_mode=test_mode)


def load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, listings: list[Listing]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {item.url: {"price_gbp": item.price_gbp, "stock_status": item.stock_status, "total_score": item.total_score} for item in listings if item.url}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def diff_state(previous: dict, current: list[Listing]) -> list[Listing]:
    return [item for item in current if previous.get(item.url or "") != {"price_gbp": item.price_gbp, "stock_status": item.stock_status, "total_score": item.total_score}]
