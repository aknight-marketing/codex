from __future__ import annotations

import json
import logging
from pathlib import Path

from monitor.browser import BrowserConfig, BrowserSession, classify_fetch_error
from monitor.discovery import discover_vendor_candidates
from monitor.extractors import extract_listing
from monitor.models import Listing, MonitorResult
from monitor.scoring import score_listing
from monitor.utils import utc_now_iso

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ["price_gbp", "chip", "ram_gb", "ssd_gb", "screen_size_in"]
CORE_VENDORS = {"apple_refurb_uk", "macfinder", "hoxton_macs", "back_market_uk", "cex", "musicmagpie"}
PLAUSIBLE_RAM_SIZES_GB = {8, 16, 18, 24, 32, 36, 48, 64, 96, 128}
PLAUSIBLE_SSD_SIZES_GB = {256, 512, 1024, 2048, 4096, 8192}


def _minimum_price_floor(listing: Listing) -> float:
    chip = (listing.chip or "").upper()
    if "MAX" in chip:
        return 1400
    if chip == "M4 PRO":
        return 1500
    if chip == "M3 PRO":
        return 950
    if chip.startswith("M"):
        return 900
    return 800


def _validate_listing(listing: Listing) -> Listing:
    problems: list[str] = []
    severity = "review"
    missing = [field for field in REQUIRED_FIELDS if getattr(listing, field) in (None, "")]
    problems.extend(missing)
    if listing.screen_size_in and not (13.8 <= listing.screen_size_in <= 14.3):
        problems.append("screen_size_in_not_14")
        severity = "reject"
    if listing.stock_status != "in_stock":
        problems.append("stock_status")
        severity = "reject"
    if listing.url and "/search" in listing.url:
        problems.append("not_actual_product_page")
        severity = "reject"
    if listing.price_gbp is not None and listing.price_gbp < _minimum_price_floor(listing):
        problems.append("price_suspiciously_low")
        severity = "reject"
    if listing.ram_gb is not None and listing.ram_gb not in PLAUSIBLE_RAM_SIZES_GB:
        problems.append("ram_gb_implausible")
        severity = "reject"
    if listing.ssd_gb is not None and listing.ssd_gb not in PLAUSIBLE_SSD_SIZES_GB:
        problems.append("ssd_gb_implausible")
        severity = "reject"
    if listing.raw.get("price_is_ambiguous"):
        problems.append("price_ambiguous")
        severity = "reject"
    if not listing.chip or not listing.ram_gb or not listing.ssd_gb:
        severity = "reject"
    if problems:
        listing.review_reason = ", ".join(problems)
        listing.review_severity = severity
    return listing


def _dedupe(listings: list[Listing]) -> list[Listing]:
    deduped: dict[tuple[str, str | None, int | None, int | None, str | None], Listing] = {}
    for item in sorted(listings, key=lambda x: x.total_score, reverse=True):
        key = (item.vendor_key, (item.title or "").lower(), item.ram_gb, item.ssd_gb, item.chip)
        deduped.setdefault(key, item)
    return list(deduped.values())


def _empty_vendor_stat(vendor: dict, mode: str) -> dict[str, object]:
    return {
        "vendor": vendor["name"],
        "vendor_key": vendor["key"],
        "mode": mode,
        "discovery_status": "not_attempted",
        "discovery_issues": [],
        "candidate_count": 0,
        "parser_success_count": 0,
        "parser_failure_count": 0,
        "actionable_count": 0,
        "excluded_count": 0,
        "live_fetch_success_count": 0,
        "live_fetch_failure_count": 0,
        "stock_validation_success_count": 0,
        "blocked": False,
        "last_error": None,
    }


def _build_run_health(result: MonitorResult) -> dict[str, object]:
    vendors_checked = len(result.vendor_stats)
    vendors_with_direct_candidates = sum(1 for stat in result.vendor_stats if stat.get("candidate_count", 0) > 0)
    vendors_successfully_parsed = sum(1 for stat in result.vendor_stats if stat.get("parser_success_count", 0) > 0)
    vendors_with_live_actionable = sum(1 for stat in result.vendor_stats if stat.get("actionable_count", 0) > 0)
    parser_errors = sum(int(stat.get("parser_failure_count", 0)) for stat in result.vendor_stats)
    blocked_vendors = sum(1 for stat in result.vendor_stats if stat.get("blocked"))
    excluded_listings = sum(int(stat.get("excluded_count", 0)) for stat in result.vendor_stats)
    return {
        "run_mode": result.run_mode_label,
        "degraded": result.degraded,
        "fixture_fallback_used": result.fixture_fallback_used,
        "vendors_checked_count": vendors_checked,
        "vendors_with_direct_candidates_count": vendors_with_direct_candidates,
        "vendors_successfully_parsed_count": vendors_successfully_parsed,
        "vendors_with_live_actionable_listings_count": vendors_with_live_actionable,
        "parser_errors_count": parser_errors,
        "blocked_vendors_count": blocked_vendors,
        "excluded_listings_count": excluded_listings,
        "needs_review_count": len(result.needs_review),
    }


