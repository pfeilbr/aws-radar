"""Raw items -> digests and site data. Re-runs from scratch every time; raw is the truth.

Writes
    site/data/index.js           catalog, per-service counts, latest items (all services)
    site/data/s/<service>.js     that service's timeline
    data/services/<service>.md   the same timeline as Markdown, readable on GitHub
    data/changes/<date>.md       what each run added (from each item's fetch time)

Site data is JavaScript (`window.RADAR...=`), not JSON, so the page also works from file://.
"""

from __future__ import annotations

import json
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

import yaml

from radar import CONFIG_DIR, DATA_DIR, ROOT, SITE_DIR, SITE_URL
from radar.catalog import Catalog
from radar.classify import regions_for, services_for, tags_for
from radar.store import RawStore, iso, load_state, utcnow
from radar.text import first_sentences

SERVICE_ITEM_CAP = 600
LATEST_DAYS = 7
LATEST_CAP = 800
MD_CAP = 150
CHANGES_LIST_CAP = 300
RUN_GAP = timedelta(minutes=15)
_AWS_WORD = re.compile(r"\b(?:AWS|Amazon|re:Invent)\b", re.I)
_AWS_TITLE = re.compile(r"\bAWS\b|\bre:Invent\b|\bAmazon [A-Z]")  # "Amazon S3", not "Amazon scammer"
SKIP_SDK_SERVICES = {"endpoint-rules"}  # botocore housekeeping, not a service change


def load_sources() -> dict[str, dict]:
    cfg = yaml.safe_load((CONFIG_DIR / "sources.yaml").read_text())
    return {s["id"]: s for s in cfg["sources"]}


def _url_key(url: str) -> str:
    base, _, query = url.split("#")[0].partition("?")
    params = "&".join(p for p in query.split("&") if p and not p.startswith("utm_"))
    base = base.rstrip("/").lower().replace("http://", "https://")
    return f"{base}?{params}" if params else base


def digest_item(item: dict, src: dict, cat: Catalog) -> dict:
    title = item["title"]
    summary = first_sentences(item["summary"], 260) if item["summary"] else ""
    if summary and (summary.lower().startswith(title.lower()[:60]) or title.lower() in summary.lower()):
        summary = ""  # adds nothing beyond the title
    api = None
    if "/releases/" in item["url"] and re.fullmatch(r"v?[\d.]+[\w.-]*", title):
        title = f"{src['name'].removesuffix(' releases')} {title}"  # bare version tags
    if src["type"] == "github-changelog":
        api = (item.get("extra") or {}).get("sdk_service")
        summary, title = "", first_sentences(item["summary"] or title, 300)
    if src["type"] == "github-issues":
        summary = ""  # issue bodies are the roadmap template ("Community Note ... vote")
    if src["type"] == "bluesky-author":
        title, summary = first_sentences(item["summary"] or title, 300), ""
    primary, mentioned = services_for(item, src, cat)
    d = {
        "id": item["id"],
        "d": item["published"],
        "t": title,
        "u": item["url"],
        "src": item["source"],
        "svc": primary,
        "tags": tags_for(item, src),
    }
    if mentioned:
        d["m"] = mentioned
    regions = regions_for(item, src)
    if regions:
        d["rg"] = regions
    if api:
        d["api"] = api
    if summary:
        d["s"] = summary
    if item["authors"]:
        d["by"] = ", ".join(item["authors"][:3])
    x = item.get("extra") or {}
    if x.get("points") is not None:
        d["pts"] = x["points"]
    if x.get("hn_url"):
        d["hn"] = x["hn_url"]
    if x.get("link"):
        d["link"] = x["link"]
    return d


