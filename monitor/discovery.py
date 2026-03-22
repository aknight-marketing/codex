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


def extract_links(base_url: str, html_text: str, vendor: dict) -> list[CandidateLink]:
    patterns = [re.compile(p, re.I) for p in vendor.get("include_url_patterns", [])]
    exclude_patterns = [re.compile(p, re.I) for p in vendor.get("exclude_url_patterns", [])]
    required_terms = [t.lower() for t in vendor.get("required_terms", ["macbook", "pro", "14"])]
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
        haystack = f"{absolute} {title}".lower()
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
            for item in extract_links(url, html_text, vendor):
                candidates.setdefault(item.url, item)
            logger.info("Vendor %s discovery page %s -> %s candidates", vendor["name"], url, len(candidates))
        except Exception as exc:
            issues.append({"url": url, "error": str(exc), "classification": classify_fetch_error(exc)})
            logger.warning("Vendor %s discovery failed for %s: %s", vendor["name"], url, exc)
    return list(candidates.values()), issues
