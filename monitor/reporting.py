from __future__ import annotations

from pathlib import Path

from monitor.models import Listing, MonitorResult
from monitor.utils import dump_csv, dump_json, dump_xlsx, ensure_dir, slugify

FIELDS = [
    "timestamp", "vendor", "title", "chip", "ram_gb", "ssd_gb", "screen_size_in", "condition", "stock_status",
    "price_gbp", "warranty", "returns", "delivery_estimate", "keyboard_layout", "url", "seller_quality_score",
    "spec_fit_score", "value_score", "total_score", "notes", "buy_now", "rationale", "source_url", "availability_text", "stock_evidence", "review_reason",
]


def _price(value: float | None) -> str:
    return f"£{value:,.0f}" if value is not None else "—"


def _listing_rows(items: list[Listing]) -> list[dict]:
    return [{k: listing.to_dict().get(k) for k in FIELDS} for listing in items]


def write_run_outputs(base_path: Path, result: MonitorResult, summary_md: str) -> dict[str, Path]:
    rows = _listing_rows(result.shortlist)
    review_rows = _listing_rows(result.needs_review)
    json_path = base_path.with_suffix(".json")
    csv_path = base_path.with_suffix(".csv")
    xlsx_path = base_path.with_suffix(".xlsx")
    md_path = base_path.with_suffix(".md")
    payload = {
        "generated_at": result.generated_at,
        "mode": result.mode,
        "used_test_mode": result.used_test_mode,
        "shortlist": [l.to_dict() for l in result.shortlist],
        "needs_review": [l.to_dict() for l in result.needs_review],
        "vendor_errors": result.vendor_errors,
    }
    dump_json(json_path, payload)
    dump_csv(csv_path, rows + review_rows)
    dump_xlsx(xlsx_path, rows + review_rows)
    md_path.write_text(summary_md, encoding="utf-8")
    return {"json": json_path, "csv": csv_path, "xlsx": xlsx_path, "md": md_path}


def build_full_summary(result: MonitorResult) -> str:
    lines = ["# Refurbished 14-inch MacBook Pro monitor summary\n", f"Generated: {result.generated_at}\n"]
    if result.used_test_mode:
        lines.append("**Test mode:** fixture-backed run for local validation only.\n")
    if not result.shortlist:
        lines.append("## Recommendation: **WAIT THIS WEEK**\n\nNo fully-qualified live listings passed the shortlist rules.\n")
    else:
        top = result.shortlist[0]
        decision = "BUY NOW" if top.buy_now else "WAIT THIS WEEK"
        lines.append(f"## Recommendation: **{decision}**\n")
        lines.append(f"\nTop qualified listing: [{top.title}]({top.url}) from **{top.vendor}** at **{_price(top.price_gbp)}**. {top.rationale}.\n")
    lines.append("## Ranked shortlist\n")
    lines.append("| Rank | Vendor | Listing | Spec | Price | Score | Verdict |")
    lines.append("| --- | --- | --- | --- | ---: | ---: | --- |")
    for idx, item in enumerate(result.shortlist, start=1):
        spec = "/".join(x for x in [item.chip or "?", f"{item.ram_gb}GB" if item.ram_gb else None, f"{int(item.ssd_gb/1024)}TB" if item.ssd_gb and item.ssd_gb >= 1024 else (f"{item.ssd_gb}GB" if item.ssd_gb else None)] if x)
        lines.append(f"| {idx} | {item.vendor} | [{item.title}]({item.url}) | {spec} | {_price(item.price_gbp)} | {item.total_score:.1f} | {'buy now' if item.buy_now else 'wait'} |")
    if result.needs_review:
        lines.append("\n## Needs review\n")
        for item in result.needs_review:
            lines.append(f"- **{item.vendor}**: [{item.title}]({item.url}) — excluded from shortlist ({item.review_reason})")
    if result.vendor_errors:
        lines.append("\n## Vendor issues\n")
        for issue in result.vendor_errors:
            lines.append(f"- **{issue.get('vendor')}**: {issue.get('error')} {issue.get('url','')}")
    return "\n".join(lines) + "\n"


def build_stock_monitor_summary(result: MonitorResult, changes: list[Listing]) -> str:
    lines = ["# Stock monitor update\n", f"Generated: {result.generated_at}\n"]
    if result.used_test_mode:
        lines.append("**Test mode:** fixture-backed run for local validation only.\n")
    if not changes:
        lines.append("No newly live or materially changed watchlist listings were detected.\n")
        return "\n".join(lines)
    lines.append("## Changes\n")
    for item in changes:
        lines.append(f"- **{item.vendor}**: [{item.title}]({item.url}) — {_price(item.price_gbp)}; {item.rationale}")
    return "\n".join(lines) + "\n"


def _card(item: Listing) -> str:
    ssd = '—'
    if item.ssd_gb is not None:
        ssd = f"{int(item.ssd_gb/1024)}TB" if item.ssd_gb >= 1024 else f"{item.ssd_gb}GB"
    return (
        f"<article class='card'><h3><a href='{item.url}'>{item.title}</a></h3>"
        f"<p><strong>{item.vendor}</strong> • {_price(item.price_gbp)} • {item.chip or 'Unknown chip'} • {item.ram_gb or '?'}GB • {ssd} SSD</p>"
        f"<p>{item.rationale or ''}</p></article>"
    )