def collect_digests(cat: Catalog, sources: dict[str, dict]) -> list[dict]:
    by_url: dict[str, dict] = {}
    out = []
    for item in RawStore().all_items():
        src = sources.get(item["source"])
        if not src:
            continue
        if (item.get("extra") or {}).get("sdk_service") in SKIP_SDK_SERVICES:
            continue
        d = digest_item(item, src, cat)
        if src["group"] == "social" and not (d["svc"] or d.get("m")) and not _AWS_WORD.search(
                f"{item['title']} {item['summary']}"):
            continue  # off-topic post from an AWS person; stays in data/raw
        if src["type"] == "hn-algolia" and not d["svc"] and not _AWS_TITLE.search(item["title"]):
            continue  # search hit that only names AWS in passing (or not at all); stays in data/raw
        d["_f"] = item["fetched"]
        key = _url_key(d["u"]) if src["type"] != "github-changelog" else d["id"]
        prev = by_url.get(key)
        if prev and prev["src"] == d["src"]:
            key = d["id"]  # one source, several items sharing a generic URL (status page)
            prev = None
        if prev:  # same post via two sources (News Blog RSS + Blogs API): merge
            prev["svc"] += [s for s in d["svc"] if s not in prev["svc"]]
            prev["m"] = [s for s in prev.get("m", []) + d.get("m", []) if s not in prev["svc"]]
            prev["tags"] += [t for t in d["tags"] if t not in prev["tags"]]
            prev.setdefault("also", []).append(d["src"])
            continue
        by_url[key] = d
        out.append(d)
    out.sort(key=lambda d: d["d"], reverse=True)
    return out


def _md_line(d: dict, sources: dict) -> str:
    tags = " ".join(f"`{t}`" for t in d["tags"])
    text = (f"`{d['api']}` " if d.get("api") else "") + d["t"] + (f" — {d['s']}" if d.get("s") else "")
    return f"- {d['d'][:10]} {tags} [{text}]({d['u']}) · {sources[d['src']]['name']}"


FEED_CAP = 60
_ATTR = {'"': "&quot;"}  # saxutils.escape leaves quotes alone; attributes need them escaped


def _safe_url(url: str, page: str) -> str:
    """Feed links come from third parties: only http(s) passes, anything else points at the site."""
    return url if re.match(r"https?://", url or "", re.I) else SITE_URL + page
LAUNCH_KINDS = {"aws-whats-new", "aws-news-blog", "botocore-changelog", "containers-roadmap-shipped",
                "cloudformation-roadmap-shipped"}


def _atom(path: Path, title: str, page: str, items: list[dict], sources: dict, cat: Catalog) -> None:
    """One Atom feed. Entry ids are the stable item ids, so readers never see repeats."""
    updated = items[0]["d"] if items else iso(utcnow())
    out = ['<?xml version="1.0" encoding="utf-8"?>',
           '<feed xmlns="http://www.w3.org/2005/Atom">',
           f"<title>{escape(title)}</title>",
           f'<link rel="alternate" href="{escape(SITE_URL + page)}"/>',
           f'<link rel="self" href="{escape(SITE_URL + str(path.relative_to(SITE_DIR)))}"/>',
           f"<id>{escape(SITE_URL + str(path.relative_to(SITE_DIR)))}</id>",
           f"<updated>{updated}</updated>",
           "<author><name>AWS Radar</name></author>"]
    for d in items[:FEED_CAP]:
        tags = " ".join(f"[{t}]" for t in d["tags"])
        svcs = ", ".join(cat.services[s].short for s in d["svc"] if s in cat.services)
        body = " · ".join(filter(None, [tags, svcs, sources[d["src"]]["name"], d.get("s")]))
        title_text = (f"{d['api']}: " if d.get("api") else "") + d["t"]
        out += ["<entry>",
                f"<title>{escape(title_text)}</title>",
                f'<link href="{escape(_safe_url(d["u"], page), _ATTR)}"/>',
                f"<id>urn:aws-radar:{escape(d['id'])}</id>",
                f"<updated>{d['d']}</updated>",
                f"<summary>{escape(body)}</summary>",
                "</entry>"]
    out.append("</feed>")
    path.write_text("\n".join(out) + "\n")


