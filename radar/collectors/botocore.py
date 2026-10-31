"""botocore CHANGELOG.rst: one item per `api-change` line, dated from PyPI upload times."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from radar.collectors import Context
from radar.store import make_item, utcnow

_SECTION = re.compile(r"^(\d+\.\d+\.\d+)\n=+\n(.*?)(?=^\d+\.\d+\.\d+\n=+\n|\Z)", re.M | re.S)
_CHANGE = re.compile(r"^\* api-change:``([^`]+)``:\s*(.+?)(?=^\* |\Z)", re.M | re.S)
PYPI_SIMPLE = "https://pypi.org/simple/botocore/"


def _vkey(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def _release_dates(ctx: Context) -> dict[str, str]:
    r = ctx.fetcher.get(PYPI_SIMPLE, headers={"Accept": "application/vnd.pypi.simple.v1+json"})
    r.raise_for_status()
    dates: dict[str, str] = {}
    for f in r.json()["files"]:
        m = re.match(r"botocore-(\d+\.\d+\.\d+)[.-]", f["filename"])
        if m and f.get("upload-time"):
            dates.setdefault(m.group(1), f["upload-time"])
    return dates


def collect(src: dict, ctx: Context) -> list[dict]:
    r = ctx.fetcher.get_conditional(src["url"], ctx.state)
    if r is None:
        return []
    sections = [(v, body) for v, body in _SECTION.findall(r.text)]
    last = ctx.state.get("last_version")
    if last:
        sections = [(v, b) for v, b in sections if _vkey(v) > _vkey(last)]
    if not sections:
        return []
    dates = _release_dates(ctx)
    cutoff = utcnow() - timedelta(days=src.get("backfill_days", 90))
    items = []
    for version, body in sections:
        published = (datetime.fromisoformat(dates[version].replace("Z", "+00:00"))
                     if version in dates else utcnow())
        if not last and published < cutoff:
            continue
        anchor = version.replace(".", "")
        for service, desc in _CHANGE.findall(body):
            desc = " ".join(desc.split())
            desc = re.sub(r"^\[``botocore``\]\s*", "", desc)
            items.append(make_item(
                source=src["id"], key=f"{version}:{service}:{desc}",
                url=f"https://github.com/boto/botocore/blob/develop/CHANGELOG.rst#{anchor}",
                title=f"{service}: {desc}", summary=desc,
                published=published.astimezone(UTC), tags_raw=[service],
                extra={"version": version, "sdk_service": service},
            ))
    ctx.state["last_version"] = max((v for v, _ in sections), key=_vkey)
    return items
