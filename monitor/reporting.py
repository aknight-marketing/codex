from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urljoin

from monitor.models import Listing, MonitorResult
from monitor.utils import dump_csv, dump_json, dump_xlsx, ensure_dir, slugify

FIELDS = [
    "timestamp", "vendor", "title", "chip", "ram_gb", "ssd_gb", "screen_size_in", "condition", "stock_status",
    "price_gbp", "warranty", "returns", "delivery_estimate", "keyboard_layout", "url", "seller_quality_score",
    "spec_fit_score", "value_score", "total_score", "notes", "buy_now", "rationale", "source_url", "availability_text",
    "stock_evidence", "review_reason", "status_label",
]

SECTION_META = {
    "full-sweep": {"title": "Full sweep", "path": "full-sweep"},
    "stock-monitor": {"title": "Stock monitor", "path": "stock-monitor"},
    "live-verification": {"title": "Live verification", "path": "live-verification"},
}


def _price(value: float | None) -> str:
    return f"£{value:,.0f}" if value is not None else "—"


def _listing_rows(items: list[Listing]) -> list[dict]:
    return [{k: listing.to_dict().get(k) for k in FIELDS} for listing in items]


def result_payload(result: MonitorResult, summary_md: str) -> dict:
    return {
        "generated_at": result.generated_at,
        "mode": result.mode,
        "used_test_mode": result.used_test_mode,
        "degraded": result.degraded,
        "trust_label": result.trust_label,
        "production_readiness": result.production_readiness,
        "readiness_reasons": result.readiness_reasons,
        "summary_markdown": summary_md,
        "shortlist": [l.to_dict() for l in result.shortlist],
        "needs_review": [l.to_dict() for l in result.needs_review],
        "unavailable": [l.to_dict() for l in result.unavailable],
        "vendor_errors": result.vendor_errors,
        "vendor_status": result.vendor_status,
        "state_changes": result.state_changes,
    }


def write_run_outputs(base_path: Path, result: MonitorResult, summary_md: str) -> dict[str, Path]:
    rows = _listing_rows(result.shortlist)
    review_rows = _listing_rows(result.needs_review)
    unavailable_rows = _listing_rows(result.unavailable)
    json_path = base_path.with_suffix(".json")
    csv_path = base_path.with_suffix(".csv")
    xlsx_path = base_path.with_suffix(".xlsx")
    md_path = base_path.with_suffix(".md")
    dump_json(json_path, result_payload(result, summary_md))
    dump_csv(csv_path, rows + review_rows + unavailable_rows)
    dump_xlsx(xlsx_path, rows + review_rows + unavailable_rows)
    md_path.write_text(summary_md, encoding="utf-8")
    return {"json": json_path, "csv": csv_path, "xlsx": xlsx_path, "md": md_path}


def _readiness_banner(result: MonitorResult) -> tuple[str, str]:
    mapping = {
        "production_ready": ("Production ready", "pill"),
        "live_but_degraded": ("Live but degraded", "pill warn"),
        "not_trustworthy_for_buying": ("Not trustworthy for buying decisions", "pill danger"),
        "test_fixture_only": ("Fixture/test only", "pill danger"),
    }
    return mapping.get(result.production_readiness, (result.production_readiness.replace("_", " ").title(), "pill warn"))


def _build_common_summary_lines(result: MonitorResult, heading: str) -> list[str]:
    lines = [f"# {heading}\n", f"Generated: {result.generated_at}\n"]
    lines.append(f"Production readiness: **{result.production_readiness}**\n")
    lines.append(f"Trust label: **{result.trust_label}**\n")
    lines.append(f"Degraded: **{'yes' if result.degraded else 'no'}**\n")
    if result.readiness_reasons:
        lines.append("\n## Readiness reasons\n")
        for reason in result.readiness_reasons:
            lines.append(f"- {reason}")
    return lines


