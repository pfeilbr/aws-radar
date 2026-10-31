"""Hit every source in config/sources.yaml once and report whether it works.

For each source: HTTP status, number of items returned, newest item date and its age.
Exits non-zero if any enabled source fails, so it can gate the scheduled job.

    uv run scripts/validate_sources.py
    uv run scripts/validate_sources.py --only reddit-aws --all
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import feedparser
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from radar import CONFIG_DIR  # noqa: E402
from radar.http import Fetcher  # noqa: E402

CONFIG = CONFIG_DIR / "sources.yaml"


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def check_rss(f: Fetcher, src: dict) -> tuple[int, int, datetime | None]:
    r = f.get(src["url"])
    feed = feedparser.parse(r.content)
    dates = [
        datetime(*e[k][:6], tzinfo=UTC)
        for e in feed.entries
        for k in ("published_parsed", "updated_parsed")
        if e.get(k)
    ]
    return r.status_code, len(feed.entries), max(dates, default=None)


def check_aws_blog_api(f: Fetcher, src: dict) -> tuple[int, int, datetime | None]:
    r = f.get(src["url"].format(size=src.get("page_size", 100), page=0))
    items = r.json().get("items", []) if r.status_code == 200 else []
    dates = [parse_date(i["item"]["additionalFields"].get("createdDate")) for i in items]
    return r.status_code, len(items), max(filter(None, dates), default=None)


def check_hn(f: Fetcher, src: dict) -> tuple[int, int, datetime | None]:
    r = f.get(src["url"])
    hits = r.json().get("hits", []) if r.status_code == 200 else []
    dates = [parse_date(h.get("created_at")) for h in hits]
    return r.status_code, len(hits), max(filter(None, dates), default=None)


def check_bluesky(f: Fetcher, src: dict) -> tuple[int, int, datetime | None]:
    total, newest, worst = 0, None, 200
    for actor in src["actors"]:
        r = f.get(src["url"].format(actor=actor))
        if r.status_code != 200:
            print(f"    ! {actor}: HTTP {r.status_code}", file=sys.stderr)
            worst = r.status_code
            continue
        feed = r.json().get("feed", [])
        total += len(feed)
        for p in feed:
            d = parse_date(p["post"]["record"].get("createdAt"))
            if d and (newest is None or d > newest):
                newest = d
    return worst, total, newest


def check_github_changelog(f: Fetcher, src: dict) -> tuple[int, int, datetime | None]:
    r = f.get(src["url"])
    # botocore CHANGELOG.rst: version headers are underlined with '='.
    versions = re.findall(r"^(\d+\.\d+\.\d+)\n=+$", r.text, re.M) if r.status_code == 200 else []
    if versions:
        print(f"    latest version {versions[0]}", file=sys.stderr)
    return r.status_code, len(versions), None


def check_github_issues(f: Fetcher, src: dict) -> tuple[int, int, datetime | None]:
    r = f.get(src["url"].format(page=1), headers={"Accept": "application/vnd.github+json"})
    issues = r.json() if r.status_code == 200 else []
    key = "closed_at" if src.get("state") == "closed" else "updated_at"
    dates = [parse_date(i.get(key)) for i in issues]
    return r.status_code, len(issues), max(filter(None, dates), default=None)


def check_x(f: Fetcher, src: dict) -> tuple[int, int, datetime | None]:
    if not os.environ.get(src.get("auth_env", "")):
        raise RuntimeError(f"skipped: set {src['auth_env']} to check")
    raise RuntimeError("X collector not implemented yet")


CHECKS = {
    "rss": check_rss,
    "aws-blog-api": check_aws_blog_api,
    "hn-algolia": check_hn,
    "bluesky-author": check_bluesky,
    "github-changelog": check_github_changelog,
    "github-issues": check_github_issues,
    "x-following": check_x,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", nargs="*", help="source ids to check")
    ap.add_argument("--all", action="store_true", help="include disabled sources")
    ap.add_argument("--json", action="store_true", help="print results as JSON")
    args = ap.parse_args()

    cfg = yaml.safe_load(CONFIG.read_text())
    fetcher = Fetcher(cfg["defaults"])
    now = datetime.now(UTC)
    results, failed = [], 0

    for src in cfg["sources"]:
        if args.only and src["id"] not in args.only:
            continue
        if not (src.get("enabled") or args.all or args.only):
            continue
        row = {"id": src["id"], "type": src["type"], "enabled": bool(src.get("enabled"))}
        try:
            status, count, newest = CHECKS[src["type"]](fetcher, src)
            age = round((now - newest).total_seconds() / 86400, 1) if newest else None
            stale_after = src.get("stale_after_days", cfg["defaults"].get("stale_after_days", 14))
            row |= {
                "status": status,
                "items": count,
                "newest": newest.isoformat() if newest else None,
                "age_days": age,
                "stale": age is not None and age > stale_after,
                "ok": status == 200 and count > 0,
            }
        except Exception as e:  # noqa: BLE001 - report every failure, keep going
            row |= {"status": None, "items": 0, "newest": None, "age_days": None,
                    "ok": False, "error": str(e)[:120]}
        if not row["ok"] and row["enabled"]:
            failed += 1
        results.append(row)
        if not args.json:
            if not row["enabled"]:
                mark = "off "
            elif not row["ok"]:
                mark = "FAIL"
            else:
                mark = "old " if row.get("stale") else "ok  "
            age = f"{row['age_days']}d" if row["age_days"] is not None else "-"
            print(f"{mark} {row['id']:<26} {str(row['status']):<5} {row['items']:>4} items  "
                  f"newest {age:>6}  {row.get('error', '')}")

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        enabled = [r for r in results if r["enabled"]]
        stale = sum(1 for r in enabled if r["ok"] and r.get("stale"))
        print(f"\n{len(enabled) - failed}/{len(enabled)} enabled sources ok"
              f" ({stale} stale), {len(results) - len(enabled)} disabled")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
