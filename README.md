# codex

Refurbished MacBook Pro monitor focused on UK sellers and 14-inch configurations.

## What it does

- Searches configured UK vendors for refurbished 14-inch MacBook Pro listings.
- Uses direct vendor discovery pages first, plus vendor-specific extraction for Apple Certified Refurbished UK, MacFinder, Hoxton Macs, Back Market UK, CeX, and musicMagpie.
- Validates product pages rather than trusting search/category snippets alone.
- Excludes listings from the ranked shortlist unless price, chip, RAM, SSD, stock, and 14-inch size are all clearly parsed.
- Produces JSON, CSV, XLSX, Markdown, and a mobile-friendly static HTML report site.
- Publishes the latest dashboard and historical snapshots through GitHub Pages.
- Includes a stock-monitor mode with stateful change detection and optional email notification via SMTP environment variables.

## Layout

- `monitor/vendors.json` — vendor configuration, discovery URLs, and watch URLs
- `monitor/run_full.py` — full Saturday sweep
- `monitor/run_stock_monitor.py` — twice-daily stock monitor
- `monitor/extractors/` — vendor-specific and generic page extraction
- `monitor/reporting.py` — JSON/CSV/XLSX/Markdown plus `docs/` HTML publishing
- `docs/index.html` — latest mobile-friendly dashboard
- `docs/history/` — archived reports
- `docs/data/latest.json` — latest machine-readable snapshot
- `docs/data/history/` — historical JSON snapshots

## Manual run

Production-style local run:

- Validates product pages rather than trusting search/category snippets alone.
- Extracts vendor, title, chip, RAM, SSD, price, stock status, warranty, returns, delivery, keyboard layout, and direct URL where available.
- Scores listings for spec fit, seller trust, and value.
- Produces JSON, CSV, XLSX, and Markdown outputs. XLSX files are generated at runtime or in workflow artifacts, but are not committed to the repo to keep PRs text-only.
- Includes a stock-monitor mode with stateful change detection.
- Ships with GitHub Actions schedules for a Saturday full sweep and twice-daily stock checks.

## Layout

- `monitor/vendors.json` — vendor configuration and trust metadata
- `monitor/run_full.py` — full Saturday sweep
- `monitor/run_stock_monitor.py` — twice-daily stock monitor
- `monitor/scoring.py` — explicit scoring model
- `monitor/extractors/generic.py` — page extraction logic
- `monitor/output/` — generated outputs
- `.github/workflows/` — scheduled GitHub Actions workflows

## Manual run

```bash
python3 -m monitor.run_full --verbose
python3 -m monitor.run_stock_monitor --verbose
```

Explicit local fixture test mode:

```bash
python3 -m monitor.run_full --test-mode --verbose
python3 -m monitor.run_stock_monitor --test-mode --verbose
```

## GitHub Pages publishing

Both scheduled workflows now deploy the generated `docs/` directory to GitHub Pages, so the primary UX is a phone-friendly static report site rather than downloadable artifacts.

Expected Pages URL pattern:

```text
https://<owner>.github.io/<repo>/
```

Artifacts are still uploaded as a debugging fallback, but they are no longer the primary way to consume results.

## Optional email notification

If these secrets/environment variables are set, the monitor can send a short email summary after a run:

- `MONITOR_SMTP_HOST`
- `MONITOR_SMTP_PORT`
- `MONITOR_SMTP_USERNAME`
- `MONITOR_SMTP_PASSWORD`
- `MONITOR_EMAIL_FROM`
- `MONITOR_EMAIL_TO`

If they are not configured, the monitor still works fully via GitHub Pages.

## GitHub Actions schedules

- Full sweep: Saturdays at `08:00 UTC` (`09:00` UK when on GMT / winter time; adjust if you want DST-locked wall clock behavior)
- Stock monitor: daily at `11:00 UTC` and `18:00 UTC`
- Both workflows also support manual `workflow_dispatch`

## Environment note

Offline fixtures are now for **explicit test mode only**. Scheduled and production runs do **not** silently fall back to fixtures; they report failures clearly instead.
The code prefers Playwright for browser-backed fetching. In restricted environments where outbound browser/network access is blocked, it falls back to a local offline snapshot so the pipeline can still be smoke-tested end to end.
