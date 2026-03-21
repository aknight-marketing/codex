from __future__ import annotations

import logging
import time
import urllib.request
from dataclasses import dataclass

logger = logging.getLogger(__name__)

try:
    from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright
except Exception:  # pragma: no cover - fallback for minimal environments
    Browser = BrowserContext = Page = None
    sync_playwright = None


@dataclass
class BrowserConfig:
    headless: bool = True
    timeout_ms: int = 30000
    retries: int = 2


class BrowserSession:
    def __init__(self, config: BrowserConfig):
        self.config = config
        self._pw = None
        self.browser = None
        self.context = None
        self.mode = "urllib"

    def __enter__(self) -> "BrowserSession":
        if sync_playwright is not None:
            try:
                self._pw = sync_playwright().start()
                self.browser = self._pw.chromium.launch(headless=self.config.headless)
                self.context = self.browser.new_context(
                    user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36",
                    locale="en-GB",
                    timezone_id="Europe/London",
                )
                self.mode = "playwright"
                return self
            except Exception as exc:
                logger.warning("Playwright unavailable, falling back to urllib: %s", exc)
        self.mode = "urllib"
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self._pw:
            self._pw.stop()

    def get_html(self, url: str) -> str:
        last_exc = None
        for attempt in range(1, self.config.retries + 2):
            try:
                if self.mode == "playwright":
                    page = self.context.new_page()
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=self.config.timeout_ms)
                        page.wait_for_timeout(1500)
                        return page.content()
                    finally:
                        page.close()
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=self.config.timeout_ms / 1000) as response:
                    return response.read().decode("utf-8", errors="ignore")
            except Exception as exc:
                last_exc = exc
                logger.warning("Fetch failed for %s on attempt %s/%s: %s", url, attempt, self.config.retries + 1, exc)
                time.sleep(min(2 * attempt, 5))
        raise RuntimeError(f"Unable to fetch {url}: {last_exc}")