def _quality_checks(result: MonitorResult) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    health = result.run_health
    checks.append({
        "name": "direct_vendor_discovery",
        "passed": health["vendors_with_direct_candidates_count"] >= 3,
        "detail": f"{health['vendors_with_direct_candidates_count']} vendors produced direct candidates",
    })
    bogus_prices = [item for item in result.shortlist if item.price_gbp is not None and item.price_gbp < _minimum_price_floor(item)]
    checks.append({"name": "no_bogus_shortlist_prices", "passed": not bogus_prices, "detail": f"{len(bogus_prices)} suspicious shortlist prices"})
    incomplete = [
        item for item in result.shortlist
        if any(getattr(item, field) in (None, "") for field in REQUIRED_FIELDS)
        or item.stock_status != "in_stock"
        or item.ram_gb not in PLAUSIBLE_RAM_SIZES_GB
        or item.ssd_gb not in PLAUSIBLE_SSD_SIZES_GB
        or item.raw.get("price_is_ambiguous")
    ]
    checks.append({"name": "shortlist_core_fields", "passed": not incomplete, "detail": f"{len(incomplete)} shortlist rows missing core fields"})
    core_failures = [issue for issue in result.vendor_errors if issue.get("vendor_key") in CORE_VENDORS]
    checks.append({"name": "core_vendor_parser_errors", "passed": not core_failures, "detail": f"{len(core_failures)} core vendor discovery/extraction errors"})
    if result.fixture_fallback_used:
        checks.append({"name": "fixture_fallback_not_used", "passed": False, "detail": "Fixture-backed execution is not production-trustworthy"})
    else:
        checks.append({"name": "fixture_fallback_not_used", "passed": True, "detail": "Live network paths were attempted without fixture fallback"})
    return checks


def _trust_label(result: MonitorResult) -> str:
    if result.fixture_fallback_used or result.used_test_mode:
        return "Test/fixture only"
    if result.production_readiness == "Not ready":
        return "Not trustworthy for buying decisions"
    if result.degraded:
        return "Live but degraded"
    return "Production-ready"



def _production_readiness(result: MonitorResult) -> str:
    health = result.run_health
    checked = health["vendors_checked_count"]
    parsed = health["vendors_successfully_parsed_count"]
    blocked = health["blocked_vendors_count"]
    actionable = health["vendors_with_live_actionable_listings_count"]
    if result.fixture_fallback_used or result.used_test_mode:
        return "Not ready"
    if checked == 0 or blocked == checked or parsed == 0:
        return "Not ready"
    if parsed <= 2 or actionable == 0:
        return "Degraded"
    if parsed < max(3, checked - 1) or blocked > 0:
        return "Partially ready"
    return "Ready"

def _can_recommend_buy_now(result: MonitorResult) -> bool:
    if result.degraded or result.fixture_fallback_used or result.used_test_mode:
        return False
    if not result.shortlist:
        return False
    top = result.shortlist[0]
    return bool(
        top.buy_now
        and top.stock_status == "in_stock"
        and all(getattr(top, field) not in (None, "") for field in REQUIRED_FIELDS)
        and top.seller_quality_score >= 15
        and top.value_score >= 22
    )


