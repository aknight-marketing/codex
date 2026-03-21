from __future__ import annotations

from pathlib import Path

from monitor.models import Listing
from monitor.utils import dump_csv, dump_json, dump_xlsx

FIELDS = [
    "timestamp", "vendor", "title", "chip", "ram_gb", "ssd_gb", "screen_size_in", "condition", "stock_status",
    "price_gbp", "warranty", "returns", "delivery_estimate", "keyboard_layout", "url", "seller_quality_score",
    "spec_fit_score", "value_score", "total_score", "notes", "buy_now", "rationale", "source_url", "availability_text",
]


def _price(value: float | None) -> str:
    return f"£{value:,.0f}" if value is not None else "—"


def write_outputs(base_path: Path, listings: list[Listing], summary_md: str) -> dict[str, Path]:
    rows = []
    for listing in listings:
        row = listing.to_dict()
        rows.append({k: row.get(k) for k in FIELDS})
    json_path = base_path.with_suffix(".json")
    csv_path = base_path.with_suffix(".csv")
    xlsx_path = base_path.with_suffix(".xlsx")
    md_path = base_path.with_suffix(".md")
    dump_json(json_path, [l.to_dict() for l in listings])
    dump_csv(csv_path, rows)
    dump_xlsx(xlsx_path, rows)
    md_path.write_text(summary_md, encoding="utf-8")
    return {"json": json_path, "csv": csv_path, "xlsx": xlsx_path, "md": md_path}


def build_full_summary(listings: list[Listing], generated_at: str) -> str:
    lines = ["# Refurbished 14-inch MacBook Pro monitor summary\n", f"Generated: {generated_at}\n"]
    if not listings:
        lines.append("No live buyable listings were validated across the configured vendors. Recommendation: **wait this week**.\n")
        return "\n".join(lines)
    top = listings[0]
    if top.buy_now:
        lines.append(f"## Recommendation: **BUY NOW**\n\nTop pick: [{top.title}]({top.url}) from **{top.vendor}** at **{_price(top.price_gbp)}**. {top.rationale}.\n")
    else:
        lines.append("## Recommendation: **WAIT THIS WEEK**\n\nNo listing cleared the no-brainer buy-now threshold. The current best options are useful fallbacks, but pricing/spec fit is not yet exceptional enough.\n")
        lines.append(f"Best current fallback: [{top.title}]({top.url}) from **{top.vendor}** at **{_price(top.price_gbp)}**. {top.rationale}.\n")
    lines.append("## Ranked live listings\n")
    lines.append("| Rank | Vendor | Listing | Spec | Price | Score | Buy now | Notes |")
    lines.append("| --- | --- | --- | --- | ---: | ---: | --- | --- |")
    for idx, item in enumerate(listings, start=1):
        spec = "/".join(x for x in [item.chip or "?", f"{item.ram_gb}GB" if item.ram_gb else None, f"{int(item.ssd_gb/1024)}TB" if item.ssd_gb and item.ssd_gb >= 1024 else (f"{item.ssd_gb}GB" if item.ssd_gb else None)] if x)
        lines.append(f"| {idx} | {item.vendor} | [{item.title}]({item.url}) | {spec} | {_price(item.price_gbp)} | {item.total_score:.1f} | {'yes' if item.buy_now else 'no'} | {item.rationale or ''} |")
    return "\n".join(lines) + "\n"


def build_stock_monitor_summary(changes: list[Listing], generated_at: str) -> str:
    lines = [f"# Stock monitor update\n\nGenerated: {generated_at}\n"]
    if not changes:
        lines.append("No newly live or materially changed watchlist listings were detected.\n")
        return "\n".join(lines)
    lines.append("## Changes\n")
    for item in changes:
        lines.append(f"- **{item.vendor}**: [{item.title}]({item.url}) — {_price(item.price_gbp)}; {item.rationale}")
    return "\n".join(lines) + "\n"
