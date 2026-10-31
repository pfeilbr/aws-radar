"""X (Twitter) posts from the accounts a handle follows, or from an X List.

UNTESTED: written against the X API v2 docs without a token. Needs X_BEARER_TOKEN (a paid
X API plan) and either `handle` or `list_id` in sources.yaml. See docs/sources.md.

Modes
  list_id set:  GET /2/lists/:id/tweets             one request per run (cheapest)
  handle set:   GET /2/users/by/username/:handle    -> user id (cached in state)
                GET /2/users/:id/following          follow list, refreshed weekly (cached)
                keep accounts whose bio mentions AWS (or all, with aws_only: false),
                at most `max_accounts`, then GET /2/users/:id/tweets per account with
                since_id cursors so each run only pays for new posts.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta

from radar.collectors import Context, Skip
from radar.store import iso, make_item, utcnow

API = "https://api.x.com/2"
TWEET_FIELDS = "tweet.fields=created_at,author_id,entities,public_metrics"
AWS_BIO = re.compile(r"\b(?:AWS|Amazon Web Services|re:Invent|serverless|cloud)\b", re.I)


def _get(ctx: Context, url: str, token: str) -> dict:
    r = ctx.fetcher.get(url, headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return r.json()


def _item(src: dict, tweet: dict, username: str) -> dict:
    text = tweet.get("text", "")
    urls = [u.get("expanded_url") for u in (tweet.get("entities") or {}).get("urls", []) if u.get("expanded_url")]
    metrics = tweet.get("public_metrics") or {}
    return make_item(
        source=src["id"], key=tweet["id"], url=f"https://x.com/{username}/status/{tweet['id']}",
        title=text.split("\n", 1)[0][:200] or "(no text)", summary=text,
        published=datetime.fromisoformat(tweet["created_at"].replace("Z", "+00:00")),
        authors=[username],
        extra={"link": urls[0] if urls else None, "likes": metrics.get("like_count"),
               "reposts": metrics.get("retweet_count")},
    )


def collect(src: dict, ctx: Context) -> list[dict]:
    token = os.environ.get(src.get("auth_env", "X_BEARER_TOKEN"))
    if not token:
        raise Skip(f"set {src.get('auth_env', 'X_BEARER_TOKEN')} to collect from X")
    if not (src.get("list_id") or src.get("handle")):
        raise Skip("set x-following.handle or x-following.list_id in config/sources.yaml")

    if src.get("list_id"):
        data = _get(ctx, f"{API}/lists/{src['list_id']}/tweets?max_results=100&expansions=author_id"
                         f"&user.fields=username&{TWEET_FIELDS}", token)
        users = {u["id"]: u["username"] for u in (data.get("includes") or {}).get("users", [])}
        return [_item(src, t, users.get(t.get("author_id"), "i")) for t in data.get("data", [])]

    st = ctx.state.setdefault("x", {})
    if "user_id" not in st:
        st["user_id"] = _get(ctx, f"{API}/users/by/username/{src['handle']}", token)["data"]["id"]

    refreshed = st.get("following_refreshed")
    if not refreshed or utcnow() - datetime.fromisoformat(refreshed.replace("Z", "+00:00")) > timedelta(days=7):
        following, page = [], ""
        while True:
            data = _get(ctx, f"{API}/users/{st['user_id']}/following?max_results=1000"
                             f"&user.fields=description,username{page}", token)
            following += data.get("data", [])
            nxt = (data.get("meta") or {}).get("next_token")
            if not nxt:
                break
            page = f"&pagination_token={nxt}"
        aws_only = src.get("aws_only", True)
        keep = [u for u in following if not aws_only or AWS_BIO.search(u.get("description", ""))]
        st["accounts"] = {u["id"]: u["username"] for u in keep[: src.get("max_accounts", 50)]}
        st["following_refreshed"] = iso(utcnow())

    items = []
    cursors = st.setdefault("since_id", {})
    for uid, username in st["accounts"].items():
        since = f"&since_id={cursors[uid]}" if uid in cursors else ""
        data = _get(ctx, f"{API}/users/{uid}/tweets?max_results=20&exclude=retweets,replies"
                         f"&{TWEET_FIELDS}{since}", token)
        tweets = data.get("data", [])
        if tweets:
            cursors[uid] = max(tweets, key=lambda t: int(t["id"]))["id"]
        items += [_item(src, t, username) for t in tweets]
    return items
