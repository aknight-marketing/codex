from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from monitor.browser import classify_fetch_error

logger = logging.getLogger(__name__)

A_RE = re.compile(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)


@dataclass
class CandidateLink:
    url: str
    title: str
    source_url: str
    discovery_method: str = "direct_vendor_page"


def _strip_tags(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", value))).strip()


def _is_allowed_domain(absolute: str, vendor: dict) -> bool:
    parsed = urlparse(absolute)
    return not vendor.get("domains") or any(domain in parsed.netloc for domain in vendor["domains"])


def _page_context(html_text: str) -> str:
    parts = []
    title = TITLE_RE.search(html_text)
    h1 = H1_RE.search(html_text)
    if title:
        parts.append(_strip_tags(title.group(1)))
    if h1:
        parts.append(_strip_tags(h1.group(1)))
    return " ".join(parts)


def _classify_discovery_page(html_text: str) -> dict[str, str] | None:
    lowered = html_text.lower()
    if any(token in lowered for token in ["access denied", "captcha", "forbidden", "cloudflare", "verify you are human"]):
        return {"error": "Discovery blocked by anti-bot or access denial", "classification": "anti_bot_or_access_denied"}
    if any(token in lowered for token in ["0 products", "no products", "no results", "sold out", "out of stock"]):
        return {"error": "Discovery found zero inventory", "classification": "zero_inventory"}
    return {"error": "Discovery page fetched but no candidate product links matched selectors", "classification": "selector_failure"}


def extract_links(base_url: str, html_text: str, vendor: dict) -> list[CandidateLink]:
    patterns = [re.compile(p, re.I) for p in vendor.get("include_url_patterns", [])]
    exclude_patterns = [re.compile(p, re.I) for p in vendor.get("exclude_url_patterns", [])]
    required_terms = [t.lower() for t in vendor.get("required_terms", ["macbook", "pro", "14"])]
    page_context = _page_context(html_text).lower()
    found: dict[str, CandidateLink] = {}
    for href, label_html in A_RE.findall(html_text):
        absolute = urljoin(base_url, html.unescape(href))
        if not _is_allowed_domain(absolute, vendor):
            continue
        if patterns and not any(p.search(absolute) for p in patterns):
            continue
        if any(p.search(absolute) for p in exclude_patterns):
            continue
        title = _strip_tags(label_html)
        haystack = f"{absolute} {title} {page_context}".lower()
        if required_terms and not all(term in haystack for term in required_terms):
            continue
        found.setdefault(absolute, CandidateLink(url=absolute, title=title or absolute, source_url=base_url))
    return list(found.values())


def _looks_like_product_page(url: str, vendor: dict) -> bool:
    return any(fragment in url for fragment in vendor.get("product_page_fragments", []))


def discover_vendor_candidates(vendor: dict, browser, mode: str = "full") -> tuple[list[CandidateLink], list[dict[str, str]]]:
    urls = vendor.get("watch_urls", []) if mode == "stock" and vendor.get("watch_urls") else vendor.get("discovery_urls", [])
    if not urls and vendor.get("watch_urls"):
        urls = vendor.get("watch_urls", [])
    candidates: dict[str, CandidateLink] = {}
    issues: list[dict[str, str]] = []
    for url in urls:
        try:
            html_text = browser.get_html(url)
            if _looks_like_product_page(url, vendor):
                candidates.setdefault(url, CandidateLink(url=url, title=url, source_url=url))
                continue
            extracted = extract_links(url, html_text, vendor)
            for item in extracted:
                candidates.setdefault(item.url, item)
            if not extracted:
                issue = _classify_discovery_page(html_text)
                if issue:
                    issues.append({"url": url, **issue})
            logger.info("Vendor %s discovery page %s -> %s candidates", vendor["name"], url, len(candidates))
        except Exception as exc:
            issues.append({"url": url, "error": str(exc), "classification": classify_fetch_error(exc)})
            logger.warning("Vendor %s discovery failed for %s: %s", vendor["name"], url, exc)
    return list(candidates.values()), issues
