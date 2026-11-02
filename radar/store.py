"""Append-only raw item store and per-source state.

    data/raw/<source>/<YYYY-MM>.jsonl   one item per line, keyed by published month
    data/state/<source>.json            HTTP validators, cursors, last run time

Existing lines are never rewritten. An item already stored (same id) is skipped on write.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path

from radar import DATA_DIR

RAW_DIR = DATA_DIR / "raw"
STATE_DIR = DATA_DIR / "state"


def _ends_with_newline(path: Path) -> bool:
    with path.open("rb") as fh:
        fh.seek(-1, os.SEEK_END)
        return fh.read(1) == b"\n"


def _read_jsonl(path: Path) -> Iterator[dict]:
    """Yield each item; skip (and report) a line that does not parse, such as a write cut
    short by a killed run, so one bad line cannot stop every build. The line stays on disk."""
    with path.open() as fh:
        for n, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                print(f"warning: {path}:{n}: unreadable line skipped ({e})", file=sys.stderr)


def utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_id(source: str, key: str) -> str:
    return f"{source}:{hashlib.sha1(key.encode()).hexdigest()[:16]}"


def make_item(*, source: str, key: str, url: str, title: str, published: datetime,
              summary: str = "", authors: list[str] | None = None,
              tags_raw: list[str] | None = None, extra: dict | None = None) -> dict:
    return {
        "id": make_id(source, key),
        "source": source,
        "url": url,
        "title": title.strip(),
        "summary": summary[:1500],
        "published": iso(published),
        "fetched": iso(utcnow()),
        "authors": authors or [],
        "tags_raw": tags_raw or [],
        "extra": extra or {},
    }


class RawStore:
    def __init__(self, root: Path = RAW_DIR):
        self.root = root
        self._seen: dict[str, set[str]] = {}

    def seen(self, source: str) -> set[str]:
        if source not in self._seen:
            ids = set()
            for f in (self.root / source).glob("*.jsonl"):
                ids.update(it["id"] for it in _read_jsonl(f))
            self._seen[source] = ids
        return self._seen[source]

    def add(self, items: Iterable[dict]) -> list[dict]:
        """Append items not stored yet; return the ones actually added."""
        added = []
        by_file: dict[Path, list[dict]] = {}
        for it in items:
            seen = self.seen(it["source"])
            if it["id"] in seen:
                continue
            seen.add(it["id"])
            month = it["published"][:7]
            by_file.setdefault(self.root / it["source"] / f"{month}.jsonl", []).append(it)
            added.append(it)
        for path, rows in by_file.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            rows.sort(key=lambda r: (r["published"], r["id"]))
            with path.open("a") as fh:
                if path.stat().st_size and not _ends_with_newline(path):
                    fh.write("\n")  # never glue a new item onto a line a killed run cut short
                for r in rows:
                    fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
        return added

    def all_items(self) -> Iterator[dict]:
        for f in sorted(self.root.glob("*/*.jsonl")):
            yield from _read_jsonl(f)


def load_state(source: str) -> dict:
    p = STATE_DIR / f"{source}.json"
    return json.loads(p.read_text()) if p.exists() else {}


def save_state(source: str, state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    # Write then rename: a run killed mid-write leaves the old state, never half a JSON file.
    path = STATE_DIR / f"{source}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)
