"""Collect from every due source, rebuild digests and site data, optionally commit.

    uv run scripts/update.py                     # collect due sources, rebuild
    uv run scripts/update.py --force             # ignore cadence, poll everything
    uv run scripts/update.py --backfill          # go further back (first run does this anyway)
    uv run scripts/update.py --only aws-blogs    # one source
    uv run scripts/update.py --build-only        # rebuild from data/raw, no network
    uv run scripts/update.py --commit [--push]   # git commit data/ (and push)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from radar import ROOT  # noqa: E402
from radar.build import build  # noqa: E402
from radar.collect import run  # noqa: E402
from radar.store import utcnow  # noqa: E402


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, text=True, capture_output=True)


def push_with_rebase(attempts: int = 3) -> None:
    """Push, rebasing onto whatever landed meanwhile. Raw files are per source and
    append-only, so only generated files can conflict: take ours, then regenerate them
    from the merged raw data. Retries when another push wins the race in between."""
    for attempt in range(1, attempts + 1):
        git("pull", "--rebase", "-q", "-X", "theirs")
        build()
        git("add", "data")
        if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode:
            git("commit", "-q", "--amend", "--no-edit")
        try:
            git("push")
            return
        except subprocess.CalledProcessError as e:
            if attempt == attempts:
                raise
            print(f"push rejected ({e.stderr.strip()[:120]}), retrying", file=sys.stderr)
            time.sleep(5 * attempt)


def write_step_summary(report: list[dict], added: int, stats: dict) -> None:
    """Per-source table on the GitHub Actions run page (no-op elsewhere)."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    lines = [f"### +{added} items · {stats.get('items', 0):,} total", "",
             "| source | status | fetched | added | note |", "| --- | --- | ---: | ---: | --- |"]
    for r in report:
        if r.get("status") == "not due":
            continue
        note = str(r.get("note", "")).replace("|", "\\|")
        lines.append(f"| {r['id']} | {r['status']} | {r.get('fetched', '')} | {r.get('added', '')} | {note} |")
    skipped = sum(1 for r in report if r.get("status") == "not due")
    lines += ["", f"{skipped} sources not due this run."]
    with open(path, "a") as fh:
        fh.write("\n".join(lines) + "\n")


def failing_sources() -> set[str]:
    """Sources whose latest outcome is an error (shown on the site's #/sources page)."""
    out = set()
    for f in (ROOT / "data" / "state").glob("*.json"):
        st = json.loads(f.read_text())
        err = st.get("last_error") or {}
        if err and err.get("at", "") >= (st.get("last_success") or ""):
            out.add(f.stem)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--build-only", action="store_true")
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--push", action="store_true")
    args = ap.parse_args()

    added, report = [], []
    failing_before = failing_sources()
    if not args.build_only:
        print("collecting", file=sys.stderr)
        added, report = run(args.only, force=args.force, backfill=args.backfill)
    stats = build()
    errors = [r for r in report if r.get("status") == "error"]
    print(f"added {len(added)} items; {stats}; {len(errors)} source errors", file=sys.stderr)
    write_step_summary(report, len(added), stats)

    if args.commit:
        git("add", "data")
        # State (ETags, last-run times) changes every run. Commit only when items arrived or
        # a source started or stopped failing, so the site's health page stays truthful.
        failing_after = failing_sources()
        new_items = subprocess.run(["git", "diff", "--cached", "--quiet", "--", "data/raw"], cwd=ROOT).returncode != 0
        health_changed = failing_after != failing_before
        if not new_items and not health_changed:
            git("reset", "-q")
            print("no new items, nothing committed", file=sys.stderr)
        else:
            per_source = ", ".join(f"{r['id']} +{r['added']}" for r in report if r.get("added"))
            if new_items:
                msg = f"data: update {utcnow():%Y-%m-%d %H:%M}Z (+{len(added)} items)"
            else:
                msg = f"data: source health {utcnow():%Y-%m-%d %H:%M}Z"
            body = per_source or "no new items"
            if health_changed:
                body += ("\n\nnow failing: " + (", ".join(sorted(failing_after)) or "none")
                         + "\nrecovered: " + (", ".join(sorted(failing_before - failing_after)) or "none"))
            if errors:
                body += "\n\nerrors: " + ", ".join(r["id"] for r in errors)
            git("commit", "-m", msg, "-m", body)
            print(msg, file=sys.stderr)
            if args.push:
                push_with_rebase()
            if os.environ.get("GITHUB_OUTPUT"):
                with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
                    fh.write("committed=true\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
