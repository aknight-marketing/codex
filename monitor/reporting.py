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
        "run_mode_label": result.run_mode_label,
        "used_test_mode": result.used_test_mode,
        "fixture_fallback_used": result.fixture_fallback_used,
        "browser_mode": result.browser_mode,
        "trust_label": result.trust_label,
        "production_readiness": result.production_readiness,
        "degraded": result.degraded,
        "live_verification_blocked": result.live_verification_blocked,
        "run_health": result.run_health,
        "quality_checks": result.quality_checks,
        "vendor_stats": result.vendor_stats,
        "shortlist": [l.to_dict() for l in result.shortlist],
        "needs_review": [l.to_dict() for l in result.needs_review],
        "vendor_errors": result.vendor_errors,
    }
    dump_json(json_path, payload)
    dump_csv(csv_path, rows + review_rows)
    dump_xlsx(xlsx_path, rows + review_rows)
    md_path.write_text(summary_md, encoding="utf-8")
    return {"json": json_path, "csv": csv_path, "xlsx": xlsx_path, "md": md_path}


def _run_health_lines(result: MonitorResult) -> list[str]:
    health = result.run_health
    return [
        f"- Run mode: **{result.run_mode_label}**",
        f"- Trust label: **{result.trust_label}**",
        f"- Production readiness: **{result.production_readiness}**",
        f"- Degraded: **{result.degraded}**",
        f"- Fixture fallback used: **{result.fixture_fallback_used}**",
        f"- Fetch backend: **{result.browser_mode}**",
        f"- Vendors checked: **{health['vendors_checked_count']}**",
        f"- Vendors with direct candidates: **{health['vendors_with_direct_candidates_count']}**",
        f"- Vendors successfully parsed: **{health['vendors_successfully_parsed_count']}**",
        f"- Vendors with live actionable listings: **{health['vendors_with_live_actionable_listings_count']}**",
        f"- Parser errors: **{health['parser_errors_count']}**",
        f"- Blocked vendors: **{health['blocked_vendors_count']}**",
        f"- Excluded listings: **{health['excluded_listings_count']}**",
        f"- Needs review: **{health['needs_review_count']}**",
    ]


def build_full_summary(result: MonitorResult) -> str:
    lines = ["# Refurbished 14-inch MacBook Pro monitor summary\n", f"Generated: {result.generated_at}\n"]
    lines.append("## Run health\n")
    lines.extend(_run_health_lines(result))
    lines.append("")
    for check in result.quality_checks:
        lines.append(f"- {'PASS' if check['passed'] else 'FAIL'} — **{check['name']}**: {check['detail']}")
    lines.append("")
    if not result.shortlist:
        lines.append("## Recommendation: **WAIT THIS WEEK**\n\nNo fully-qualified live listings passed the shortlist rules.\n")
    else:
        top = result.shortlist[0]
        decision = "BUY NOW" if result.can_recommend_buy_now else "WAIT THIS WEEK"
        lines.append(f"## Recommendation: **{decision}**\n")
        lines.append(f"\nTop qualified listing: [{top.title}]({top.url}) from **{top.vendor}** at **{_price(top.price_gbp)}**. {top.rationale}.\n")
    lines.append("## Ranked shortlist\n")
    lines.append("| Rank | Vendor | Listing | Spec | Price | Score | Verdict |")
    lines.append("| --- | --- | --- | --- | ---: | ---: | --- |")
    for idx, item in enumerate(result.shortlist, start=1):
        spec = "/".join(x for x in [item.chip or "?", f"{item.ram_gb}GB" if item.ram_gb else None, f"{int(item.ssd_gb/1024)}TB" if item.ssd_gb and item.ssd_gb >= 1024 else (f"{item.ssd_gb}GB" if item.ssd_gb else None)] if x)
        verdict = "buy now" if result.can_recommend_buy_now and idx == 1 else "wait"
        lines.append(f"| {idx} | {item.vendor} | [{item.title}]({item.url}) | {spec} | {_price(item.price_gbp)} | {item.total_score:.1f} | {verdict} |")
    if result.needs_review:
        lines.append("\n## Needs review\n")
        for item in result.needs_review:
            lines.append(f"- **{item.vendor}**: [{item.title}]({item.url}) — excluded from shortlist ({item.review_reason})")
    if result.vendor_stats:
        lines.append("\n## Vendor coverage\n")
        lines.append("| Vendor | Discovery | Candidates | Parsed | Actionable | Blocked | Last error |")
        lines.append("| --- | --- | ---: | ---: | ---: | --- | --- |")
        for stat in result.vendor_stats:
            lines.append(f"| {stat['vendor']} | {stat['discovery_status']} | {stat['candidate_count']} | {stat['parser_success_count']} | {stat['actionable_count']} | {stat['blocked']} | {stat.get('last_error') or '—'} |")
    if result.vendor_errors:
        lines.append("\n## Vendor issues\n")
        for issue in result.vendor_errors:
            lines.append(f"- **{issue.get('vendor')}**: {issue.get('error')} {issue.get('url', '')}")
    return "\n".join(lines) + "\n"