def build_full_summary(result: MonitorResult) -> str:
    lines = _build_common_summary_lines(result, "Refurbished 14-inch MacBook Pro monitor summary")
    if not result.shortlist:
        lines.append("\n## Recommendation: **WAIT THIS WEEK**\n")
        lines.append("No fully-qualified live listings passed the shortlist rules.\n")
    else:
        top = result.shortlist[0]
        decision = "BUY NOW" if top.buy_now else "WAIT THIS WEEK"
        lines.append(f"\n## Recommendation: **{decision}**\n")
        lines.append(f"Top qualified listing: [{top.title}]({top.url}) from **{top.vendor}** at **{_price(top.price_gbp)}**. {top.rationale}.\n")
    lines.append("\n## Ranked shortlist\n")
    lines.append("| Rank | Vendor | Listing | Spec | Price | Score | Verdict |")
    lines.append("| --- | --- | --- | --- | ---: | ---: | --- |")
    for idx, item in enumerate(result.shortlist, start=1):
        spec = "/".join(
            x for x in [
                item.chip or "?",
                f"{item.ram_gb}GB" if item.ram_gb else None,
                f"{int(item.ssd_gb/1024)}TB" if item.ssd_gb and item.ssd_gb >= 1024 else (f"{item.ssd_gb}GB" if item.ssd_gb else None),
            ] if x
        )
        lines.append(f"| {idx} | {item.vendor} | [{item.title}]({item.url}) | {spec} | {_price(item.price_gbp)} | {item.total_score:.1f} | {'buy now' if item.buy_now else 'wait'} |")
    if result.needs_review:
        lines.append("\n## Needs review\n")
        for item in result.needs_review:
            lines.append(f"- **{item.vendor}**: [{item.title}]({item.url}) — {item.review_reason}")
    if result.unavailable:
        lines.append("\n## Unavailable / out of stock\n")
        for item in result.unavailable:
            lines.append(f"- **{item.vendor}**: [{item.title}]({item.url}) — {item.review_reason or item.stock_status}")
    if result.vendor_errors:
        lines.append("\n## Vendor issues\n")
        for issue in result.vendor_errors:
            lines.append(f"- **{issue.get('vendor')}**: {issue.get('error')} {issue.get('url', '')}")
    return "\n".join(lines) + "\n"


def build_stock_monitor_summary(result: MonitorResult, changes: list[dict]) -> str:
    lines = _build_common_summary_lines(result, "Stock monitor update")
    if not changes:
        lines.append("\nNo newly observed, changed, or disappeared watchlist listings were detected.\n")
        return "\n".join(lines) + "\n"
    lines.append("\n## State changes\n")
    for item in changes:
        lines.append(
            f"- **{item['vendor']}**: [{item['title']}]({item['url']}) — {item['change_type']} "
            f"({item.get('previous_status_label') or 'none'} → {item.get('current_status_label') or 'none'}; "
            f"{item.get('previous_stock_status') or 'none'} → {item.get('current_stock_status') or 'none'}). "
            f"{item.get('reason') or ''}"
        )
    return "\n".join(lines) + "\n"


