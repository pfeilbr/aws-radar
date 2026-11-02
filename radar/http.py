"""Polite HTTP: one fetcher, per-host spacing, backoff on 429/503, conditional GETs.

Standard library (urllib) on purpose: Reddit answers `403 Blocked` to httpx requests from
GitHub Actions runners while curl and urllib with the same User-Agent get 200
(tested on 2026-10-31, see docs/sources.md).
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from email.message import Message
from urllib.parse import urlparse


class HTTPError(Exception):
    """Non-2xx response (raised by Response.raise_for_status) or a network failure."""


class Response:
    def __init__(self, url: str, status_code: int, headers: Message, content: bytes):
        self.url = url
        self.status_code = status_code
        self.headers = headers          # case-insensitive .get()
        self.content = content

    @property
    def text(self) -> str:
        charset = self.headers.get_content_charset() if hasattr(self.headers, "get_content_charset") else None
        return self.content.decode(charset or "utf-8", errors="replace")

    def json(self):
        return json.loads(self.content)

    def raise_for_status(self) -> None:
        if not 200 <= self.status_code < 300:
            reason = self.text[:60].strip().replace("\n", " ") if self.status_code >= 400 else ""
            raise HTTPError(f"HTTP {self.status_code} for {self.url} {reason}".rstrip())


def get(url: str, headers: dict | None = None, timeout: float = 30) -> Response:
    """One GET, following redirects. HTTP error statuses are returned, not raised."""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return Response(r.url, r.status, r.headers, r.read())
    except urllib.error.HTTPError as e:
        return Response(url, e.code, e.headers, e.read())
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise HTTPError(f"{type(e).__name__} for {url}: {e}") from e


class Fetcher:
    def __init__(self, defaults: dict):
        self.headers = {"User-Agent": defaults["user_agent"]}
        self.timeout = defaults.get("timeout_seconds", 30)
        self.intervals = defaults.get("min_interval_seconds") or {}
        self.last_hit: dict[str, float] = {}

    def get(self, url: str, retries: int = 3, headers: dict | None = None) -> Response:
        """GET with politeness spacing. Rate limits (429/503) and transient failures (502/504,
        timeouts, resets) are retried with backoff; the last response or error is returned/raised."""
        host = urlparse(url).hostname or ""
        for attempt in range(1, retries + 1):
            wait = self.intervals.get(host, 0) - (time.monotonic() - self.last_hit.get(host, 0))
            if wait > 0:
                time.sleep(wait)
            self.last_hit[host] = time.monotonic()
            try:
                r = get(url, {**self.headers, **(headers or {})}, self.timeout)
            except HTTPError as e:  # network-level: DNS, reset, timeout
                if attempt == retries:
                    raise
                print(f"    {host}: {e}, retrying in {5 * attempt}s", file=sys.stderr)
                time.sleep(5 * attempt)
                continue
            if r.status_code in (502, 504) and attempt < retries:
                print(f"    {host}: HTTP {r.status_code}, retrying in {5 * attempt}s", file=sys.stderr)
                time.sleep(5 * attempt)
                continue
            if r.status_code not in (429, 503) or attempt == retries:
                return r
            retry_after = r.headers.get("retry-after", "") or ""
            delay = int(retry_after) if retry_after.isdigit() else 20 * attempt
            print(f"    {host}: HTTP {r.status_code}, retrying in {delay}s", file=sys.stderr)
            time.sleep(min(delay, 120))
        return r

    def get_conditional(self, url: str, state: dict) -> Response | None:
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