def build_stock_monitor_summary(result: MonitorResult, changes: list[Listing]) -> str:
    lines = ["# Stock monitor update\n", f"Generated: {result.generated_at}\n", "## Run health\n"]
    lines.extend(_run_health_lines(result))
    lines.append("")
    for check in result.quality_checks:
        lines.append(f"- {'PASS' if check['passed'] else 'FAIL'} — **{check['name']}**: {check['detail']}")
    lines.append("")
    if not changes:
        lines.append("No newly live or materially changed watchlist listings were detected.\n")
        return "\n".join(lines)
    lines.append("## Changes\n")
    for item in changes:
        lines.append(f"- **{item.vendor}**: [{item.title}]({item.url}) — {_price(item.price_gbp)}; {item.rationale}")
    return "\n".join(lines) + "\n"


def build_live_verification_summary(result: MonitorResult, public_site_url: str) -> str:
    lines = ["# Production live verification summary\n", f"Generated: {result.generated_at}\n"]
    lines.extend(_run_health_lines(result))
    lines.append("")
    lines.append(f"- Public Pages base: **{public_site_url}**")
    lines.append("")
    lines.append(f"## Live verification verdict: **{result.production_readiness}**\n")
    if result.live_verification_blocked:
        lines.append("This environment still shows blocked/denied vendor access during live verification.\n")
    elif result.run_health['vendors_successfully_parsed_count'] == 0:
        lines.append("Fetches completed but no vendors produced parsed listings.\n")
    else:
        lines.append("At least some vendors were fetched and parsed successfully in live mode.\n")
    lines.append("\n## Vendor-by-vendor status\n")
    lines.append("| Vendor | Discovery | Candidates | Parsed | Actionable | Failure type | Last error |")
    lines.append("| --- | --- | ---: | ---: | ---: | --- | --- |")
    for stat in result.vendor_stats:
        failure_type = stat['discovery_issues'][-1]['classification'] if stat.get('discovery_issues') else ('parser_failure' if stat.get('parser_failure_count') else '—')
        lines.append(f"| {stat['vendor']} | {stat['discovery_status']} | {stat['candidate_count']} | {stat['parser_success_count']} | {stat['actionable_count']} | {failure_type} | {stat.get('last_error') or '—'} |")
    return "\n".join(lines) + "\n"


def _card(item: Listing) -> str:
    ssd = '—'
    if item.ssd_gb is not None:
        ssd = f"{int(item.ssd_gb/1024)}TB" if item.ssd_gb >= 1024 else f"{item.ssd_gb}GB"
    return (
        f"<article class='card'><div class='card-head'><span class='pill wait'>WAIT THIS WEEK</span><span class='muted'>{item.vendor}</span></div>"
        f"<h3><a href='{item.url}'>{item.title}</a></h3>"
        f"<p><strong>{_price(item.price_gbp)}</strong> • {item.chip or 'Unknown chip'} • {item.ram_gb or '?'}GB • {ssd} SSD • {item.stock_status or 'unknown'}</p>"
        f"<p>{item.rationale or ''}</p></article>"
    )


def _render_html(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{title}</title>"
        "<style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:0;background:#0f172a;color:#e2e8f0;line-height:1.5}"
        "a{color:#93c5fd}main{max-width:1100px;margin:0 auto;padding:16px}.hero,.card,table,.banner,.nav{background:#111827;border-radius:14px;padding:16px;margin:12px 0}"
        ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}table{width:100%;border-collapse:collapse;display:block;overflow:auto}"
        "th,td{padding:10px;border-bottom:1px solid #334155;text-align:left;white-space:nowrap;vertical-align:top}.pill{display:inline-block;padding:6px 10px;border-radius:999px;background:#1d4ed8;font-size:.85rem}"
        ".pill.wait{background:#7c2d12}.pill.buy{background:#166534}.pill.info{background:#1d4ed8}.pill.warn{background:#b45309}ul{padding-left:20px}small,.muted{color:#94a3b8}pre{white-space:pre-wrap}.card-head{display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap}"
        ".banner.fail{border:1px solid #b91c1c}.banner.pass{border:1px solid #166534}.nav a{margin-right:16px}.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px}.kv div{background:#0b1220;border-radius:10px;padding:10px}@media (max-width:720px){main{padding:12px}th,td{font-size:.92rem;padding:8px}}</style></head><body><main>"
        f"{body}</main></body></html>"
    )


