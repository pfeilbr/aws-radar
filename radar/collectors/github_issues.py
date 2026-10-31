"""GitHub issues with a label, e.g. AWS public roadmaps' "Shipped" / "Coming Soon" cards.

Uses GITHUB_TOKEN when set (Actions provides one); unauthenticated limits are fine too.
"""

from __future__ import annotations

import os
from datetime import datetime

from radar.collectors import Context
from radar.store import make_item
from radar.text import html_to_text


def collect(src: dict, ctx: Context) -> list[dict]:
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    pages = src.get("backfill_pages", 3) if ctx.backfill else 1
    label = src["label"]
    items = []
    for page in range(1, pages + 1):
        r = ctx.fetcher.get(src["url"].format(page=page), headers=headers)
        r.raise_for_status()
        batch = r.json()
        for issue in batch:
            if "pull_request" in issue:
                continue
            when = issue.get("closed_at") if src.get("state") == "closed" else issue.get("updated_at")
            labels = [lb["name"] for lb in issue.get("labels", [])]
            items.append(make_item(
                # Keyed by label too: a card that moves from "Coming Soon" to "Shipped" is news twice.
                source=src["id"], key=f"{issue['number']}:{label}", url=issue["html_url"],
                title=issue["title"], summary=html_to_text(issue.get("body") or "")[:600],
                published=datetime.fromisoformat((when or issue["created_at"]).replace("Z", "+00:00")),
                tags_raw=labels,
                extra={"number": issue["number"], "label": label,
                       "reactions": (issue.get("reactions") or {}).get("total_count")},
            ))
        if len(batch) < 100:
            break
    return items
