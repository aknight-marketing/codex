from __future__ import annotations

import json
import logging
from pathlib import Path

from monitor.browser import BrowserConfig, BrowserSession
from monitor.discovery import CandidateLink, discover_vendor_candidates
from monitor.extractors import extract_listing
from monitor.models import Listing, MonitorResult
from monitor.scoring import score_listing
from monitor.utils import utc_now_iso

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ["price_gbp", "chip", "ram_gb", "ssd_gb", "screen_size_in"]


def _append_reason(listing: Listing, reason: str) -> None:
    reasons = [part.strip() for part in (listing.review_reason or "").split(",") if part.strip()]
    if reason not in reasons:
        reasons.append(reason)
    listing.review_reason = ", ".join(reasons) if reasons else None


def _placeholder_listing(vendor: dict, candidate: CandidateLink, timestamp: str, reason: str, *, status_label: str = "degraded_extraction") -> Listing:
    return Listing(
        timestamp=timestamp,
        vendor=vendor["name"],
        vendor_key=vendor["key"],
        title=candidate.title or candidate.url,
        stock_status=None,
        url=candidate.url,
        source_url=candidate.source_url,
        review_reason=reason,
        status_label=status_label,
        raw={"placeholder": True},
    )


def _classify_listing(listing: Listing) -> tuple[str, Listing]:
    missing = [field for field in REQUIRED_FIELDS if getattr(listing, field) in (None, "")]
    if listing.screen_size_in and not (13.8 <= listing.screen_size_in <= 14.3):
        missing.append("screen_size_in_not_14")

    if listing.stock_status == "out_of_stock":
        _append_reason(listing, "out_of_stock")
        listing.status_label = "out_of_stock"
        return "unavailable", listing

    if listing.stock_status != "in_stock":
        missing.append("stock_status_unknown")

    for field in missing:
        _append_reason(listing, field)

    if listing.review_reason:
        if listing.status_label is None:
            if "degraded" in listing.review_reason or "extractor" in listing.review_reason or "unknown" in listing.review_reason:
                listing.status_label = "degraded_extraction"
            else:
                listing.status_label = "needs_review"
        return "needs_review", listing

    listing.status_label = "actionable"
    return "shortlist", listing


def _dedupe(listings: list[Listing]) -> list[Listing]:
    deduped: dict[tuple[str, int | None, int | None, str | None], Listing] = {}
    for item in sorted(listings, key=lambda x: x.total_score, reverse=True):
        key = ((item.title or "").lower(), item.ram_gb, item.ssd_gb, item.chip)
        deduped.setdefault(key, item)
    return list(deduped.values())


def _summarize_vendor(vendor: dict, candidates: list[CandidateLink], observed: list[Listing], errors: list[dict[str, str]]) -> dict:
    actionable = sum(1 for item in observed if item.status_label == "actionable")
    review = sum(1 for item in observed if item.status_label in {"needs_review", "degraded_extraction"})
    unavailable = sum(1 for item in observed if item.status_label == "out_of_stock")
    degraded = review > 0 or any(error.get("vendor") == vendor["name"] for error in errors)
    if not candidates:
        status = "no_discovery"
    elif degraded:
        status = "degraded"
    elif actionable or unavailable:
        status = "healthy"
    else:
        status = "review_only"
    return {
        "vendor": vendor["name"],
        "vendor_key": vendor["key"],
        "candidates_found": len(candidates),
        "observed_listings": len(observed),
        "actionable": actionable,
        "needs_review": review,
        "unavailable": unavailable,
        "errors": sum(1 for error in errors if error.get("vendor") == vendor["name"]),
        "status": status,
    }


