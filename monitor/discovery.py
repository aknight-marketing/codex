from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

A_RE = re.compile(r"<a[^>]+href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", re.I | re.S)
import urllib.parse
import urllib.request
from dataclasses import dataclass

logger = logging.getLogger(__name__)
DDG_HTML = "https://html.duckduckgo.com/html/?{}"
RESULT_RE = re.compile(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class CandidateLink:
    url: str
    title: str
    source_url: str


def _strip_tags(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", value))).strip()


def extract_links(base_url: str, html_text: str, vendor: dict) -> list[CandidateLink]:
    patterns = [re.compile(p, re.I) for p in vendor.get("include_url_patterns", [])]
    exclude_patterns = [re.compile(p, re.I) for p in vendor.get("exclude_url_patterns", [])]
    required_terms = [t.lower() for t in vendor.get("required_terms", ["macbook", "pro", "14"])]
    found: dict[str, CandidateLink] = {}
    for href, label_html in A_RE.findall(html_text):
        absolute = urljoin(base_url, html.unescape(href))
        parsed = urlparse(absolute)
        if vendor.get("domains") and not any(domain in parsed.netloc for domain in vendor["domains"]):
            continue
        if patterns and not any(p.search(absolute) for p in patterns):
            continue
        if any(p.search(absolute) for p in exclude_patterns):
            continue
        title = _strip_tags(label_html)
        haystack = f"{absolute} {title}".lower()
        if not all(term in haystack for term in required_terms):
            continue
        found.setdefault(absolute, CandidateLink(url=absolute, title=title or absolute, source_url=base_url))
    return list(found.values())


def discover_vendor_candidates(vendor: dict, browser, mode: str = "full") -> list[CandidateLink]:
    urls = vendor.get("watch_urls", []) if mode == "stock" and vendor.get("watch_urls") else vendor.get("discovery_urls", [])
    if not urls and vendor.get("watch_urls"):
        urls = vendor.get("watch_urls", [])
    candidates: dict[str, CandidateLink] = {}
    for url in urls:
        try:
            html_text = browser.get_html(url)
            if vendor.get("watch_urls") and mode == "stock" and any(url == watch for watch in vendor.get("watch_urls", [])) and any(p in url for p in vendor.get("product_page_fragments", [])):
                candidates.setdefault(url, CandidateLink(url=url, title=url, source_url=url))
                continue
            for item in extract_links(url, html_text, vendor):
                candidates.setdefault(item.url, item)
            logger.info("Vendor %s discovery page %s -> %s candidates", vendor["name"], url, len(candidates))
        except Exception as exc:
            logger.warning("Vendor %s discovery failed for %s: %s", vendor["name"], url, exc)
    return list(candidates.values())
    return html.unescape(TAG_RE.sub(" ", value)).strip()


def fetch_search_results(query: str, max_results: int = 10, user_agent: str = "Mozilla/5.0") -> list[CandidateLink]:
    params = urllib.parse.urlencode({"q": query})
    source_url = DDG_HTML.format(params)
    req = urllib.request.Request(source_url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=30) as response:
        html_text = response.read().decode("utf-8", errors="ignore")
    links: list[CandidateLink] = []
    for href, title_html in RESULT_RE.findall(html_text):
        links.append(CandidateLink(url=html.unescape(href), title=_strip_tags(title_html), source_url=source_url))
        if len(links) >= max_results:
            break
    return links


def discover_vendor_candidates(vendor: dict) -> list[CandidateLink]:
    candidates: list[CandidateLink] = []
    for query in vendor.get("search_queries", []):
        try:
            found = fetch_search_results(query, max_results=vendor.get("max_search_results", 10))
            logger.info("Vendor %s: query '%s' -> %s candidates", vendor["name"], query, len(found))
            candidates.extend(found)
        except Exception as exc:
            logger.warning("Vendor %s: search failed for '%s': %s", vendor["name"], query, exc)
    allowed_domains = tuple(vendor.get("domains", []))
    unique: dict[str, CandidateLink] = {}
    for item in candidates:
        if allowed_domains and not any(domain in item.url for domain in allowed_domains):
            continue
        unique.setdefault(item.url, item)
    return list(unique.values())
