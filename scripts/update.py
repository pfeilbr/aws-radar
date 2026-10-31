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
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from radar import ROOT  # noqa: E402
from radar.build import build  # noqa: E402
from radar.collect import run  # noqa: E402
from radar.store import utcnow  # noqa: E402


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, text=True, capture_output=True)


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
    if not args.build_only:
        print("collecting", file=sys.stderr)
        added, report = run(args.only, force=args.force, backfill=args.backfill)
    stats = build()
    errors = [r for r in report if r.get("status") == "error"]
    print(f"added {len(added)} items; {stats}; {len(errors)} source errors", file=sys.stderr)

    if args.commit:
        git("add", "data")
        # State (ETags, last-run times) changes every run; only commit when items arrived.
        if subprocess.run(["git", "diff", "--cached", "--quiet", "--", "data/raw"], cwd=ROOT).returncode == 0:
            git("reset", "-q")
            print("no new items, nothing committed", file=sys.stderr)
        else:
            per_source = ", ".join(f"{r['id']} +{r['added']}" for r in report if r.get("added"))
            msg = f"data: update {utcnow():%Y-%m-%d %H:%M}Z (+{len(added)} items)"
            body = per_source or "state only"
            if errors:
                body += "\n\nerrors: " + ", ".join(r["id"] for r in errors)
            git("commit", "-m", msg, "-m", body)
            print(msg, file=sys.stderr)
            if args.push:
                # Someone may have pushed since checkout. Raw files are per source and
                # append-only, so only generated files can conflict: take ours, then
                # regenerate them from the merged raw data.
                git("pull", "--rebase", "-q", "-X", "theirs")
                build()
                git("add", "data")
                if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode:
                    git("commit", "-q", "--amend", "--no-edit")
                git("push")
            if os.environ.get("GITHUB_OUTPUT"):
                with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
                    fh.write("committed=true\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
