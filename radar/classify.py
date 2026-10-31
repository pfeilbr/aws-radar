"""Item -> service ids + change tags. Pure rules, no model calls.

Services come from the strongest signal available:
  1. tags the source attached (What's New product slugs, blog tags, botocore service names)
  2. the source's default `services` in sources.yaml
  3. service names mentioned in the title (and, for social posts, the text)
A child service (EKS Anywhere) also lists its parent (EKS) so the parent page shows it.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache

from radar import CONFIG_DIR
from radar.catalog import Catalog

# Blog tags so broad they would bury a service page; used only when nothing else matches.
GENERIC_TAGS = {"amazon-machine-learning", "aws-govcloud-us"}

# (tag, regex over title + start of summary). First match per tag; several tags may apply.
TAG_RULES: list[tuple[str, re.Pattern]] = [(t, re.compile(p, re.I)) for t, p in [
    ("GA", r"\bgenerally available\b|\bgeneral availability\b|\bnow GA\b"),
    ("preview", r"\b(?:in |public |gated )?preview\b|\bbeta\b"),
    ("region", r"\b(?:now available|expands?|launch(?:es|ed)?|available) in (?:the )?(?:\w+ )?(?:additional |more |new )?"
               r"(?:AWS )?(?:regions?|.*\b(?:region|regions)\b)|\bregional expansion\b|\badditional (?:AWS )?regions\b"),
    ("pricing", r"\bpric(?:e|es|ing)\b|\bcost reduction\b|\bfree tier\b|\bper[- ]second billing\b|\bsavings plans?\b"),
    ("deprecation", r"\bdeprecat|\bend of (?:support|life)\b|\bend-of-(?:support|life)\b|\bretir(?:e|es|ing|ement)\b"
                    r"|\bsunset|\bdiscontinu|\bno longer (?:available|supported)\b"),
    ("security", r"\bCVE-\d{4}-\d+|\bvulnerab|\bsecurity bulletin\b"),
    ("quota", r"\bquotas?\b|\b(?:raises?|increases?) (?:the )?(?:default )?(?:limit|maximum)\b"),
    ("instances", r"\b[a-z]{1,3}\d[a-z0-9-]*\.(?:\d*x?large|metal)\b|\b[A-Z][a-z]?\d[a-zA-Z0-9-]* instances?\b"),
]]

GROUP_TAGS = {"aws-code": "sdk", "community": "community", "social": "social", "aws-media": "media",
              "aws-roadmap": "roadmap"}
ROADMAP_LABEL_TAGS = {"shipped": "shipped", "coming soon": "coming-soon"}
SOURCE_TAGS = {"aws-service-health": "outage", "aws-security-bulletins": "security"}
LAUNCH_SOURCES = {"aws-whats-new", "aws-news-blog"}


def services_for(item: dict, src: dict, cat: Catalog) -> tuple[list[str], list[str]]:
    """(primary, mentioned). Primary: the item is about the service. Mentioned: the service is
    only tagged or named in passing (blog posts tag every service an architecture uses)."""
    primary: list[str] = []
    mentioned: list[str] = []

    def add(bucket: list[str], sid: str | None) -> None:
        if sid and sid not in primary and sid not in bucket:
            bucket.append(sid)

    title_hits = cat.match_text(item["title"])
    if src["type"] == "github-changelog":
        for t in item["tags_raw"]:
            add(primary, cat.match_botocore(t))
    else:
        tagged, generic = [], []
        for t in item["tags_raw"]:
            t = t.split("/")[-1] if t.startswith("general:products/") else t
            if t.startswith("marketing:"):
                continue
            sid = cat.match_name(t)
            if sid:
                (generic if t in GENERIC_TAGS else tagged).append(sid)
        tagged = list(dict.fromkeys(tagged))
        # What's New tags are precise. Blog tags are precise only when there are few of them
        # or the title names the service.
        precise = src["type"] != "aws-blog-api" or len(tagged) <= 2
        for sid in tagged:
            add(primary if precise or sid in title_hits else mentioned, sid)
        for sid in src.get("services") or []:
            add(primary, sid)
        for sid in title_hits:
            add(primary, sid)
        # CloudFormation type names: "AWS::Glue::Job" -> glue
        for ns in re.findall(r"AWS::(\w+)::", item["title"]):
            add(primary, cat.match_botocore(ns.lower()) or cat.match_name(ns))
        if src["group"] in ("social", "community"):
            for sid in cat.match_text(item["summary"][:600]):
                add(mentioned, sid)
        if not primary and not mentioned:
            for sid in generic:
                add(mentioned, sid)
    mentioned = [s for s in mentioned if s not in primary]
    # GovCloud is a partition, not the subject: never let it lead an item.
    if "govcloud" in primary and len(primary) > 1:
        primary.remove("govcloud")
        primary.append("govcloud")
    # Parents after children, so EKS Anywhere items also land on the EKS page.
    for bucket in (primary, mentioned):
        for sid in list(bucket):
            parent = cat.services[sid].parent if sid in cat.services else None
            add(bucket, parent)
    return primary, [s for s in mentioned if s not in primary]


def tags_for(item: dict, src: dict) -> list[str]:
    text = f"{item['title']} {item['summary'][:300]}"
    tags = [tag for tag, rx in TAG_RULES if rx.search(text)]
    if src["id"] in SOURCE_TAGS:
        tags.insert(0, SOURCE_TAGS[src["id"]])
    if src["group"] in GROUP_TAGS:
        tags.append(GROUP_TAGS[src["group"]])
    if src["type"] == "github-issues":
        label = ROADMAP_LABEL_TAGS.get(src.get("label", "").lower())
        if label:
            tags.insert(0, label)
    if src["id"] in LAUNCH_SOURCES and not set(tags) & {"GA", "preview", "region", "deprecation"}:
        tags.append("feature")
    return list(dict.fromkeys(tags))


@lru_cache(maxsize=1)
def _region_patterns() -> list[tuple[re.Pattern, str]]:
    """'Asia Pacific (Tokyo)', 'Tokyo' after a region phrase, or 'ap-northeast-1' -> code."""
    names = json.loads((CONFIG_DIR / "vocab" / "regions.json").read_text())
    pats = []
    for code, name in names.items():
        pats.append((re.compile(rf"(?<![\w-]){re.escape(code)}(?![\w-])"), code))
        pats.append((re.compile(re.escape(name).replace(r"\ ", r"\s+"), re.I), code))
        # "Europe (Spain) and Asia Pacific (Malaysia)" are covered above; also catch the
        # bare city inside a list such as "Asia Pacific (Tokyo, Seoul, and Mumbai)".
        m = re.match(r"(.+) \((.+)\)$", name)
        if m:
            area, city = m.groups()
            pats.append((re.compile(rf"{re.escape(area)}\s*\([^)]*\b{re.escape(city)}\b[^)]*\)", re.I), code))
    return pats


def regions_for(item: dict, src: dict) -> list[str]:
    """Region codes named in launch posts (region expansions). Empty for other sources."""
    if src["id"] not in LAUNCH_SOURCES:
        return []
    text = f"{item['title']} {item['summary']}"
    return sorted({code for rx, code in _region_patterns() if rx.search(text)})
