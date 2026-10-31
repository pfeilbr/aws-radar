"""Bluesky posts from listed accounts via the public AppView (no auth)."""

from __future__ import annotations

import sys
from datetime import datetime

from radar.collectors import Context
from radar.store import make_item


def collect(src: dict, ctx: Context) -> list[dict]:
    items = []
    for actor in src["actors"]:
        r = ctx.fetcher.get(src["url"].format(actor=actor))
        if r.status_code != 200:
            print(f"    bluesky {actor}: HTTP {r.status_code}", file=sys.stderr)
            continue
        for entry in r.json().get("feed", []):
            post = entry["post"]
            if entry.get("reason") or post["author"]["handle"] != actor:
                continue  # reposts: the original author is not on our list
            rec = post["record"]
            text = rec.get("text", "")
            rkey = post["uri"].rsplit("/", 1)[-1]
            extra = {"likes": post.get("likeCount"), "reposts": post.get("repostCount")}
            ext = (post.get("embed") or {}).get("external") or {}
            if ext.get("uri"):
                extra["link"] = ext["uri"]
                extra["link_title"] = ext.get("title")
            title = text.split("\n", 1)[0][:200] or ext.get("title") or "(no text)"
            items.append(make_item(
                source=src["id"], key=post["uri"],
                url=f"https://bsky.app/profile/{actor}/post/{rkey}", title=title,
                summary=" ".join(filter(None, [text, ext.get("title")])),
                published=datetime.fromisoformat(rec["createdAt"].replace("Z", "+00:00")),
                authors=[post["author"].get("displayName") or actor], extra=extra,
            ))
    return items
