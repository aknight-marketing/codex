from __future__ import annotations

import html
import logging
import re
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
