from __future__ import annotations

import json
import logging
from pathlib import Path

from monitor.browser import BrowserConfig, BrowserSession
from monitor.discovery import discover_vendor_candidates
from monitor.extractors.generic import extract_listing_from_html
from monitor.models import Listing
from monitor.scoring import score_listing
from monitor.utils import utc_now_iso

logger = logging.getLogger(__name__)


def _load_offline_snapshots(config: dict, generated_at: str, vendor_filter: set[str] | None = None) -> list[Listing]:
    snapshot_path = config.get("offline_snapshot_path")
    if not snapshot_path:
        return []
    path = Path(snapshot_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    vendors = {vendor["key"]: vendor for vendor in config["vendors"]}
    results: list[Listing] = []
    for item in payload:
        vendor = vendors.get(item["vendor_key"])
        if not vendor or (vendor_filter and vendor["key"] not in vendor_filter):
            continue
        listing = extract_listing_from_html(vendor, item["url"], item["html"], item.get("source_url", item["url"]), generated_at)
        if listing:
            listing.notes = vendor.get("notes")
            score_listing(listing, vendor_quality=float(vendor.get("trust_score", 10)))
            results.append(listing)
    if results:
        logger.warning("Using offline snapshot fallback because live network fetches are unavailable in this environment.")
    return results


def run_monitor(config: dict, mode: str = "full", vendor_filter: set[str] | None = None) -> list[Listing]:
    generated_at = utc_now_iso()
    results: list[Listing] = []
    browser_config = BrowserConfig(headless=True, timeout_ms=config.get("defaults", {}).get("timeout_ms", 30000))
    with BrowserSession(browser_config) as browser:
        for vendor in config["vendors"]:
            if vendor_filter and vendor["key"] not in vendor_filter:
                continue
            logger.info("Checking vendor: %s", vendor["name"])
            candidates = discover_vendor_candidates(vendor)
            limit = vendor.get("stock_monitor_max_candidates", 4) if mode == "stock" else vendor.get("full_sweep_max_candidates", 8)
            for candidate in candidates[:limit]:
                try:
                    html = browser.get_html(candidate.url)
                    listing = extract_listing_from_html(vendor, candidate.url, html, candidate.source_url, generated_at)
                    if not listing:
                        continue
                    listing.notes = vendor.get("notes")
                    score_listing(listing, vendor_quality=float(vendor.get("trust_score", 10)))
                    if listing.url:
                        results.append(listing)
                        logger.info("Live listing: %s | %s | %s", listing.vendor, listing.title, listing.price_gbp)
                except Exception as exc:
                    logger.warning("Vendor %s candidate %s failed: %s", vendor["name"], candidate.url, exc)
    if not results:
        results = _load_offline_snapshots(config, generated_at, vendor_filter)
    deduped: dict[tuple[str, int | None, int | None, str | None], Listing] = {}
    for item in sorted(results, key=lambda x: x.total_score, reverse=True):
        key = ((item.title or "").lower(), item.ram_gb, item.ssd_gb, item.chip)
        deduped.setdefault(key, item)
    return sorted(deduped.values(), key=lambda x: x.total_score, reverse=True)


def load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, listings: list[Listing]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {item.url: {"price_gbp": item.price_gbp, "stock_status": item.stock_status, "total_score": item.total_score} for item in listings if item.url}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def diff_state(previous: dict, current: list[Listing]) -> list[Listing]:
    changes = []
    for item in current:
        before = previous.get(item.url or "")
        if before is None or before.get("stock_status") != item.stock_status or before.get("price_gbp") != item.price_gbp:
            changes.append(item)
    return changes