def write_feeds(digests: list[dict], per_service: dict, cat: Catalog, sources: dict) -> None:
    feeds = SITE_DIR / "feeds"
    if feeds.exists():
        shutil.rmtree(feeds)
    (feeds / "s").mkdir(parents=True)
    _atom(feeds / "launches.xml", "AWS Radar · launches and API changes", "",
          [d for d in digests if d["src"] in LAUNCH_KINDS], sources, cat)
    _atom(feeds / "all.xml", "AWS Radar · everything", "", digests, sources, cat)
    for sid, items in per_service.items():
        main = [d for d in items if sid in d["svc"]]
        if main and sid in cat.services:
            _atom(feeds / "s" / f"{sid}.xml", f"AWS Radar · {cat.services[sid].name}",
                  f"#/s/{sid}", main, sources, cat)


WEEKLY_WEEKS = 26
ROADMAP_SOURCES = {"containers-roadmap-shipped", "cloudformation-roadmap-shipped"}


def write_weekly(digests: list[dict], cat: Catalog, sources: dict, now: datetime) -> None:
    """data/weekly/<YYYY>-W<ww>.md: one page per ISO week, launches first. Rebuilt every run."""
    out_dir = DATA_DIR / "weekly"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    weeks: dict[tuple[int, int], list[dict]] = defaultdict(list)
    cutoff = iso(now - timedelta(weeks=WEEKLY_WEEKS))
    for d in digests:
        if d["d"] >= cutoff:
            y, w, _ = datetime.fromisoformat(d["d"].replace("Z", "+00:00")).isocalendar()
            weeks[(y, w)].append(d)

    def svc_name(d: dict) -> str:
        return cat.services[d["svc"][0]].name if d["svc"] and d["svc"][0] in cat.services else "Other"

    index = ["# AWS Radar · weekly", "", "Generated from data/raw; do not edit.", ""]
    for (y, w) in sorted(weeks, reverse=True):
        items = weeks[(y, w)]
        start = datetime.fromisocalendar(y, w, 1).date()
        launches = [d for d in items if d["src"] in ("aws-whats-new", "aws-news-blog")]
        api = [d for d in items if d["src"] == "botocore-changelog"]
        shipped = [d for d in items if d["src"] in ROADMAP_SOURCES]
        community = sorted((d for d in items if d.get("pts")), key=lambda d: -d["pts"])[:10]
        name = f"{y}-W{w:02d}"
        lines = [f"# AWS Radar · week {w}, {y} (from {start})", "",
                 f"{len(launches)} launches · {len(api)} API changes · {len(shipped)} roadmap items shipped · "
                 f"{len(items)} items in all. Generated from data/raw; do not edit.", ""]
        if launches:
            lines += ["## Launches", ""]
            by_svc: dict[str, list[dict]] = defaultdict(list)
            for d in launches:
                by_svc[svc_name(d)].append(d)
            for sname in sorted(by_svc, key=lambda k: (-len(by_svc[k]), k)):
                lines.append(f"### {sname}")
                lines += [_md_line(d, sources) for d in by_svc[sname]]
                lines.append("")
        if api:
            lines += ["## API changes (botocore)", ""]
            by_api: dict[str, list[dict]] = defaultdict(list)
            for d in api:
                by_api[d.get("api", "?")].append(d)
            for name_ in sorted(by_api, key=lambda k: (-len(by_api[k]), k)):
                first = by_api[name_][0]
                more = f" (+{len(by_api[name_]) - 1} more)" if len(by_api[name_]) > 1 else ""
                lines.append(f"- `{name_}` {first['t']}{more}")
            lines.append("")
        if shipped:
            lines += ["## Shipped from public roadmaps", ""] + [_md_line(d, sources) for d in shipped] + [""]
        if community:
            lines += ["## Most discussed (Hacker News)", ""]
            lines += [f"- {d['pts']} pts · [{d['t']}]({d.get('hn') or d['u']})" for d in community] + [""]
        (out_dir / f"{name}.md").write_text("\n".join(lines) + "\n")
        index.append(f"- [{name}]({name}.md) · from {start} · {len(launches)} launches, {len(api)} API changes")
    (out_dir / "README.md").write_text("\n".join(index) + "\n")


