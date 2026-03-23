from __future__ import annotations

import re

from monitor.extractors.generic import build_listing, extract_generic, extract_product_json, stock_from_html, text_content, title_from_html


def _search(pattern: str, text: str, flags: int = re.I):
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else None


def extract_apple(vendor, url, html_text, source_url, timestamp):
    product = extract_product_json(html_text)
    text = text_content(html_text)
    title = title_from_html(html_text, product)
    stock_status, availability_text, evidence = stock_from_html(html_text, text, product)
    buyable = 'add to bag' in html_text.lower()
    review_reason = None
    status_label = None
    if stock_status == 'out_of_stock':
        review_reason = 'out_of_stock'
        status_label = 'out_of_stock'
    elif stock_status != 'in_stock' or not buyable:
        review_reason = 'apple_buy_signal_missing' if stock_status == 'in_stock' else 'stock_status_unknown'
        status_label = 'degraded_extraction'
    return build_listing(vendor, url, source_url, timestamp, html_text, title=title, text=text, stock_status=stock_status, availability_text=availability_text, stock_evidence='apple_add_to_bag' if buyable else (evidence or 'apple_page_seen'), price=float(product.get('offers', {}).get('price', 0) or 0) or None, ram_gb=int(_search(r'(\d+)GB unified memory', text) or 0) or None, ssd_gb=(int(float((_search(r'((?:\d+(?:\.\d+)?)\s?TB) SSD', text) or '0TB').upper().replace('TB',''))) * 1024 if 'TB' in (_search(r'((?:\d+(?:\.\d+)?)\s?TB) SSD', text) or '') else int((_search(r'(\d+)GB SSD', text) or 0)) or None), keyboard_layout='UK', review_reason=review_reason, status_label=status_label)


def extract_macfinder(vendor, url, html_text, source_url, timestamp):
    text = text_content(html_text)
    in_stock = 'last one left' in text.lower() or 'in stock' in text.lower()
    out_of_stock = 'out of stock' in text.lower() or 'sold' in text.lower()
    stock_status = 'in_stock' if in_stock else ('out_of_stock' if out_of_stock else None)
    review_reason = None if in_stock else ('out_of_stock' if out_of_stock else 'macfinder_stock_unknown')
    status_label = None if in_stock else ('out_of_stock' if out_of_stock else 'degraded_extraction')
    return build_listing(vendor, url, source_url, timestamp, html_text, title=title_from_html(html_text), text=text, stock_status=stock_status, availability_text='Last One Left' if 'last one left' in text.lower() else ('In stock' if in_stock else None), stock_evidence='macfinder_stock_badge' if in_stock else 'macfinder_page_seen', price=float((_search(r'£([\d,]+(?:\.\d{2})?)', text) or '0').replace(',','')) or None, ram_gb=int(_search(r'(\d+)GB Memory', text) or 0) or None, ssd_gb=int(_search(r'(\d+)GB SSD Storage', text) or 0) or None, keyboard_layout='UK', review_reason=review_reason, status_label=status_label)


def extract_hoxton(vendor, url, html_text, source_url, timestamp):
    text = text_content(html_text)
    buyable = 'add to cart' in html_text.lower() or 'buy now' in text.lower()
    out_of_stock = 'sold out' in text.lower() or 'out of stock' in text.lower()
    stock_status = 'in_stock' if buyable else ('out_of_stock' if out_of_stock else None)
    review_reason = None if buyable else ('out_of_stock' if out_of_stock else 'hoxton_buy_signal_missing')
    status_label = None if buyable else ('out_of_stock' if out_of_stock else 'degraded_extraction')
    return build_listing(vendor, url, source_url, timestamp, html_text, text=text, stock_status=stock_status, availability_text='Add to cart' if buyable else None, stock_evidence='hoxton_add_to_cart' if buyable else 'hoxton_page_seen', price=float((_search(r'£([\d,]+(?:\.\d{2})?)', text) or '0').replace(',','')) or None, review_reason=review_reason, status_label=status_label)


def extract_back_market(vendor, url, html_text, source_url, timestamp):
    product = extract_product_json(html_text)
    text = text_content(html_text)
    buy_signal = 'add to basket' if 'add to basket' in html_text.lower() else ('buy' if 'buy' in text.lower() else None)
    stock_status, availability_text, evidence = stock_from_html(html_text, text, product)
    review_reason = None
    status_label = None
    if stock_status == 'out_of_stock':
        review_reason = 'out_of_stock'
        status_label = 'out_of_stock'
    elif stock_status != 'in_stock' or not buy_signal:
        review_reason = 'backmarket_buy_signal_missing' if stock_status == 'in_stock' else 'stock_status_unknown'
        status_label = 'degraded_extraction'
    return build_listing(vendor, url, source_url, timestamp, html_text, text=text, stock_status=stock_status, availability_text=availability_text or buy_signal, stock_evidence='backmarket_buy_button' if buy_signal else (evidence or 'backmarket_page_seen'), price=float(product.get('offers', {}).get('price', 0) or 0) or None, review_reason=review_reason, status_label=status_label)


def extract_cex(vendor, url, html_text, source_url, timestamp):
    text = text_content(html_text)
    buyable = 'add to basket' in html_text.lower() or 'in stock online' in text.lower()
    out_of_stock = 'out of stock' in text.lower() or 'sold out' in text.lower()
    stock_status = 'in_stock' if buyable else ('out_of_stock' if out_of_stock else None)
    review_reason = None if buyable else ('out_of_stock' if out_of_stock else 'cex_stock_unknown')
    status_label = None if buyable else ('out_of_stock' if out_of_stock else 'degraded_extraction')
    return build_listing(vendor, url, source_url, timestamp, html_text, text=text, stock_status=stock_status, availability_text='In stock online' if buyable else None, stock_evidence='cex_stock_badge' if buyable else 'cex_page_seen', price=float((_search(r'£([\d,]+(?:\.\d{2})?)', text) or '0').replace(',','')) or None, review_reason=review_reason, status_label=status_label)


def extract_musicmagpie(vendor, url, html_text, source_url, timestamp):
    text = text_content(html_text)
    buyable = 'add to basket' in html_text.lower() or 'in stock' in text.lower()
    out_of_stock = 'out of stock' in text.lower() or 'sold out' in text.lower()
    stock_status = 'in_stock' if buyable else ('out_of_stock' if out_of_stock else None)
    review_reason = None if buyable else ('out_of_stock' if out_of_stock else 'musicmagpie_stock_unknown')
    status_label = None if buyable else ('out_of_stock' if out_of_stock else 'degraded_extraction')
    return build_listing(vendor, url, source_url, timestamp, html_text, text=text, stock_status=stock_status, availability_text='In stock' if buyable else None, stock_evidence='musicmagpie_buy_button' if buyable else 'musicmagpie_page_seen', price=float((_search(r'£([\d,]+(?:\.\d{2})?)', text) or '0').replace(',','')) or None, review_reason=review_reason, status_label=status_label)


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