def build_live_verification_summary(result: MonitorResult, public_site_url: str) -> str:
    lines = _build_common_summary_lines(result, "Live production verification")
    lines.append(f"\nPublic site base: {public_site_url}\n")
    lines.append("\n## Core vendor health\n")
    lines.append("| Vendor | Status | Candidates | Observed | Actionable | Needs review | Unavailable | Errors |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for status in result.vendor_status:
        lines.append(
            f"| {status['vendor']} | {status['status']} | {status['candidates_found']} | {status['observed_listings']} | "
            f"{status['actionable']} | {status['needs_review']} | {status['unavailable']} | {status['errors']} |"
        )
    if result.vendor_errors:
        lines.append("\n## Vendor errors\n")
        for issue in result.vendor_errors:
            lines.append(f"- **{issue.get('vendor')}**: {issue.get('error')} {issue.get('url', '')}")
    return "\n".join(lines) + "\n"


def _card(item: Listing) -> str:
    ssd = "—"
    if item.ssd_gb is not None:
        ssd = f"{int(item.ssd_gb/1024)}TB" if item.ssd_gb >= 1024 else f"{item.ssd_gb}GB"
    return (
        f"<article class='card'><h3><a href='{item.url}'>{item.title}</a></h3>"
        f"<p><strong>{item.vendor}</strong> • {_price(item.price_gbp)} • {item.chip or 'Unknown chip'} • {item.ram_gb or '?'}GB • {ssd} SSD</p>"
        f"<p>Status: {item.status_label or 'unknown'}{f' — {item.review_reason}' if item.review_reason else ''}</p>"
        f"<p>{item.rationale or ''}</p></article>"
    )


def _render_html(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{title}</title><style>"
        "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:0;background:#0f172a;color:#e2e8f0;line-height:1.5}"
        "a{color:#93c5fd} main{max-width:1100px;margin:0 auto;padding:16px} .hero,.card,table{background:#111827;border-radius:14px;padding:16px;margin:12px 0}"
        "table{width:100%;border-collapse:collapse;display:block;overflow:auto} th,td{padding:10px;border-bottom:1px solid #334155;text-align:left;white-space:nowrap}"
        ".pill{display:inline-block;padding:6px 10px;border-radius:999px;background:#1d4ed8}.warn{background:#92400e}.danger{background:#7f1d1d}"
        ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px} ul{padding-left:20px} small{color:#94a3b8} pre{white-space:pre-wrap}"
        "</style></head><body><main>"
        f"{body}</main></body></html>"
    )


def _site_href(public_site_url: str | None, relative_path: str) -> str:
    if not public_site_url:
        return relative_path
    base = public_site_url if public_site_url.endswith("/") else f"{public_site_url}/"
    return urljoin(base, relative_path)


def _section_paths(docs_dir: Path, section_slug: str) -> dict[str, Path]:
    section_dir = docs_dir / section_slug
    ensure_dir(section_dir / "history")
    ensure_dir(section_dir / "data" / "history")
    return {
        "section_dir": section_dir,
        "latest_html": section_dir / "index.html",
        "latest_json": section_dir / "data" / "latest.json",
        "history_dir": section_dir / "history",
        "history_data_dir": section_dir / "data" / "history",
    }


def _render_section_index(
    result: MonitorResult,
    summary_md: str,
    section_slug: str,
    public_site_url: str | None = None,
    latest_json_path: str | None = None,
    history_path: str | None = None,
) -> str:
    badge, badge_class = _readiness_banner(result)
    rows = []
    for idx, item in enumerate(result.shortlist, start=1):
        ssd = "—" if item.ssd_gb is None else (f"{int(item.ssd_gb/1024)}TB" if item.ssd_gb >= 1024 else f"{item.ssd_gb}GB")
        rows.append(
            f"<tr><td>{idx}</td><td>{item.vendor}</td><td><a href='{item.url}'>{item.title}</a></td><td>{item.chip or '—'}</td>"
            f"<td>{item.ram_gb or '—'}GB</td><td>{ssd}</td><td>{_price(item.price_gbp)}</td><td>{item.total_score:.1f}</td></tr>"
        )
    needs_review_html = "".join(
        f"<li><a href='{item.url}'>{item.vendor}: {item.title}</a> — {item.review_reason}</li>" for item in result.needs_review
    ) or "<li>None</li>"
    unavailable_html = "".join(
        f"<li><a href='{item.url}'>{item.vendor}: {item.title}</a> — {item.review_reason or item.stock_status}</li>" for item in result.unavailable
    ) or "<li>None</li>"
    vendor_status_html = "".join(
        f"<li>{status['vendor']}: {status['status']} (candidates={status['candidates_found']}, observed={status['observed_listings']}, errors={status['errors']})</li>"
        for status in result.vendor_status
    ) or "<li>None</li>"
    state_changes_html = "".join(
        f"<li>{item['vendor']}: <a href='{item['url']}'>{item['title']}</a> — {item['change_type']} ({item.get('previous_status_label') or 'none'} → {item.get('current_status_label') or 'none'})</li>"
        for item in result.state_changes
    ) or "<li>None</li>"
    external_hint = f"<p>Public site base: <a href='{public_site_url}'>{public_site_url}</a></p>" if public_site_url else ""
    nav_links = [
        f"<a href='{_site_href(public_site_url, '')}'>Project root</a>",
    ]
    if latest_json_path:
        nav_links.append(f"<a href='{_site_href(public_site_url, latest_json_path)}'>Latest JSON</a>")
    if history_path:
        nav_links.append(f"<a href='{_site_href(public_site_url, history_path)}'>Latest history snapshot</a>")
    return (
        f"<section class='hero'><p class='{badge_class}'>{badge}</p><h1>{SECTION_META[section_slug]['title']}</h1>"
        f"<p>Generated {result.generated_at}</p><p>Trust label: <strong>{result.trust_label}</strong></p>{external_hint}</section>"
        f"<section class='card'><h2>Links</h2><p>{' • '.join(nav_links)}</p></section>"
        f"<section class='grid'><article class='card'><h2>Readiness reasons</h2><ul>{''.join(f'<li>{reason}</li>' for reason in result.readiness_reasons) or '<li>None</li>'}</ul></article>"
        f"<article class='card'><h2>Counts</h2><ul><li>Actionable: {len(result.shortlist)}</li><li>Needs review: {len(result.needs_review)}</li><li>Unavailable: {len(result.unavailable)}</li><li>Vendor errors: {len(result.vendor_errors)}</li></ul></article></section>"
        f"<section>{''.join(_card(item) for item in result.shortlist[:5]) or '<p>No actionable shortlist items.</p>'}</section>"
        f"<section class='card'><h2>Ranked shortlist</h2><table><thead><tr><th>#</th><th>Vendor</th><th>Listing</th><th>Chip</th><th>RAM</th><th>SSD</th><th>Price</th><th>Score</th></tr></thead><tbody>{''.join(rows)}</tbody></table></section>"
        f"<section class='card'><h2>Needs review</h2><ul>{needs_review_html}</ul></section>"
        f"<section class='card'><h2>Unavailable / out of stock</h2><ul>{unavailable_html}</ul></section>"
        f"<section class='card'><h2>Vendor health</h2><ul>{vendor_status_html}</ul></section>"
        f"<section class='card'><h2>State changes</h2><ul>{state_changes_html}</ul></section>"
        f"<section class='card'><h2>Raw summary markdown</h2><pre>{summary_md}</pre></section>"
    )


def _build_root_manifest(docs_dir: Path) -> dict:
    sections = {}
    for slug in SECTION_META:
        latest_json = docs_dir / slug / "data" / "latest.json"
        if not latest_json.exists():
            continue
        payload = json.loads(latest_json.read_text(encoding="utf-8"))
        history_dir = docs_dir / slug / "history"
        latest_history = sorted(history_dir.glob("*.html"))[-1] if history_dir.exists() and any(history_dir.glob("*.html")) else None
        sections[slug] = {
            "title": SECTION_META[slug]["title"],
            "path": f"{slug}/",
            "latest_json": f"{slug}/data/latest.json",
            "latest_history": f"{slug}/history/{latest_history.name}" if latest_history else None,
            "payload": payload,
        }
    return {
        "sections": sections,
    }


def _write_root_index(docs_dir: Path, public_site_url: str | None = None) -> dict[str, Path]:
    manifest = _build_root_manifest(docs_dir)
    root_json = docs_dir / "data" / "latest.json"
    ensure_dir(root_json.parent)
    dump_json(root_json, manifest)
    cards = []
    for slug, section in manifest["sections"].items():
        payload = section["payload"] or {}
        history_link = ""
        if section.get("latest_history"):
            history_link = f" • <a href='{_site_href(public_site_url, section['latest_history'])}'>Latest history</a>"
        cards.append(
            "<article class='card'>"
            f"<h2><a href='{_site_href(public_site_url, section['path'])}'>{section['title']}</a></h2>"
            f"<p>Readiness: <strong>{payload.get('production_readiness', 'not yet generated')}</strong></p>"
            f"<p>Trust label: <strong>{payload.get('trust_label', 'unknown')}</strong></p>"
            f"<p>Generated: {payload.get('generated_at', '—')}</p>"
            f"<p><a href='{_site_href(public_site_url, section['latest_json'])}'>Latest JSON</a>{history_link}</p>"
            "</article>"
        )
    if not cards:
        cards.append("<article class='card'><h2>No published sections yet</h2><p>Run the full sweep or stock monitor workflow to publish a section.</p></article>")
    body = (
        "<section class='hero'><h1>MacBook monitor reports</h1><p>Static Pages index for the current reporting surfaces.</p></section>"
        f"<section class='grid'>{''.join(cards)}</section>"
    )
    root_html = docs_dir / "index.html"
    root_html.write_text(_render_html("MacBook monitor reports", body), encoding="utf-8")
    return {"root_html": root_html, "root_json": root_json}


def publish_docs(
    docs_dir: Path,
    result: MonitorResult,
    summary_md: str,
    report_name: str,
    section_slug: str,
    public_site_url: str | None = None,
    update_root_index: bool = True,
) -> dict[str, Path]:
    ensure_dir(docs_dir)
    paths = _section_paths(docs_dir, section_slug)
    slug = slugify(f"{report_name}-{result.generated_at}")
    payload = result_payload(result, summary_md)
    latest_html = paths["latest_html"]
    history_html = paths["history_dir"] / f"{slug}.html"
    latest_json = paths["latest_json"]
    history_json = paths["history_data_dir"] / f"{slug}.json"
    dump_json(latest_json, payload)
    dump_json(history_json, payload)
    latest_json_path = f"{section_slug}/data/latest.json"
    history_path = f"{section_slug}/history/{history_html.name}"
    latest_html.write_text(
        _render_html(
            SECTION_META[section_slug]["title"],
            _render_section_index(result, summary_md, section_slug, public_site_url, latest_json_path, history_path),
        ),
        encoding="utf-8",
    )
    history_html.write_text(
        _render_html(
            f"{SECTION_META[section_slug]['title']} history",
            f"<section class='hero'><h1>{SECTION_META[section_slug]['title']} history snapshot</h1><p>{result.generated_at}</p><p><a href='../index.html'>Back to latest section report</a></p></section><section class='card'><pre>{summary_md}</pre></section>",
        ),
        encoding="utf-8",
    )
    published = {
        "latest_html": latest_html,
        "history_html": history_html,
        "latest_json": latest_json,
        "history_json": history_json,
    }
    if update_root_index:
        published.update(_write_root_index(docs_dir, public_site_url))
    return published
