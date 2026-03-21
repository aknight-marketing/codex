# codex

Refurbished MacBook Pro monitor focused on UK sellers and 14-inch configurations.

## What it does

- Searches configured UK vendors for refurbished 14-inch MacBook Pro listings.
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

## GitHub Actions schedules

- Full sweep: Saturdays at `08:00 UTC` (`09:00` UK when on GMT / winter time; adjust if you want DST-locked wall clock behavior)
- Stock monitor: daily at `11:00 UTC` and `18:00 UTC`
- Both workflows also support manual `workflow_dispatch`

## Environment note

The code prefers Playwright for browser-backed fetching. In restricted environments where outbound browser/network access is blocked, it falls back to a local offline snapshot so the pipeline can still be smoke-tested end to end.
