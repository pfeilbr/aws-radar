"""Hacker News stories via the Algolia search API."""

from __future__ import annotations

from datetime import UTC, datetime

from radar.collectors import Context
from radar.store import make_item


def collect(src: dict, ctx: Context) -> list[dict]:
    pages = src.get("backfill_pages", 5) if ctx.backfill else 1
    items = []
    for page in range(pages):
        r = ctx.fetcher.get(f"{src['url']}&page={page}")
        r.raise_for_status()
        hits = r.json().get("hits", [])
        for h in hits:
            hn_url = f"https://news.ycombinator.com/item?id={h['objectID']}"
            items.append(make_item(
                source=src["id"], key=h["objectID"], url=h.get("url") or hn_url,
                title=h.get("title") or "",
                published=datetime.fromtimestamp(h["created_at_i"], tz=UTC),
                authors=[h["author"]] if h.get("author") else [],
                extra={"hn_url": hn_url, "points": h.get("points"),
                       "comments": h.get("num_comments")},
            ))
        if not hits:
            break
    return items
