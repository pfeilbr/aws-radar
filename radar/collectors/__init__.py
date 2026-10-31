"""One collector per source `type` in config/sources.yaml.

A collector is `collect(src, ctx) -> list[item]`. It may return items already stored; the
store dedupes by id. Collectors keep their cursors and HTTP validators in `ctx.state`.
"""

from __future__ import annotations

from dataclasses import dataclass

from radar.http import Fetcher


@dataclass
class Context:
    fetcher: Fetcher
    state: dict          # this source's persisted state (mutated in place)
    seen: set[str]       # ids already stored for this source
    backfill: bool       # first run or --backfill: go further back than usual


class Skip(Exception):
    """Source cannot run right now (e.g. missing token); not an error."""


def registry():
    from radar.collectors import aws_blog_api, bluesky, botocore, github_issues, hn, rss, x

    return {
        "rss": rss.collect,
        "aws-blog-api": aws_blog_api.collect,
        "hn-algolia": hn.collect,
        "bluesky-author": bluesky.collect,
        "github-changelog": botocore.collect,
        "github-issues": github_issues.collect,
        "x-following": x.collect,
    }
