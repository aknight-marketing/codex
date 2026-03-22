from __future__ import annotations

import re

from monitor.extractors.generic import build_listing, extract_generic, extract_product_json, stock_from_html, text_content, title_from_html
from monitor.utils import VALID_RAM_SIZES_GB, parse_ssd_gb


def _search(pattern: str, text: str, flags: int = re.I):
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else None


def _offer_price(product):
    if not isinstance(product, dict):
        return None
    offers = product.get("offers")
    if isinstance(offers, dict):
        offers = [offers]
    elif isinstance(offers, list):
        flattened = []
        for offer in offers:
            if isinstance(offer, dict):
                flattened.append(offer)
            elif isinstance(offer, list):
                flattened.extend(item for item in offer if isinstance(item, dict))
        offers = flattened
    else:
        offers = []
    prices = []
    for offer in offers:
        if not isinstance(offer, dict):
            continue
        value = offer.get("price")
        if value in (None, ""):
            continue
        try:
            prices.append(float(str(value).replace(",", "")))
        except ValueError:
            continue
    return min(prices) if prices else None


def _max_price(text: str):
    prices = []
    for match in re.finditer(r"£\s*([\d,]+(?:\.\d{2})?)", text):
        cleaned = float(match.group(1).replace(",", ""))
        prefix = text[max(0, match.start() - 18):match.start()].lower()
        suffix = text[match.end():match.end() + 18].lower()
        if any(token in prefix for token in ["from ", "deposit ", "starting at "]) or any(token in suffix for token in [" deposit", " per month"]):
            continue
        prices.append(cleaned)
    if prices:
        return max(prices)
    fallback = re.findall(r"£\s*([\d,]+(?:\.\d{2})?)", text)
    return max((float(item.replace(",", "")) for item in fallback), default=None)


def _all_prices(html_text: str, text: str) -> list[float]:
    prices: list[float] = []
    for match in re.finditer(r"(?:£|GBP\s?)([\d,]+(?:\.\d{2})?)", f"{html_text}\n{text}", re.I):
        try:
            prices.append(float(match.group(1).replace(",", "")))
        except ValueError:
            continue
    return prices


def _extract_macfinder_price(html_text: str, text: str, product: dict) -> tuple[float | None, bool]:
    candidates = []
    structured_price = _offer_price(product)
    if structured_price is not None:
        candidates.append(structured_price)
    text_price = _max_price(text)
    if text_price is not None:
        candidates.append(text_price)
    candidates.extend(price for price in _all_prices(html_text, text) if price >= 500)
    if not candidates:
        return None, False
    best = max(candidates)
    low_prices = [price for price in _all_prices(html_text, text) if price < max(500, best * 0.5)]
    ambiguous = bool(low_prices and best > min(low_prices) * 2)
    return best, ambiguous


def _cex_ram_from_text(text: str) -> int | None:
    for pattern in [r"/(\d+)GB\s+Ram\b", r"\b(\d+)GB\s+Ram\b", r"\b(\d+)GB\s+(?:unified\s+)?memory\b"]:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        value = int(match.group(1))
        if value in VALID_RAM_SIZES_GB:
            return value
    parsed = [int(value) for value in re.findall(r"(\d+)GB", text, re.I) if int(value) in VALID_RAM_SIZES_GB]
    return max(parsed) if parsed else None


def _cex_ssd_from_text(text: str) -> int | None:
    for pattern in [r"/((?:\d+(?:\.\d+)?)\s?(?:TB|GB))\s+SSD\b", r"\b((?:\d+(?:\.\d+)?)\s?(?:TB|GB))\s+SSD\b"]:
        match = re.search(pattern, text, re.I)
        if match:
            return parse_ssd_gb(match.group(1) + " SSD")
    return parse_ssd_gb(text)


def extract_apple(vendor, url, html_text, source_url, timestamp):
    product = extract_product_json(html_text)
    text = text_content(html_text)
    title = title_from_html(html_text, product)
    stock_status, availability_text, evidence = stock_from_html(html_text, text, product)
    combined = f"{title} {text}".lower()
    if "14-inch" not in combined and "14 inch" not in combined and "14.2-inch" not in combined:
        return None
    if "16-inch" in combined or "16 inch" in combined:
        return None
    if stock_status != "in_stock" or "add to bag" not in html_text.lower():
        return None
    ssd_tb = _search(r"((?:\d+(?:\.\d+)?)\s?TB) SSD", text)
    ssd_gb = int(float(ssd_tb.upper().replace("TB", "").strip()) * 1024) if ssd_tb else (int(_search(r"(\d+)GB SSD", text) or 0) or None)
    return build_listing(vendor, url, source_url, timestamp, html_text, title=title, text=text, stock_status=stock_status, availability_text=availability_text, stock_evidence=evidence or "apple_add_to_bag", price=_offer_price(product), ram_gb=int(_search(r"(\d+)GB unified memory", text) or 0) or None, ssd_gb=ssd_gb, keyboard_layout="UK")