def write_catalog_gaps(cat: Catalog, sources: dict) -> int:
    """data/reports/catalog-gaps.md: source service tags that map to no service.

    The to-do list for config/service_overrides.yaml (add an alias, or add to ignore_tags).
    """
    gaps: dict[str, Counter] = defaultdict(Counter)
    for item in RawStore().all_items():
        src = sources.get(item["source"])
        if not src:
            continue
        for t in item["tags_raw"]:
            if src["type"] == "github-changelog":
                if t not in SKIP_SDK_SERVICES and not cat.match_botocore(t):
                    gaps["botocore service names"][t] += 1
            elif src["id"] == "aws-whats-new":
                if t.startswith("general:products/"):
                    slug = t.split("/")[-1]
                    if slug not in cat.ignore_tags and not cat.match_name(slug):
                        gaps["What's New product slugs"][slug] += 1
            elif src["type"] == "aws-blog-api":
                if t not in cat.ignore_tags and not cat.match_name(t):
                    gaps["AWS Blogs tags"][t] += 1
    out = DATA_DIR / "reports" / "catalog-gaps.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Catalog gaps", "",
             "Service tags from sources that map to no service in the catalog. Fix by adding an",
             "alias in `config/service_overrides.yaml` (or listing the tag under `ignore_tags`),",
             "then `uv run scripts/build_catalog.py`. Generated; do not edit.", ""]
    total = 0
    for kind in sorted(gaps):
        lines += [f"## {kind}", "", "| tag | items |", "| --- | ---: |"]
        lines += [f"| `{t}` | {n} |" for t, n in gaps[kind].most_common()]
        lines.append("")
        total += len(gaps[kind])
    if not total:
        lines.append("None. Every service tag maps to a service.")
    out.write_text("\n".join(lines) + "\n")
    return total


def build(now: datetime | None = None) -> dict:
    now = now or utcnow()
    cat = Catalog.load()
    sources = load_sources()
    digests = collect_digests(cat, sources)
    write_changes(digests, cat, sources)
    for d in digests:
        del d["_f"]

    per_service: dict[str, list[dict]] = defaultdict(list)
    for d in digests:
        for sid in d["svc"] + d.get("m", []):
            per_service[sid].append(d)

    data_dir = SITE_DIR / "data"
    if data_dir.exists():
        shutil.rmtree(data_dir)
    (data_dir / "s").mkdir(parents=True)
    md_dir = DATA_DIR / "services"
    if md_dir.exists():
        shutil.rmtree(md_dir)
    md_dir.mkdir(parents=True)

    def since(days: int) -> str:
        return iso(now - timedelta(days=days))

    samples: dict[str, list[dict]] = defaultdict(list)
    for readme in sorted((ROOT / "samples").glob("*/*/*/README.md")):
        sid, lang, name = readme.parent.relative_to(ROOT / "samples").parts
        samples[sid].append({"lang": lang, "name": name, "path": f"samples/{sid}/{lang}/{name}"})

    services_out = []
    for s in sorted(cat.services.values(), key=lambda s: s.short.lower()):
        items = per_service.get(s.id, [])
        main = [d for d in items if s.id in d["svc"]]
        launches = [d for d in main if d["src"] in ("aws-whats-new", "aws-news-blog", "botocore-changelog")]
        services_out.append({
            "id": s.id, "name": s.name, "short": s.short, "cat": s.category, "icon": s.icon,
            "parent": s.parent, "total": len(main), "mentions": len(items) - len(main),
            "n7": sum(d["d"] >= since(7) for d in main),
            "n30": sum(d["d"] >= since(30) for d in main),
            "l30": sum(d["d"] >= since(30) for d in launches),
            "last": main[0]["d"] if main else None,
            **({"samples": samples[s.id]} if samples.get(s.id) else {}),
        })
        if items:
            payload = json.dumps(items[:SERVICE_ITEM_CAP], ensure_ascii=False, separators=(",", ":"))
            (data_dir / "s" / f"{s.id}.js").write_text(f"RADAR_LOAD({json.dumps(s.id)},{payload});\n")
        if main:
            lines = [f"# {s.name}", "",
                     f"Latest {min(len(main), MD_CAP)} of {len(main)} items. Generated by AWS Radar; "
                     "do not edit.", ""]
            lines += [_md_line(d, sources) for d in main[:MD_CAP]]
            (md_dir / f"{s.id}.md").write_text("\n".join(lines) + "\n")

    latest = [d for d in digests if d["d"] >= since(LATEST_DAYS)][:LATEST_CAP]

    # Compact full-history index for site search: [date, title, url, services, source, api, tags]
    search = [[d["d"][:10], d["t"], d["u"], " ".join(d["svc"]), d["src"], d.get("api", ""),
               " ".join(d["tags"])] for d in digests]
    (data_dir / "search.js").write_text(
        "window.RADAR_SEARCH=" + json.dumps(search, ensure_ascii=False, separators=(",", ":")) + ";\n")

    # Source health for the #/sources page.
    per_src: dict[str, list[str]] = defaultdict(list)
    for d in digests:
        for sid in [d["src"], *d.get("also", [])]:  # merged duplicates count for both sources
            per_src[sid].append(d["d"])
    health = {}
    for sid, src in sources.items():
        st = load_state(sid)
        err = st.get("last_error") or {}
        health[sid] = {
            "name": src["name"], "group": src["group"], "type": src["type"],
            "enabled": bool(src.get("enabled")), "cadence": src.get("cadence"),
            "items": len(per_src.get(sid, [])), "newest": max(per_src.get(sid, []), default=None),
            "last_success": st.get("last_success"), "last_run": st.get("last_run"),
            "error": err.get("error") if err and err.get("at", "") >= (st.get("last_success") or "") else None,
            "url": src.get("url", "").split("?")[0] if "{" not in src.get("url", "") else None,
        }
    index = {
        "generated": iso(now),
        "categories": cat.categories,
        "services": services_out,
        "sources": health,
        "site_url": SITE_URL,
        "latest": latest,
        "counts": {"items": len(digests), "unmatched": sum(1 for d in digests if not d["svc"])},
    }
    (data_dir / "index.js").write_text(
        "window.RADAR_INDEX=" + json.dumps(index, ensure_ascii=False, separators=(",", ":")) + ";\n")
    write_feeds(digests, per_service, cat, sources)
    write_weekly(digests, cat, sources, now)
    gaps = write_catalog_gaps(cat, sources)
    return index["counts"] | {"services_with_items": len(per_service), "catalog_gaps": gaps}


