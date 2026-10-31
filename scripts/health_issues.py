"""Open a GitHub issue for each source failing for more than a day; close it on recovery.

Run by .github/workflows/update.yml after each update (needs `gh` and GH_TOKEN with
issues: write). Issues carry the `source-failing` label and the source id in the title.

    uv run scripts/health_issues.py            # act
    uv run scripts/health_issues.py --dry-run  # print what it would do
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
LABEL = "source-failing"
GRACE = timedelta(hours=24)


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], cwd=ROOT, check=True, text=True, capture_output=True).stdout


def ts(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sources = {s["id"]: s for s in yaml.safe_load((ROOT / "config" / "sources.yaml").read_text())["sources"]}
    now = datetime.now(UTC)
    failing: dict[str, dict] = {}
    for sid, src in sources.items():
        if not src.get("enabled"):
            continue
        p = ROOT / "data" / "state" / f"{sid}.json"
        st = json.loads(p.read_text()) if p.exists() else {}
        err = st.get("last_error") or {}
        last_ok = ts(st.get("last_success"))
        if err and (not last_ok or ts(err["at"]) > last_ok) and (not last_ok or now - last_ok > GRACE):
            failing[sid] = {"error": err.get("error", ""), "since": st.get("last_success") or "never"}

    open_issues = json.loads(gh("issue", "list", "--label", LABEL, "--state", "open",
                                "--json", "number,title", "--limit", "100")) if not args.dry_run else []
    by_source = {i["title"].split("`")[1]: i["number"] for i in open_issues if i["title"].count("`") >= 2}

    if failing and not args.dry_run:
        subprocess.run(["gh", "label", "create", LABEL, "--color", "B42318",
                        "--description", "A collector has been failing for over a day"],
                       cwd=ROOT, capture_output=True)  # ignore "already exists"
    for sid, info in failing.items():
        if sid in by_source:
            continue
        title = f"Source `{sid}` failing since {info['since'][:16]}"
        body = (f"`{sid}` ({sources[sid]['name']}) has not succeeded for more than "
                f"{int(GRACE.total_seconds() // 3600)} hours.\n\nLast error:\n\n```\n{info['error']}\n```\n\n"
                f"State: `data/state/{sid}.json`. Check it with "
                f"`uv run scripts/validate_sources.py --only {sid}`.\n\n"
                "This issue closes itself when the source recovers.")
        print("open:", title)
        if not args.dry_run:
            gh("issue", "create", "--title", title, "--label", LABEL, "--body", body)
    for sid, number in by_source.items():
        if sid not in failing:
            print(f"close: #{number} ({sid} recovered)")
            if not args.dry_run:
                gh("issue", "close", str(number), "--comment", f"`{sid}` is succeeding again.")
    if not failing and not by_source:
        print("all sources healthy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
