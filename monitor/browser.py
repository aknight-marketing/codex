from __future__ import annotations

import json
import logging
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover
    sync_playwright = None

ANTI_BOT_PATTERNS = [
    "tunnel connection failed",
    "access denied",
    "captcha",
    "cloudflare",
    "bot",
]
DNS_PATTERNS = ["name or service not known", "temporary failure in name resolution", "nodename nor servname"]
NETWORK_PATTERNS = ["network is unreachable", "connection refused", "connection reset", "remote end closed connection"]


@dataclass
class BrowserConfig:
    headless: bool = True
    timeout_ms: int = 30000
    retries: int = 2
    fixture_path: str | None = None


def classify_fetch_error(error: Exception | str) -> str:
    message = str(error).lower()
    if any(token in message for token in DNS_PATTERNS):
        return "dns_failure"
    if any(token in message for token in NETWORK_PATTERNS):
        return "network_failure"
    if "timed out" in message or "timeout" in message:
        return "timeout"
    if any(token in message for token in ANTI_BOT_PATTERNS):
        return "anti_bot_or_access_denied"
    if "http error" in message or "403 forbidden" in message or "404" in message or "500" in message:
        return "http_error"
    return "error"


class BrowserSession:
    def __init__(self, config: BrowserConfig):
        self.config = config
        self._pw = None
        self.browser = None
        self.context = None
        self.mode = "urllib"
        self.fixtures = self._load_fixtures(config.fixture_path)

    @property
    def fixture_fallback_used(self) -> bool:
        return self.mode == "fixture"

    @staticmethod
    def _load_fixtures(path: str | None) -> dict[str, str]:
        if not path:
            return {}
        fixture_path = Path(path)
        if not fixture_path.is_absolute():
            fixture_path = Path.cwd() / fixture_path
        if not fixture_path.exists():
            raise FileNotFoundError(f"Fixture file not found: {fixture_path}")
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return {k: str(v) for k, v in payload.items()}
        raise ValueError("Fixture file must be a JSON object mapping URL to HTML")

    def __enter__(self) -> "BrowserSession":
        if self.fixtures:
            self.mode = "fixture"
            return self
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
        if self.mode == "fixture":
            if url not in self.fixtures:
                raise KeyError(f"No fixture HTML for URL: {url}")
            return self.fixtures[url]
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
