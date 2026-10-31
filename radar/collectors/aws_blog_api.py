"""Every AWS blog through aws.amazon.com/api/dirs/items/search?item.directoryId=blog-posts."""

from __future__ import annotations

import re
from datetime import datetime

from radar.collectors import Context
from radar.store import make_id, make_item
from radar.text import html_to_text


def collect(src: dict, ctx: Context) -> list[dict]:
    pages = src.get("backfill_pages", 20) if ctx.backfill else src.get("max_pages", 5)
    items = []
    for page in range(pages):
        r = ctx.fetcher.get(src["url"].format(size=src.get("page_size", 100), page=page))
        r.raise_for_status()
        batch = r.json().get("items", [])
        if not batch:
            break
        new_on_page = 0
        for row in batch:
            it, f = row["item"], row["item"]["additionalFields"]
            if make_id(src["id"], it["id"]) not in ctx.seen:
                new_on_page += 1
            link = f.get("link", "")
            m = re.match(r"https://aws\.amazon\.com/blogs/([^/]+)/", link)
            tags = [t["name"] for t in row.get("tags", [])
                    if t["tagNamespaceId"].startswith("blog-posts#category")]
            items.append(make_item(
                source=src["id"], key=it["id"], url=link, title=html_to_text(f.get("title")),
                summary=html_to_text(f.get("postExcerpt")),
                published=datetime.fromisoformat(f["createdDate"].replace("Z", "+00:00")),
                authors=[a.strip() for a in (f.get("contributors") or "").split(",") if a.strip()],
                tags_raw=tags, extra={"blog": m.group(1)} if m else {},
            ))
        if not new_on_page and not ctx.backfill:
            break  # caught up with what is already stored
    return items
