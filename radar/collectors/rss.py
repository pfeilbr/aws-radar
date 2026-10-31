"""RSS/Atom feeds: What's New, AWS blogs, GitHub releases, YouTube, Reddit, newsletters."""

from __future__ import annotations

import re
from datetime import datetime, timezone

import feedparser

from radar.collectors import Context
from radar.store import make_item, utcnow
from radar.text import html_to_text

_REDDIT_FOOTER = re.compile(r"\s*submitted by\s+/u/\S+.*$", re.S)


def _date(entry) -> datetime:
    for k in ("published_parsed", "updated_parsed"):
        if entry.get(k):
            return datetime(*entry[k][:6], tzinfo=timezone.utc)
    return utcnow()


def collect(src: dict, ctx: Context) -> list[dict]:
    r = ctx.fetcher.get_conditional(src["url"], ctx.state)
    if r is None:
        return []
    feed = feedparser.parse(r.content)
    items = []
    for e in feed.entries:
        link = e.get("link") or ""
        key = e.get("id") or link
        if not key:
            continue
        tags = []
        for t in e.get("tags") or []:
            # What's New packs several tags into one comma-separated <category>.
            tags += [x.strip() for x in (t.get("term") or "").split(",") if x.strip()]
        summary = html_to_text(e.get("summary") or e.get("description"))
        extra = {}
        if "reddit.com" in link:
            summary = _REDDIT_FOOTER.sub("", summary)
            m = re.search(r"reddit\.com/r/([^/]+)/", link)
            if m:
                extra["subreddit"] = m.group(1)
        if e.get("yt_videoid"):
            extra["video_id"] = e["yt_videoid"]
        authors = [a.get("name") for a in e.get("authors") or [] if a.get("name")]
        items.append(make_item(
            source=src["id"], key=key, url=link, title=html_to_text(e.get("title")),
            summary=summary, published=_date(e), authors=authors, tags_raw=tags, extra=extra,
        ))
    return items
