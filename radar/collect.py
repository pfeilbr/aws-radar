"""Run collectors for every enabled, due source and append new items to data/raw/."""

from __future__ import annotations

import re
import sys
import traceback
from datetime import datetime, timedelta

import httpx
import yaml

from radar import CONFIG_DIR
from radar.collectors import Context, Skip, registry
from radar.http import Fetcher
from radar.store import RawStore, iso, load_state, save_state, utcnow


def parse_cadence(text: str) -> timedelta:
    m = re.fullmatch(r"(\d+)([mhd])", text or "24h")
    n, unit = int(m.group(1)), m.group(2)
    return {"m": timedelta(minutes=n), "h": timedelta(hours=n), "d": timedelta(days=n)}[unit]


def run(only: list[str] | None = None, force: bool = False, backfill: bool = False) -> tuple[list[dict], list[dict]]:
    """Returns (added items, per-source report rows)."""
    cfg = yaml.safe_load((CONFIG_DIR / "sources.yaml").read_text())
    fetcher = Fetcher(cfg["defaults"])
    collectors = registry()
    store = RawStore()
    now = utcnow()
    added_all, report = [], []

    for src in cfg["sources"]:
        if only and src["id"] not in only:
            continue
        if not src.get("enabled") and not only:
            continue
        state = load_state(src["id"])
        last = state.get("last_success")
        # Allow 10 minutes of slack so a 6h cron does not skip a 6h source by seconds.
        due = (not last or now - datetime.fromisoformat(last.replace("Z", "+00:00"))
               >= parse_cadence(src.get("cadence")) - timedelta(minutes=10))
        if not (due or force or backfill):
            report.append({"id": src["id"], "status": "not due"})
            continue
        ctx = Context(fetcher=fetcher, state=state, seen=store.seen(src["id"]),
                      backfill=backfill or not last)
        row = {"id": src["id"]}
        try:
            items = collectors[src["type"]](src, ctx)
            added = store.add(items)
            added_all += added
            state["last_success"] = iso(now)
            state.pop("last_error", None)
            row |= {"status": "ok", "fetched": len(items), "added": len(added)}
        except Skip as e:
            row |= {"status": "skipped", "note": str(e)}
        except Exception as e:  # noqa: BLE001 - one broken source must not stop the run
            state["last_error"] = {"at": iso(now), "error": f"{type(e).__name__}: {e}"[:300]}
            row |= {"status": "error", "note": f"{type(e).__name__}: {e}"[:160]}
            if not isinstance(e, httpx.HTTPError):
                traceback.print_exc(file=sys.stderr)
        state["last_run"] = iso(now)
        save_state(src["id"], state)
        report.append(row)
        print(f"  {row['id']:<26} {row['status']:<8} "
              f"+{row.get('added', 0):<5} {row.get('note', '')}", file=sys.stderr)
    return added_all, report
