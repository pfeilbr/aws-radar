"""Raw items -> digests and site data. Re-runs from scratch every time; raw is the truth.

Writes
    site/data/index.js           catalog, per-service counts, latest items (all services)
    site/data/s/<service>.js     that service's timeline
    data/services/<service>.md   the same timeline as Markdown, readable on GitHub
    data/changes/<date>.md       items added by a run (append_changes)

Site data is JavaScript (`window.RADAR...=`), not JSON, so the page also works from file://.
"""

from __future__ import annotations

import json
import re
import shutil
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import yaml

from radar import CONFIG_DIR, DATA_DIR, SITE_DIR
from radar.catalog import Catalog
from radar.classify import services_for, tags_for
from radar.store import RawStore, iso, utcnow
from radar.text import first_sentences

SERVICE_ITEM_CAP = 600
LATEST_DAYS = 7
LATEST_CAP = 800
MD_CAP = 150
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


def build(now: datetime | None = None) -> dict:
    now = now or utcnow()
    cat = Catalog.load()
    sources = load_sources()
    digests = collect_digests(cat, sources)

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
        })
        if main:
            payload = json.dumps(items[:SERVICE_ITEM_CAP], ensure_ascii=False, separators=(",", ":"))
            (data_dir / "s" / f"{s.id}.js").write_text(f"RADAR_LOAD({json.dumps(s.id)},{payload});\n")
            lines = [f"# {s.name}", "",
                     f"Latest {min(len(main), MD_CAP)} of {len(main)} items. Generated by AWS Radar; "
                     "do not edit.", ""]
            lines += [_md_line(d, sources) for d in main[:MD_CAP]]
            (md_dir / f"{s.id}.md").write_text("\n".join(lines) + "\n")

    latest = [d for d in digests if d["d"] >= since(LATEST_DAYS)][:LATEST_CAP]
    index = {
        "generated": iso(now),
        "categories": cat.categories,
        "services": services_out,
        "sources": {k: {"name": v["name"], "group": v["group"]} for k, v in sources.items()},
        "latest": latest,
        "counts": {"items": len(digests), "unmatched": sum(1 for d in digests if not d["svc"])},
    }
    (data_dir / "index.js").write_text(
        "window.RADAR_INDEX=" + json.dumps(index, ensure_ascii=False, separators=(",", ":")) + ";\n")
    return index["counts"] | {"services_with_items": len(per_service)}


def append_changes(added: list[dict], now: datetime | None = None) -> int:
    """Append a run's new items to data/changes/<date>.md, grouped by service."""
    if not added:
        return 0
    now = now or utcnow()
    cat, sources = Catalog.load(), load_sources()
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in added:
        d = digest_item(item, sources[item["source"]], cat)
        groups[d["svc"][0] if d["svc"] else "_other"].append(d)
    path = DATA_DIR / "changes" / f"{now:%Y-%m-%d}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [] if path.exists() else [f"# AWS Radar · {now:%Y-%m-%d}", ""]
    lines += [f"## Run {now:%H:%M} UTC · {len(added)} new items", ""]
    for sid in sorted(groups, key=lambda k: (k == "_other", k)):
        name = cat.services[sid].name if sid in cat.services else "Not mapped to a service"
        lines.append(f"### {name}")
        lines += [_md_line(d, sources) for d in sorted(groups[sid], key=lambda d: d["d"], reverse=True)]
        lines.append("")
    with path.open("a") as fh:
        fh.write("\n".join(lines) + "\n")
    return len(added)


if __name__ == "__main__":
    print(build())
