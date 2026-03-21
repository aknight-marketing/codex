from __future__ import annotations

import re

from monitor.extractors.generic import build_listing, extract_generic, extract_product_json, stock_from_html, text_content, title_from_html


def _search(pattern: str, text: str, flags: int = re.I):
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else None


def _offer_price(product):
    offers = product.get('offers') if isinstance(product, dict) else None
    if isinstance(offers, list):
        offers = next((item for item in offers if isinstance(item, dict)), {})
    elif not isinstance(offers, dict):
        offers = {}
    value = offers.get('price', 0) or 0
    return float(value) or None


def extract_apple(vendor, url, html_text, source_url, timestamp):
    product = extract_product_json(html_text)
    text = text_content(html_text)
    title = title_from_html(html_text, product)
    stock_status, availability_text, evidence = stock_from_html(html_text, text, product)
    combined = f"{title} {text}".lower()
    if '14-inch' not in combined and '14 inch' not in combined:
        return None
    if '16-inch' in combined or '16 inch' in combined:
        return None
    if stock_status != 'in_stock' or 'add to bag' not in html_text.lower():
        return None
    return build_listing(vendor, url, source_url, timestamp, html_text, title=title, text=text, stock_status=stock_status, availability_text=availability_text, stock_evidence='apple_add_to_bag', price=_offer_price(product), ram_gb=int(_search(r'(\d+)GB unified memory', text) or 0) or None, ssd_gb=(int(float((_search(r'((?:\d+(?:\.\d+)?)\s?TB) SSD', text) or '0TB').upper().replace('TB',''))) * 1024 if 'TB' in (_search(r'((?:\d+(?:\.\d+)?)\s?TB) SSD', text) or '') else int((_search(r'(\d+)GB SSD', text) or 0)) or None), keyboard_layout='UK')


def extract_macfinder(vendor, url, html_text, source_url, timestamp):
    text = text_content(html_text)
    if 'last one left' not in text.lower() and 'in stock' not in text.lower():
        return None
    return build_listing(vendor, url, source_url, timestamp, html_text, title=title_from_html(html_text), text=text, stock_status='in_stock', availability_text='Last One Left' if 'last one left' in text.lower() else 'In stock', stock_evidence='macfinder_stock_badge', price=float((_search(r'£([\d,]+(?:\.\d{2})?)', text) or '0').replace(',','')) or None, ram_gb=int(_search(r'(\d+)GB Memory', text) or 0) or None, ssd_gb=int(_search(r'(\d+)GB SSD Storage', text) or 0) or None, keyboard_layout='UK')


def extract_hoxton(vendor, url, html_text, source_url, timestamp):
    text = text_content(html_text)
    if 'add to cart' not in html_text.lower() and 'buy now' not in text.lower():
        return None
    return build_listing(vendor, url, source_url, timestamp, html_text, text=text, stock_status='in_stock', availability_text='Add to cart', stock_evidence='hoxton_add_to_cart', price=float((_search(r'£([\d,]+(?:\.\d{2})?)', text) or '0').replace(',','')) or None)


def extract_back_market(vendor, url, html_text, source_url, timestamp):
    product = extract_product_json(html_text)
    text = text_content(html_text)
    buy_signal = 'add to basket' if 'add to basket' in html_text.lower() else ('buy' if 'buy' in text.lower() else None)
    stock_status, availability_text, evidence = stock_from_html(html_text, text, product)
    if stock_status != 'in_stock' or not buy_signal:
        return None
    return build_listing(vendor, url, source_url, timestamp, html_text, text=text, stock_status='in_stock', availability_text=availability_text or buy_signal, stock_evidence='backmarket_buy_button', price=float(product.get('offers', {}).get('price', 0) or 0) or None)


def extract_cex(vendor, url, html_text, source_url, timestamp):
    text = text_content(html_text)
    if 'add to basket' not in html_text.lower() and 'in stock online' not in text.lower():
        return None
    return build_listing(vendor, url, source_url, timestamp, html_text, text=text, stock_status='in_stock', availability_text='In stock online', stock_evidence='cex_stock_badge', price=float((_search(r'£([\d,]+(?:\.\d{2})?)', text) or '0').replace(',','')) or None)


def extract_musicmagpie(vendor, url, html_text, source_url, timestamp):
    text = text_content(html_text)
    if 'add to basket' not in html_text.lower() and 'in stock' not in text.lower():
        return None
    return build_listing(vendor, url, source_url, timestamp, html_text, text=text, stock_status='in_stock', availability_text='In stock', stock_evidence='musicmagpie_buy_button', price=float((_search(r'£([\d,]+(?:\.\d{2})?)', text) or '0').replace(',','')) or None)


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