def extract_macfinder(vendor, url, html_text, source_url, timestamp):
    product = extract_product_json(html_text)
    text = text_content(html_text)
    lowered = text.lower()
    if "last one left" not in lowered and "in stock" not in lowered:
        return None
    price, ambiguous_price = _extract_macfinder_price(html_text, text, product)
    listing = build_listing(vendor, url, source_url, timestamp, html_text, title=title_from_html(html_text, product), text=text, stock_status="in_stock", availability_text="Last One Left" if "last one left" in lowered else "In stock", stock_evidence="macfinder_stock_badge", price=price, ram_gb=int(_search(r"(\d+)GB Memory", text) or 0) or None, ssd_gb=int(_search(r"(\d+)GB SSD Storage", text) or 0) or None, keyboard_layout="UK")
    listing.raw["price_is_ambiguous"] = ambiguous_price
    return listing


def extract_hoxton(vendor, url, html_text, source_url, timestamp):
    text = text_content(html_text)
    if "add to cart" not in html_text.lower() and "buy now" not in text.lower():
        return None
    return build_listing(vendor, url, source_url, timestamp, html_text, text=text, stock_status="in_stock", availability_text="Add to cart", stock_evidence="hoxton_add_to_cart", price=float((_search(r"£([\d,]+(?:\.\d{2})?)", text) or "0").replace(',', '')) or None)


def extract_back_market(vendor, url, html_text, source_url, timestamp):
    product = extract_product_json(html_text)
    text = text_content(html_text)
    buy_signal = 'add to basket' if 'add to basket' in html_text.lower() else ('buy' if 'buy' in text.lower() else None)
    stock_status, availability_text, evidence = stock_from_html(html_text, text, product)
    if stock_status != 'in_stock' or not buy_signal:
        return None
    return build_listing(vendor, url, source_url, timestamp, html_text, text=text, stock_status='in_stock', availability_text=availability_text or buy_signal, stock_evidence=evidence or 'backmarket_buy_button', price=_offer_price(product))


def extract_cex(vendor, url, html_text, source_url, timestamp):
    text = text_content(html_text)
    if 'add to basket' not in html_text.lower() and 'in stock online' not in text.lower():
        return None
    title = title_from_html(html_text)
    listing = build_listing(
        vendor,
        url,
        source_url,
        timestamp,
        html_text,
        title=title,
        text=text,
        stock_status='in_stock',
        availability_text='In stock online',
        stock_evidence='cex_stock_badge',
        price=float((_search(r'£([\d,]+(?:\.\d{2})?)', text) or '0').replace(',', '')) or None,
        ram_gb=_cex_ram_from_text(title) or _cex_ram_from_text(text),
        ssd_gb=_cex_ssd_from_text(title) or _cex_ssd_from_text(text),
    )
    return listing


def extract_musicmagpie(vendor, url, html_text, source_url, timestamp):
    text = text_content(html_text)
    if 'add to basket' not in html_text.lower() and 'in stock' not in text.lower():
        return None
    return build_listing(vendor, url, source_url, timestamp, html_text, text=text, stock_status='in_stock', availability_text='In stock', stock_evidence='musicmagpie_buy_button', price=float((_search(r'£([\d,]+(?:\.\d{2})?)', text) or '0').replace(',', '')) or None)


EXTRACTORS = {
    'apple_refurb_uk': extract_apple,
    'macfinder': extract_macfinder,
    'hoxton_macs': extract_hoxton,
    'back_market_uk': extract_back_market,
    'cex': extract_cex,
    'musicmagpie': extract_musicmagpie,
}


def extract_listing(vendor: dict, url: str, html_text: str, source_url: str, timestamp: str):
    extractor = EXTRACTORS.get(vendor['key'], extract_generic)
    listing = extractor(vendor, url, html_text, source_url, timestamp)
    if listing:
        listing.raw['extractor'] = extractor.__name__
    return listing