def _render_html(title: str, body: str) -> str:
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>{title}</title><style>body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:0;background:#0f172a;color:#e2e8f0;line-height:1.5}}a{{color:#93c5fd}}main{{max-width:960px;margin:0 auto;padding:16px}}.hero,.card,table{{background:#111827;border-radius:14px;padding:16px;margin:12px 0}}table{{width:100%;border-collapse:collapse;display:block;overflow:auto}}th,td{{padding:10px;border-bottom:1px solid #334155;text-align:left;white-space:nowrap}}.pill{{display:inline-block;padding:6px 10px;border-radius:999px;background:#1d4ed8}}.wait{{background:#7c2d12}}ul{{padding-left:20px}}small{{color:#94a3b8}}pre{{white-space:pre-wrap}}</style></head><body><main>{body}</main></body></html>"


def _write_root_index(docs_dir: Path) -> Path:
    root_index = docs_dir / "index.html"
    body = (
        "<section class='hero'><p class='pill'>GitHub Pages</p><h1>Refurbished MacBook Pro monitor</h1>"
        "<p>Select a report below.</p></section>"
        "<section class='card'><h2>Dashboards</h2><ul>"
        "<li><a href='Refurb-monitor-26/'>Full sweep</a></li>"
        "<li><a href='stock-monitoring/'>Stock monitor</a></li>"
        "</ul></section>"
    )
    root_index.write_text(_render_html("MacBook monitor dashboards", body), encoding="utf-8")
    return root_index


def publish_docs(docs_dir: Path, result: MonitorResult, summary_md: str, report_name: str, site_slug: str) -> dict[str, Path]:
    site_dir = docs_dir / site_slug
    ensure_dir(docs_dir)
    ensure_dir(site_dir / "history")
    ensure_dir(site_dir / "data" / "history")
    slug = slugify(f"{report_name}-{result.generated_at}")
    latest_json = site_dir / "data" / "latest.json"
    history_json = site_dir / "data" / "history" / f"{slug}.json"
    latest_html = site_dir / "index.html"
    history_html = site_dir / "history" / f"{slug}.html"
    payload = {
        "generated_at": result.generated_at,
        "mode": result.mode,
        "used_test_mode": result.used_test_mode,
        "summary_markdown": summary_md,
        "shortlist": [l.to_dict() for l in result.shortlist],
        "needs_review": [l.to_dict() for l in result.needs_review],
        "vendor_errors": result.vendor_errors,
    }
    dump_json(latest_json, payload)
    dump_json(history_json, payload)
    rows = []
    for idx, item in enumerate(result.shortlist, start=1):
        ssd = '—' if item.ssd_gb is None else (f"{int(item.ssd_gb/1024)}TB" if item.ssd_gb >= 1024 else f"{item.ssd_gb}GB")
        rows.append(f"<tr><td>{idx}</td><td>{item.vendor}</td><td><a href='{item.url}'>{item.title}</a></td><td>{item.chip or '—'}</td><td>{item.ram_gb or '—'}GB</td><td>{ssd}</td><td>{_price(item.price_gbp)}</td><td>{item.total_score:.1f}</td></tr>")
    needs_review_html = ''.join(f"<li><a href='{item.url}'>{item.vendor}: {item.title}</a> — {item.review_reason}</li>" for item in result.needs_review) or '<li>None</li>'
    vendor_issues_html = ''.join(f"<li>{issue.get('vendor')}: {issue.get('error')} {issue.get('url', '')}</li>" for issue in result.vendor_errors) or '<li>None</li>'
    archive_links = [f"<li><a href='history/{entry.name}'>{entry.stem}</a></li>" for entry in sorted((site_dir / 'history').glob('*.html'), reverse=True) if entry.name != history_html.name]
    pill_class = 'pill wait' if not result.shortlist or not result.shortlist[0].buy_now else 'pill'
    verdict = 'WAIT THIS WEEK' if not result.shortlist or not result.shortlist[0].buy_now else 'BUY NOW'
    latest_body = (
        f"<section class='hero'><p class='{pill_class}'>{verdict}</p><h1>Refurbished 14-inch MacBook Pro monitor</h1><p>Generated {result.generated_at}</p><p>{'Test mode fixtures were used for this local run.' if result.used_test_mode else 'Live production run.'}</p></section>"
        f"<section>{''.join(_card(item) for item in result.shortlist[:5]) or '<p>No shortlist items.</p>'}</section>"
        f"<section class='card'><h2>Ranked shortlist</h2><table><thead><tr><th>#</th><th>Vendor</th><th>Listing</th><th>Chip</th><th>RAM</th><th>SSD</th><th>Price</th><th>Score</th></tr></thead><tbody>{''.join(rows)}</tbody></table></section>"
        f"<section class='card'><h2>Needs review</h2><ul>{needs_review_html}</ul></section>"
        f"<section class='card'><h2>Vendor issues</h2><ul>{vendor_issues_html}</ul></section>"
        f"<section class='card'><h2>Archive</h2><ul><li><a href='history/{history_html.name}'>This run</a></li>{''.join(archive_links)}</ul><small>Machine-readable latest data: <a href='data/latest.json'>data/latest.json</a></small></section>"
    )
    history_body = f"<section class='hero'><h1>{report_name.replace('_', ' ').title()}</h1><p>{result.generated_at}</p><p><a href='../index.html'>Back to latest dashboard</a></p></section><section class='card'><pre>{summary_md}</pre></section>"
    root_index = _write_root_index(docs_dir)
    latest_html.write_text(_render_html("MacBook monitor dashboard", latest_body), encoding="utf-8")
    history_html.write_text(_render_html(report_name, history_body), encoding="utf-8")
    return {"root_index": root_index, "latest_html": latest_html, "history_html": history_html, "latest_json": latest_json, "history_json": history_json}