def _write_root_index(docs_dir: Path, public_site_url: str) -> Path:
    root_index = docs_dir / "index.html"
    links = ["<a href='full-sweep/'>Latest full sweep</a>", "<a href='stock-monitor/'>Latest stock monitor</a>"]
    if (docs_dir / 'live-verification' / 'index.html').exists():
        links.append("<a href='live-verification/'>Live verification probe</a>")
    body = (
        "<section class='hero'><p class='pill info'>GitHub Pages</p><h1>Refurbished MacBook Pro monitor</h1>"
        f"<p>Project site root: <a href='{public_site_url}'>{public_site_url}</a></p></section>"
        f"<section class='nav'>{''.join(links)}</section>"
    )
    root_index.write_text(_render_html("MacBook monitor dashboards", body), encoding="utf-8")
    return root_index


def _health_cards(result: MonitorResult) -> str:
    health = result.run_health
    rows = [
        ("Run mode", result.run_mode_label),
        ("Trust label", result.trust_label),
        ("Production readiness", result.production_readiness),
        ("Degraded", str(result.degraded)),
        ("Fixture fallback", str(result.fixture_fallback_used)),
        ("Fetch backend", result.browser_mode),
        ("Vendors checked", str(health['vendors_checked_count'])),
        ("Direct candidates", str(health['vendors_with_direct_candidates_count'])),
        ("Parsed vendors", str(health['vendors_successfully_parsed_count'])),
        ("Actionable vendors", str(health['vendors_with_live_actionable_listings_count'])),
        ("Parser errors", str(health['parser_errors_count'])),
        ("Blocked vendors", str(health['blocked_vendors_count'])),
        ("Excluded listings", str(health['excluded_listings_count'])),
        ("Needs review", str(health['needs_review_count'])),
    ]
    return ''.join(f"<div><small>{label}</small><br><strong>{value}</strong></div>" for label, value in rows)


def write_placeholder_site(docs_dir: Path, site_slug: str, title: str, message: str, public_site_url: str) -> Path:
    site_dir = docs_dir / site_slug
    ensure_dir(site_dir)
    body = (
        f"<section class='hero'><p class='pill warn'>{title}</p><h1>{title}</h1><p>{message}</p>"
        f"<p>Project site base: <a href='{public_site_url}'>{public_site_url}</a></p></section>"
        "<section class='nav'><a href='../index.html'>Home</a><a href='../live-verification/'>Live verification probe</a></section>"
    )
    index = site_dir / 'index.html'
    index.write_text(_render_html(title, body), encoding='utf-8')
    return index