def _evaluate_readiness(config: dict, result: MonitorResult) -> MonitorResult:
    if result.used_test_mode:
        result.degraded = True
        result.trust_label = "fixture_only"
        result.production_readiness = "test_fixture_only"
        result.readiness_reasons = ["Fixture-backed test mode output cannot be trusted for buying decisions."]
        return result

    core_vendor_keys = set(config.get("watchlist_vendors", []))
    core_statuses = [status for status in result.vendor_status if not core_vendor_keys or status["vendor_key"] in core_vendor_keys]
    core_coverage = sum(1 for status in core_statuses if status["observed_listings"] > 0)
    severe_failures = []
    degraded_reasons = []

    if not result.shortlist and not result.needs_review:
        severe_failures.append("No observed live listings were produced.")
    if core_statuses and core_coverage < max(1, len(core_statuses) // 2):
        severe_failures.append("Less than half of core watchlist vendors produced any observable listing.")

    for status in core_statuses:
        if status["status"] == "no_discovery":
            severe_failures.append(f"{status['vendor']} produced no discovery candidates.")
        elif status["status"] in {"degraded", "review_only"}:
            degraded_reasons.append(f"{status['vendor']} requires review or had extraction issues.")

    if result.vendor_errors:
        degraded_reasons.append(f"{len(result.vendor_errors)} vendor fetch/extraction errors were recorded.")

    if severe_failures:
        result.degraded = True
        result.trust_label = "not_trustworthy"
        result.production_readiness = "not_trustworthy_for_buying"
        result.readiness_reasons = severe_failures + degraded_reasons
    elif degraded_reasons:
        result.degraded = True
        result.trust_label = "degraded_live"
        result.production_readiness = "live_but_degraded"
        result.readiness_reasons = degraded_reasons
    else:
        result.degraded = False
        result.trust_label = "production_ready"
        result.production_readiness = "production_ready"
        result.readiness_reasons = ["All core watchlist vendors produced observable listings without extraction degradation."]
    return result


def run_monitor(config: dict, mode: str = "full", test_mode: bool = False, vendor_filter: set[str] | None = None) -> MonitorResult:
    generated_at = utc_now_iso()
    shortlist: list[Listing] = []
    needs_review: list[Listing] = []
    unavailable: list[Listing] = []
    vendor_errors: list[dict[str, str]] = []
    vendor_status: list[dict] = []
    fixture_path = config.get("test_mode", {}).get("fixture_path") if test_mode else None
    browser_config = BrowserConfig(
        headless=True,
        timeout_ms=config.get("defaults", {}).get("timeout_ms", 30000),
        fixture_path=fixture_path,
    )
    with BrowserSession(browser_config) as browser:
        for vendor in config["vendors"]:
            if vendor_filter and vendor["key"] not in vendor_filter:
                continue
            logger.info("Checking vendor: %s", vendor["name"])
            candidates = discover_vendor_candidates(vendor, browser, mode=mode)
            limit = vendor.get("stock_monitor_max_candidates", 6) if mode == "stock" else vendor.get("full_sweep_max_candidates", 12)
            observed_for_vendor: list[Listing] = []
            if not candidates:
                vendor_errors.append({"vendor": vendor["name"], "error": "No discovery candidates found"})
            for candidate in candidates[:limit]:
                try:
                    html = browser.get_html(candidate.url)
                    listing = extract_listing(vendor, candidate.url, html, candidate.source_url, generated_at)
                    if not listing:
                        listing = _placeholder_listing(vendor, candidate, generated_at, "extractor_returned_none")
                    listing.notes = vendor.get("notes")
                    score_listing(listing, vendor_quality=float(vendor.get("trust_score", 10)))
                    bucket, listing = _classify_listing(listing)
                    observed_for_vendor.append(listing)
                    if bucket == "shortlist":
                        shortlist.append(listing)
                    elif bucket == "unavailable":
                        unavailable.append(listing)
                    else:
                        needs_review.append(listing)
                except Exception as exc:
                    vendor_errors.append({"vendor": vendor["name"], "url": candidate.url, "error": str(exc)})
                    logger.warning("Vendor %s candidate %s failed: %s", vendor["name"], candidate.url, exc)
                    placeholder = _placeholder_listing(vendor, candidate, generated_at, f"candidate_exception: {exc}")
                    observed_for_vendor.append(placeholder)
                    needs_review.append(placeholder)
            vendor_status.append(_summarize_vendor(vendor, candidates[:limit], observed_for_vendor, vendor_errors))
    shortlist = sorted(_dedupe(shortlist), key=lambda x: x.total_score, reverse=True)
    needs_review = sorted(_dedupe(needs_review), key=lambda x: (x.vendor, x.review_reason or "", x.title))
    unavailable = sorted(_dedupe(unavailable), key=lambda x: (x.vendor, x.title))
    result = MonitorResult(
        generated_at=generated_at,
        mode=mode,
        shortlist=shortlist,
        needs_review=needs_review,
        unavailable=unavailable,
        vendor_errors=vendor_errors,
        vendor_status=vendor_status,
        used_test_mode=test_mode,
    )
    return _evaluate_readiness(config, result)


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"generated_at": None, "entries": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "entries" in payload:
        return payload
    if isinstance(payload, dict):
        return {"generated_at": None, "entries": payload}
    return {"generated_at": None, "entries": {}}


def build_state_entries(result: MonitorResult) -> dict[str, dict]:
    entries: dict[str, dict] = {}
    for item in result.shortlist + result.needs_review + result.unavailable:
        if not item.url:
            continue
        entries[item.url] = {
            "title": item.title,
            "vendor": item.vendor,
            "vendor_key": item.vendor_key,
            "status_label": item.status_label,
            "stock_status": item.stock_status,
            "review_reason": item.review_reason,
            "price_gbp": item.price_gbp,
            "total_score": item.total_score,
            "source_url": item.source_url,
            "last_seen": result.generated_at,
        }
    return entries


def save_state(path: Path, result: MonitorResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": result.generated_at,
        "mode": result.mode,
        "entries": build_state_entries(result),
        "vendor_status": result.vendor_status,
        "trust_label": result.trust_label,
        "production_readiness": result.production_readiness,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def diff_state(previous: dict, result: MonitorResult) -> list[dict]:
    previous_entries = previous.get("entries", {}) if isinstance(previous, dict) else {}
    current_entries = build_state_entries(result)
    changes: list[dict] = []
    tracked_fields = ["status_label", "stock_status", "price_gbp", "review_reason", "total_score"]
    for url, current in current_entries.items():
        prior = previous_entries.get(url)
        if prior is None:
            changes.append({
                "change_type": "newly_observed",
                "url": url,
                "vendor": current["vendor"],
                "title": current["title"],
                "previous_status_label": None,
                "current_status_label": current["status_label"],
                "previous_stock_status": None,
                "current_stock_status": current["stock_status"],
                "reason": current["review_reason"] or current["status_label"],
            })
            continue
        changed = any(prior.get(field) != current.get(field) for field in tracked_fields)
        if changed:
            changes.append({
                "change_type": "state_changed",
                "url": url,
                "vendor": current["vendor"],
                "title": current["title"],
                "previous_status_label": prior.get("status_label"),
                "current_status_label": current["status_label"],
                "previous_stock_status": prior.get("stock_status"),
                "current_stock_status": current["stock_status"],
                "reason": current["review_reason"] or current["status_label"],
            })
    for url, prior in previous_entries.items():
        if url not in current_entries:
            changes.append({
                "change_type": "disappeared_from_discovery",
                "url": url,
                "vendor": prior.get("vendor"),
                "title": prior.get("title"),
                "previous_status_label": prior.get("status_label"),
                "current_status_label": None,
                "previous_stock_status": prior.get("stock_status"),
                "current_stock_status": None,
                "reason": "Previously tracked listing was not rediscovered in the latest run.",
            })
    return changes
