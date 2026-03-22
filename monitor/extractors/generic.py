from __future__ import annotations

import html
import json
import re
from urllib.parse import urlparse

from monitor.models import Listing
from monitor.utils import clean_whitespace, parse_chip, parse_keyboard, parse_price, parse_ram_gb, parse_screen_size, parse_ssd_gb

TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
SCRIPT_JSON_RE = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")
BUY_RE = re.compile(r"add to (?:basket|bag|cart)|buy now|configure options|shop now", re.I)
NEGATIVE_RE = re.compile(r"sold out|out of stock|unavailable|notify me|pre-?order|archived", re.I)
POSITIVE_RE = re.compile(r"in stock|available now|ready to ship|last one left", re.I)
WARRANTY_RE = re.compile(r"(\d+\s*(?:month|year)s?\s+(?:warranty|guarantee))", re.I)
RETURNS_RE = re.compile(r"(\d+\s*-?day\s+returns?)", re.I)
DELIVERY_RE = re.compile(r"((?:next|free|express|standard)[^.\n]{0,60}(?:delivery|shipping))", re.I)


def strip_tags(value: str) -> str:
    return clean_whitespace(html.unescape(TAG_RE.sub(" ", value)))


def _iter_json_nodes(payload):
    if isinstance(payload, list):
        for item in payload:
            yield from _iter_json_nodes(item)
        return
    if not isinstance(payload, dict):
        return
    yield payload
    graph = payload.get("@graph")
    if isinstance(graph, list):
        for item in graph:
            yield from _iter_json_nodes(item)
    for value in payload.values():
        if isinstance(value, (dict, list)) and value is not graph:
            yield from _iter_json_nodes(value)


def _type_matches(node: dict, expected: str) -> bool:
    node_type = node.get("@type")
    if isinstance(node_type, list):
        return expected in node_type
    return node_type == expected


def extract_product_json(html_text: str) -> dict:
    for raw in SCRIPT_JSON_RE.findall(html_text):
        try:
            payload = json.loads(html.unescape(raw.strip()))
        except Exception:
            continue
        for node in _iter_json_nodes(payload):
            if _type_matches(node, "Product"):
                return node
    return {}


def text_content(html_text: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html_text, flags=re.I | re.S)
    return strip_tags(text)


def title_from_html(html_text: str, product: dict | None = None) -> str:
    if isinstance(product, dict) and product.get("name"):
        return clean_whitespace(str(product["name"]))
    title_match = TITLE_RE.search(html_text)
    if title_match:
        return strip_tags(title_match.group(1))
    h1_match = H1_RE.search(html_text)
    return strip_tags(h1_match.group(1)) if h1_match else ""


def stock_from_html(html_text: str, text: str, product: dict | None = None) -> tuple[str | None, str | None, str | None]:
    offers = product.get("offers") if isinstance(product, dict) else None
    if isinstance(offers, list):
        flattened = []
        for offer in offers:
            if isinstance(offer, dict):
                flattened.append(offer)
            elif isinstance(offer, list):
                flattened.extend(item for item in offer if isinstance(item, dict))
        offers = next(iter(flattened), None)
    if isinstance(offers, dict):
        availability = str(offers.get("availability") or "")
        lower = availability.lower()
        if "instock" in lower:
            return "in_stock", availability, "structured_data"
        if "outofstock" in lower:
            return "out_of_stock", availability, "structured_data"
    if BUY_RE.search(html_text) and not NEGATIVE_RE.search(text):
        return "in_stock", BUY_RE.search(html_text).group(0), "buy_button"
    if POSITIVE_RE.search(text) and not NEGATIVE_RE.search(text):
        return "in_stock", POSITIVE_RE.search(text).group(0), "text_badge"
    if NEGATIVE_RE.search(text):
        return "out_of_stock", NEGATIVE_RE.search(text).group(0), "negative_text"
    return None, None, None


def build_listing(vendor: dict, url: str, source_url: str, timestamp: str, html_text: str, *, title: str | None = None, text: str | None = None, price: float | None = None, chip: str | None = None, ram_gb: int | None = None, ssd_gb: int | None = None, screen_size_in: float | None = None, stock_status: str | None = None, availability_text: str | None = None, stock_evidence: str | None = None, condition: str | None = None, warranty: str | None = None, returns: str | None = None, delivery_estimate: str | None = None, keyboard_layout: str | None = None) -> Listing:
    product = extract_product_json(html_text)
    text = text or text_content(html_text)
    title = clean_whitespace(title or title_from_html(html_text, product))
    return Listing(
        timestamp=timestamp,
        vendor=vendor["name"],
        vendor_key=vendor["key"],
        title=title,
        chip=chip or parse_chip(f"{title} {text}"),
        ram_gb=ram_gb or parse_ram_gb(f"{title} {text}"),
        ssd_gb=ssd_gb or parse_ssd_gb(f"{title} {text}"),
        screen_size_in=screen_size_in or parse_screen_size(f"{title} {text}"),
        condition=condition or vendor.get("defaults", {}).get("condition"),
        stock_status=stock_status,
        price_gbp=price if price is not None else parse_price(text),
        warranty=warranty or (WARRANTY_RE.search(text).group(1) if WARRANTY_RE.search(text) else vendor.get("defaults", {}).get("warranty")),
        returns=returns or (RETURNS_RE.search(text).group(1) if RETURNS_RE.search(text) else vendor.get("defaults", {}).get("returns")),
        delivery_estimate=delivery_estimate or (DELIVERY_RE.search(text).group(1) if DELIVERY_RE.search(text) else None),
        keyboard_layout=keyboard_layout or parse_keyboard(text) or vendor.get("defaults", {}).get("keyboard_layout"),
        url=url,
        source_url=source_url,
        availability_text=availability_text,
        stock_evidence=stock_evidence,
        raw={"domain": urlparse(url).netloc, "product_json_ld": product},
    )


def extract_generic(vendor: dict, url: str, html_text: str, source_url: str, timestamp: str) -> Listing | None:
    product = extract_product_json(html_text)
    text = text_content(html_text)
    title = title_from_html(html_text, product)
    combined = f"{title} {text}".lower()
    if "macbook pro" not in combined or "14" not in combined:
        return None
    stock_status, availability_text, stock_evidence = stock_from_html(html_text, text, product)
    if stock_status != "in_stock":
        return None
    return build_listing(vendor, url, source_url, timestamp, html_text, title=title, text=text, stock_status=stock_status, availability_text=availability_text, stock_evidence=stock_evidence)