def run_monitor(config: dict, mode: str = "full", test_mode: bool = False, vendor_filter: set[str] | None = None) -> MonitorResult:
    generated_at = utc_now_iso()
    shortlist: list[Listing] = []
    needs_review: list[Listing] = []
    vendor_errors: list[dict[str, str]] = []
    vendor_stats: list[dict[str, object]] = []
    fixture_path = config.get("test_mode", {}).get("fixture_path") if test_mode else None
    browser_config = BrowserConfig(headless=True, timeout_ms=config.get("defaults", {}).get("timeout_ms", 30000), fixture_path=fixture_path)
    with BrowserSession(browser_config) as browser:
        for vendor in config["vendors"]:
            if vendor_filter and vendor["key"] not in vendor_filter:
                continue
            logger.info("Checking vendor: %s", vendor["name"])
            vendor_stat = _empty_vendor_stat(vendor, mode)
            candidates, discovery_issues = discover_vendor_candidates(vendor, browser, mode=mode)
            vendor_stat["candidate_count"] = len(candidates)
            vendor_stat["discovery_issues"] = discovery_issues
            vendor_stat["blocked"] = any(issue.get("classification") in {"anti_bot_or_access_denied", "dns_failure", "network_failure", "timeout", "http_error"} for issue in discovery_issues)
            if discovery_issues:
                vendor_stat["last_error"] = discovery_issues[-1]["error"]
            if candidates:
                vendor_stat["discovery_status"] = "worked"
            elif discovery_issues:
                vendor_stat["discovery_status"] = "failed"
            else:
                vendor_stat["discovery_status"] = "empty"
            limit = vendor.get("stock_monitor_max_candidates", 6) if mode == "stock" else vendor.get("full_sweep_max_candidates", 12)
            if not candidates:
                selector_issue = next((issue for issue in discovery_issues if issue.get("classification") in {"anti_bot_or_access_denied", "zero_inventory", "selector_failure"}), None)
                if selector_issue:
                    if selector_issue.get("classification") == "anti_bot_or_access_denied":
                        vendor_stat["discovery_status"] = "blocked"
                        vendor_stat["blocked"] = True
                    elif selector_issue.get("classification") == "zero_inventory":
                        vendor_stat["discovery_status"] = "zero_inventory"
                    elif selector_issue.get("classification") == "selector_failure":
                        vendor_stat["discovery_status"] = "selector_failure"
                    vendor_errors.append({"vendor": vendor["name"], "vendor_key": vendor["key"], "error": selector_issue["error"]})
                else:
                    vendor_errors.append({"vendor": vendor["name"], "vendor_key": vendor["key"], "error": "No discovery candidates found"})
            for candidate in candidates[:limit]:
                try:
                    html = browser.get_html(candidate.url)
                    vendor_stat["live_fetch_success_count"] += 1
                    listing = extract_listing(vendor, candidate.url, html, candidate.source_url, generated_at)
                    if not listing:
                        vendor_stat["parser_failure_count"] += 1
                        vendor_errors.append({"vendor": vendor["name"], "vendor_key": vendor["key"], "url": candidate.url, "error": "Candidate did not validate as an in-stock 14-inch MacBook Pro product page"})
                        continue
                    vendor_stat["parser_success_count"] += 1
                    listing.notes = vendor.get("notes")
                    score_listing(listing, vendor_quality=float(vendor.get("trust_score", 10)))
                    listing = _validate_listing(listing)
                    if listing.stock_status == "in_stock":
                        vendor_stat["stock_validation_success_count"] += 1
                    if listing.review_reason:
                        vendor_stat["excluded_count"] += 1
                        needs_review.append(listing)
                    else:
                        vendor_stat["actionable_count"] += 1
                        shortlist.append(listing)
                except Exception as exc:
                    vendor_stat["live_fetch_failure_count"] += 1
                    classification = classify_fetch_error(exc)
                    vendor_stat["blocked"] = vendor_stat["blocked"] or classification in {"anti_bot_or_access_denied", "dns_failure", "network_failure", "timeout", "http_error"}
                    vendor_stat["last_error"] = str(exc)
                    vendor_errors.append({"vendor": vendor["name"], "vendor_key": vendor["key"], "url": candidate.url, "error": str(exc), "classification": classification})
                    logger.warning("Vendor %s candidate %s failed: %s", vendor["name"], candidate.url, exc)
            vendor_stats.append(vendor_stat)
    shortlist = sorted(_dedupe(shortlist), key=lambda x: x.total_score, reverse=True)
    needs_review = sorted(_dedupe(needs_review), key=lambda x: (x.review_severity or "review", x.vendor, -(x.price_gbp or 0)))
    result = MonitorResult(
        generated_at=generated_at,
        mode=mode,
        shortlist=shortlist,
        needs_review=needs_review,
        vendor_errors=vendor_errors,
        used_test_mode=test_mode,
        vendor_stats=vendor_stats,
        run_mode_label="Test mode" if test_mode else "Live mode",
        fixture_fallback_used=browser.fixture_fallback_used,
        browser_mode=browser.mode,
        live_verification_blocked=any(stat.get("blocked") for stat in vendor_stats),
    )
    result.run_health = _build_run_health(result)
    result.quality_checks = _quality_checks(result)
    result.degraded = not all(check["passed"] for check in result.quality_checks)
    result.production_readiness = _production_readiness(result)
    result.trust_label = _trust_label(result)
    result.can_recommend_buy_now = _can_recommend_buy_now(result)
    result.run_health = _build_run_health(result)
    return result


def load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, listings: list[Listing]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        item.url: {
            "vendor": item.vendor,
            "vendor_key": item.vendor_key,
            "title": item.title,
            "price_gbp": item.price_gbp,
            "stock_status": item.stock_status,
        }
        for item in listings
        if item.url
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def diff_state(previous: dict, current: list[Listing], generated_at: str) -> list[Listing]:
    changes = [
        item
        for item in current
        if previous.get(item.url or "") != {"vendor": item.vendor, "vendor_key": item.vendor_key, "title": item.title, "price_gbp": item.price_gbp, "stock_status": item.stock_status}
    ]
    current_urls = {item.url for item in current if item.url}
    for url, before in previous.items():
        if url in current_urls:
            continue
        changes.append(
            Listing(
                timestamp=generated_at,
                vendor=str(before.get("vendor") or "Unknown vendor"),
                vendor_key=str(before.get("vendor_key") or "unknown"),
                title=str(before.get("title") or url),
                price_gbp=before.get("price_gbp"),
                stock_status="out_of_stock",
                url=url,
                rationale="listing disappeared from the current shortlist",
            )
        )
    return changes
