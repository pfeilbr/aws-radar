"""Polite HTTP: one client, per-host spacing, backoff on 429/503, conditional GETs."""

from __future__ import annotations

import sys
import time
from urllib.parse import urlparse

import httpx


class Fetcher:
    def __init__(self, defaults: dict):
        self.client = httpx.Client(
            headers={"User-Agent": defaults["user_agent"]},
            timeout=defaults.get("timeout_seconds", 30),
            follow_redirects=True,
        )
        self.intervals = defaults.get("min_interval_seconds") or {}
        self.last_hit: dict[str, float] = {}

    def get(self, url: str, retries: int = 3, **kwargs) -> httpx.Response:
        host = urlparse(url).hostname or ""
        for attempt in range(1, retries + 1):
            wait = self.intervals.get(host, 0) - (time.monotonic() - self.last_hit.get(host, 0))
            if wait > 0:
                time.sleep(wait)
            self.last_hit[host] = time.monotonic()
            r = self.client.get(url, **kwargs)
            if r.status_code not in (429, 503) or attempt == retries:
                return r
            retry_after = r.headers.get("retry-after", "")
            delay = int(retry_after) if retry_after.isdigit() else 20 * attempt
            print(f"    {host}: HTTP {r.status_code}, retrying in {delay}s", file=sys.stderr)
            time.sleep(min(delay, 120))
        return r

    def get_conditional(self, url: str, state: dict) -> httpx.Response | None:
        """GET with If-None-Match / If-Modified-Since from state; None when unchanged (304).

        Updates state["http"][url] with the new validators on 200.
        """
        validators = state.setdefault("http", {}).get(url, {})
        headers = {}
        if validators.get("etag"):
            headers["If-None-Match"] = validators["etag"]
        if validators.get("last_modified"):
            headers["If-Modified-Since"] = validators["last_modified"]
        r = self.get(url, headers=headers)
        if r.status_code == 304:
            return None
        r.raise_for_status()
        state["http"][url] = {
            k: v for k, v in (("etag", r.headers.get("etag")),
                              ("last_modified", r.headers.get("last-modified"))) if v
        }
        return r
