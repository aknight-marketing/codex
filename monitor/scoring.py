from __future__ import annotations

from monitor.models import Listing

TARGET_PRICE = {
    ("M3 MAX", 48, 1024): 2500,
    ("M3 MAX", 64, 1024): 2800,
    ("M3 MAX", 36, 1024): 2250,
    ("M2 MAX", 32, 1024): 1850,
    ("M4 PRO", 24, 1024): 1850,
    ("M3 PRO", 18, 512): 1200,
    ("M4", 24, 512): 1400,
}


def spec_fit_score(listing: Listing) -> float:
    score = 0.0
    chip = (listing.chip or "").upper()
    ram = listing.ram_gb or 0
    ssd = listing.ssd_gb or 0
    size = listing.screen_size_in or 0
    if 13.8 <= size <= 14.3:
        score += 18
    elif size:
        score -= 40
    if chip == "M3 MAX":
        score += 46
        score += 30 if ram in {48, 64} else 22 if ram == 36 else 12 if ram >= 32 else 0
    elif chip == "M2 MAX":
        score += 32
        score += 16 if ram >= 32 else 0
    elif chip == "M4 PRO":
        score += 24
        score += 10 if ram >= 24 else 0
    elif chip == "M3 PRO":
        score += 16
        score += 4 if ram >= 18 else 0
    if ssd >= 1024:
        score += 18
    elif ssd >= 512:
        score += 8
    return max(score, 0)


def value_score(listing: Listing) -> float:
    chip = (listing.chip or "").upper()
    ram = listing.ram_gb or 0
    ssd = listing.ssd_gb or 0
    price = listing.price_gbp
    if price is None:
        return -20
    target = TARGET_PRICE.get((chip, ram, ssd), 1500)
    delta = target - price
    if delta >= 300:
        return 30
    if delta >= 100:
        return 22
    if delta >= 0:
        return 16
    if delta >= -150:
        return 6
    if delta >= -300:
        return -8
    return -20


def score_listing(listing: Listing, vendor_quality: float) -> Listing:
    listing.seller_quality_score = vendor_quality
    listing.spec_fit_score = spec_fit_score(listing)
    listing.value_score = value_score(listing)
    listing.total_score = round((vendor_quality * 0.6) + listing.spec_fit_score + listing.value_score, 2)
    listing.buy_now = bool(listing.spec_fit_score >= 80 and listing.value_score >= 22 and vendor_quality >= 16)
    reasons = [x for x in [listing.chip, f"{listing.ram_gb}GB RAM" if listing.ram_gb else None, f"{int(listing.ssd_gb/1024)}TB SSD" if listing.ssd_gb and listing.ssd_gb >= 1024 else (f"{listing.ssd_gb}GB SSD" if listing.ssd_gb else None), f"£{listing.price_gbp:,.0f}" if listing.price_gbp else None] if x]
    reasons.append("excellent fit and price" if listing.buy_now else ("strong fallback" if listing.total_score >= 70 else "wait for a better-priced higher-spec listing"))
    listing.rationale = ", ".join(reasons)
    return listing