def publish_docs(docs_dir: Path, result: MonitorResult, summary_md: str, report_name: str, site_slug: str, public_site_url: str) -> dict[str, Path]:
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
        "run_mode_label": result.run_mode_label,
        "used_test_mode": result.used_test_mode,
        "fixture_fallback_used": result.fixture_fallback_used,
        "browser_mode": result.browser_mode,
        "trust_label": result.trust_label,
        "production_readiness": result.production_readiness,
        "degraded": result.degraded,
        "live_verification_blocked": result.live_verification_blocked,
        "run_health": result.run_health,
        "quality_checks": result.quality_checks,
        "vendor_stats": result.vendor_stats,
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
        verdict = 'BUY NOW' if result.can_recommend_buy_now and idx == 1 else 'WAIT'
        rows.append(f"<tr><td>{idx}</td><td>{item.vendor}</td><td><a href='{item.url}'>{item.title}</a><br><small>{item.rationale or ''}</small></td><td>{item.chip or '—'}</td><td>{item.ram_gb or '—'}GB</td><td>{ssd}</td><td>{_price(item.price_gbp)}</td><td>{item.stock_status or '—'}</td><td>{verdict}</td><td>{item.total_score:.1f}</td></tr>")
    needs_review_html = ''.join(f"<li><a href='{item.url}'>{item.vendor}: {item.title}</a> — {item.review_reason}</li>" for item in result.needs_review) or '<li>None</li>'
    vendor_issues_html = ''.join(f"<li>{issue.get('vendor')}: {issue.get('error')} {issue.get('url', '')}</li>" for issue in result.vendor_errors) or '<li>None</li>'
    check_html = ''.join(f"<li>{'PASS' if check['passed'] else 'FAIL'} — <strong>{check['name']}</strong>: {check['detail']}</li>" for check in result.quality_checks) or '<li>No checks recorded</li>'
    vendor_stats_rows = ''.join(
        f"<tr><td>{stat['vendor']}</td><td>{stat['discovery_status']}</td><td>{stat['candidate_count']}</td><td>{stat['parser_success_count']}</td><td>{stat['parser_failure_count']}</td><td>{stat['actionable_count']}</td><td>{stat['stock_validation_success_count']}</td><td>{stat['blocked']}</td><td>{stat.get('last_error') or '—'}</td></tr>"
        for stat in result.vendor_stats
    ) or "<tr><td colspan='9'>No vendor stats</td></tr>"
    archive_links = ''.join(f"<li><a href='history/{entry.name}'>{entry.stem}</a></li>" for entry in sorted((site_dir / 'history').glob('*.html'), reverse=True)) or '<li>No history yet</li>'
    verdict = 'BUY NOW' if result.can_recommend_buy_now else 'WAIT THIS WEEK'
    pill_class = 'pill buy' if result.can_recommend_buy_now else 'pill wait'
    trust_pill = 'info' if result.trust_label == 'Production-ready' else ('warn' if result.trust_label == 'Live but degraded' else 'wait')
    health_class = 'banner fail' if result.degraded else 'banner pass'
    health_text = 'This run is degraded or non-production. Do not treat it as a clean live buying signal.' if result.degraded or result.fixture_fallback_used else 'This run passed the built-in live quality gates.'
    latest_body = (
        f"<section class='nav'><a href='../index.html'>Home</a><a href='./'>Latest {report_name.replace('_', ' ')}</a><a href='history/{history_html.name}'>Archive snapshot</a><a href='data/latest.json'>JSON</a></section>"
        f"<section class='hero'><p class='{pill_class}'>{verdict}</p><h1>Refurbished 14-inch MacBook Pro monitor</h1><p>Generated {result.generated_at}</p><p><span class='pill {trust_pill}'>{result.trust_label}</span></p><p>Production readiness: {result.production_readiness}.</p><p>Run mode: {result.run_mode_label}. Fixture fallback used: {result.fixture_fallback_used}. Browser backend: {result.browser_mode}.</p><p>Expected GitHub Pages base: <a href='{public_site_url}'>{public_site_url}</a></p></section>"
        f"<section class='{health_class}'><h2>Run health</h2><p>{health_text}</p><div class='kv'>{_health_cards(result)}</div><ul>{check_html}</ul></section>"
        f"<section class='grid'>{''.join(_card(item) for item in result.shortlist[:6]) or '<p>No shortlist items.</p>'}</section>"
        f"<section class='card'><h2>Ranked shortlist</h2><table><thead><tr><th>#</th><th>Vendor</th><th>Listing</th><th>Chip</th><th>RAM</th><th>SSD</th><th>Price</th><th>Stock</th><th>Verdict</th><th>Score</th></tr></thead><tbody>{''.join(rows)}</tbody></table></section>"
        f"<section class='card'><h2>Needs review</h2><ul>{needs_review_html}</ul></section>"
        f"<section class='card'><h2>Vendor coverage</h2><table><thead><tr><th>Vendor</th><th>Discovery</th><th>Candidates</th><th>Parsed</th><th>Parser failed</th><th>Actionable</th><th>Stock validated</th><th>Blocked</th><th>Last error</th></tr></thead><tbody>{vendor_stats_rows}</tbody></table></section>"
        f"<section class='card'><h2>Vendor issues</h2><ul>{vendor_issues_html}</ul></section>"
        f"<section class='card'><h2>Archive</h2><ul>{archive_links}</ul><small>Machine-readable latest data: <a href='data/latest.json'>data/latest.json</a></small></section>"
    )
    history_body = f"<section class='nav'><a href='../index.html'>Back to latest dashboard</a><a href='../data/latest.json'>Latest JSON</a></section><section class='hero'><p class='pill {trust_pill}'>{result.trust_label}</p><h1>{report_name.replace('_', ' ').title()}</h1><p>{result.generated_at}</p></section><section class='card'><pre>{summary_md}</pre></section>"
    root_index = _write_root_index(docs_dir, public_site_url)
    latest_html.write_text(_render_html("MacBook monitor dashboard", latest_body), encoding="utf-8")
    history_html.write_text(_render_html(report_name, history_body), encoding="utf-8")
    return {"root_index": root_index, "latest_html": latest_html, "history_html": history_html, "latest_json": latest_json, "history_json": history_json}