def write_changes(digests: list[dict], cat: Catalog, sources: dict) -> None:
    """data/changes/<date>.md: what each run added, derived from each item's fetch time.

    Derived (not appended) so the files can always be rebuilt, e.g. after a rebase.
    """
    # A run is a burst of fetches: a new one starts after a gap of more than RUN_GAP.
    runs: dict[str, list[dict]] = defaultdict(list)
    start = prev = None
    for d in sorted(digests, key=lambda d: d["_f"]):
        t = datetime.fromisoformat(d["_f"].replace("Z", "+00:00"))
        if prev is None or t - prev > RUN_GAP:
            start = d["_f"]
        runs[start].append(d)
        prev = t
    days: dict[str, list[str]] = defaultdict(list)
    for run in sorted(runs, reverse=True):
        days[run[:10]].append(run)
    out_dir = DATA_DIR / "changes"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    for day, day_runs in days.items():
        lines = [f"# AWS Radar · {day}", "",
                 "What each collection run added. Generated from data/raw; do not edit.", ""]
        for run in day_runs:
            items = runs[run]
            lines += [f"## Run {run[11:16]} UTC · {len(items)} new items", ""]
            groups: dict[str, list[dict]] = defaultdict(list)
            for d in items:
                groups[d["svc"][0] if d["svc"] else "_other"].append(d)
            order = sorted(groups, key=lambda k: (k == "_other", -len(groups[k]), k))
            if len(items) > CHANGES_LIST_CAP:  # a backfill: counts only
                lines += [f"- {cat.services[k].name if k in cat.services else 'Not mapped to a service'}: "
                          f"{len(groups[k])}" for k in order]
                lines.append("")
                continue
            for sid in order:
                name = cat.services[sid].name if sid in cat.services else "Not mapped to a service"
                lines.append(f"### {name}")
                lines += [_md_line(d, sources) for d in sorted(groups[sid], key=lambda d: d["d"], reverse=True)]
                lines.append("")
        (out_dir / f"{day}.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    print(build())
