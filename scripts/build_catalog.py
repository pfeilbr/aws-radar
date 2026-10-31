"""Build config/services.yaml and site/assets/icons/ from the AWS Architecture Icons package.

    uv run scripts/build_catalog.py                    # download the current package
    uv run scripts/build_catalog.py --zip pkg.zip      # use a package already downloaded
    uv run scripts/build_catalog.py --report           # also list unmatched vocabulary

The icons page (aws.amazon.com/architecture/icons/) links one zip per quarterly release.
Only the 64px service SVGs and category SVGs are copied. Hand edits go in
config/service_overrides.yaml, never in the generated services.yaml.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import zipfile
from pathlib import Path

import httpx
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from radar import CONFIG_DIR, SITE_DIR  # noqa: E402
from radar.catalog import Catalog, Service, norm  # noqa: E402

ICONS_PAGE = "https://aws.amazon.com/architecture/icons/"
ICON_DIR = SITE_DIR / "assets" / "icons"

CATEGORIES = {
    # icon-package folder -> (category id, display name)
    "Analytics": ("analytics", "Analytics"),
    "Application-Integration": ("application-integration", "Application Integration"),
    "Artificial-Intelligence": ("ai", "Artificial Intelligence"),
    "Blockchain": ("blockchain", "Blockchain"),
    "Business-Applications": ("business-applications", "Business Applications"),
    "Cloud-Financial-Management": ("cloud-financial-management", "Cloud Financial Management"),
    "Compute": ("compute", "Compute"),
    "Containers": ("containers", "Containers"),
    "Customer-Enablement": ("customer-enablement", "Customer Enablement"),
    "Databases": ("databases", "Databases"),
    "Developer-Tools": ("developer-tools", "Developer Tools"),
    "End-User-Computing": ("end-user-computing", "End User Computing"),
    "Front-End-Web-Mobile": ("front-end-web-mobile", "Front-End Web & Mobile"),
    "Games": ("games", "Games"),
    "General-Icons": ("general", "General"),
    "Internet-of-Things": ("iot", "Internet of Things"),
    "Management-Tools": ("management-governance", "Management & Governance"),
    "Media-Services": ("media", "Media Services"),
    "Migration-Modernization": ("migration", "Migration & Modernization"),
    "Networking-Content-Delivery": ("networking", "Networking & Content Delivery"),
    "Quantum-Technologies": ("quantum", "Quantum Technologies"),
    "Satellite": ("satellite", "Satellite"),
    "Security-Identity": ("security", "Security, Identity & Compliance"),
    "Storage": ("storage", "Storage"),
}
CATEGORY_ICON_ALIASES = {"Management-Tools": "Management-Governance", "Security-Identity": "Security-Identity-Compliance"}


def slug(text: str) -> str:
    return norm(text).replace(" ", "-")


def download_package() -> bytes:
    ua = {"User-Agent": "Mozilla/5.0 (aws-radar catalog builder)"}
    page = httpx.get(ICONS_PAGE, headers=ua, follow_redirects=True, timeout=60).text
    links = sorted(set(re.findall(r"https://[^\"']+/Icon-package_[^\"']+\.zip", page)))
    if not links:
        sys.exit("no Icon-package zip link found on " + ICONS_PAGE)
    print("downloading", links[-1])
    return httpx.get(links[-1], headers=ua, follow_redirects=True, timeout=300).content


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--zip", type=Path, help="icon package zip already on disk")
    ap.add_argument("--report", action="store_true", help="print unmatched vocabulary")
    args = ap.parse_args()

    data = args.zip.read_bytes() if args.zip else download_package()
    zf = zipfile.ZipFile(io.BytesIO(data))
    overrides = yaml.safe_load((CONFIG_DIR / "service_overrides.yaml").read_text())
    by_default_id = overrides.get("services") or {}
    drop = set(overrides.get("drop") or [])

    (ICON_DIR / "services").mkdir(parents=True, exist_ok=True)
    (ICON_DIR / "categories").mkdir(parents=True, exist_ok=True)

    services: dict[str, dict] = {}
    used: set[str] = set()
    categories: dict[str, dict] = {}
    for info in zf.infolist():
        p = info.filename
        if "__MACOSX" in p or not p.endswith(".svg"):
            continue
        m = re.search(r"Architecture-Service-Icons_\d+/Arch_([^/]+)/64/Arch_(.+)_64\.svg$", p)
        if m:
            folder, stem = m.groups()
            if folder not in CATEGORIES:
                print("unknown category folder", folder, file=sys.stderr)
                continue
            name = stem.replace("-", " ").replace(" & ", " & ")
            default_id = slug(name)
            if default_id in drop or stem in drop:
                continue
            ov = by_default_id.get(default_id, {})
            used.add(default_id)
            sid = ov.get("id", default_id)
            if sid in services:  # same icon listed under two categories: keep the first
                continue
            (ICON_DIR / "services" / f"{sid}.svg").write_bytes(zf.read(info))
            services[sid] = {
                "id": sid,
                "name": ov.get("name", name),
                "short": ov.get("short", re.sub(r"^(Amazon|AWS)\s+", "", ov.get("name", name))),
                "category": ov.get("category", CATEGORIES[folder][0]),
                "icon": f"assets/icons/services/{sid}.svg",
                "aliases": ov.get("aliases", []),
                "keywords": ov.get("keywords", []),
                "parent": ov.get("parent"),
            }
            continue
        m = re.search(r"Category-Icons_\d+/Arch-Category_64/Arch-Category_(.+)_64\.svg$", p)
        if m:
            stem = m.group(1)
            folder = next((f for f, a in CATEGORY_ICON_ALIASES.items() if a == stem), stem)
            if folder in CATEGORIES:
                cid, cname = CATEGORIES[folder]
                (ICON_DIR / "categories" / f"{cid}.svg").write_bytes(zf.read(info))
                categories[cid] = {"name": cname, "icon": f"assets/icons/categories/{cid}.svg"}

    for cid, cname in CATEGORIES.values():
        categories.setdefault(cid, {"name": cname, "icon": None})

    for extra in overrides.get("extra") or []:
        services[extra["id"]] = {"aliases": [], "keywords": [], "parent": None,
                                 "short": re.sub(r"^(Amazon|AWS)\s+", "", extra["name"]),
                                 "icon": None, **extra}

    missing = sorted(set(by_default_id) - used)
    if missing:
        print("overrides that matched no icon:", ", ".join(missing), file=sys.stderr)

    for s in services.values():
        if s["parent"] and s["parent"] not in services:
            print(f"{s['id']}: unknown parent {s['parent']}", file=sys.stderr)

    out = {
        "generated_by": "scripts/build_catalog.py (edit config/service_overrides.yaml instead)",
        "categories": dict(sorted(categories.items())),
        "services": sorted(services.values(), key=lambda s: s["id"]),
    }
    (CONFIG_DIR / "services.yaml").write_text(yaml.safe_dump(out, sort_keys=False, width=100))
    print(f"{len(services)} services, {len(categories)} categories -> config/services.yaml")

    if args.report:
        cat = Catalog([Service(**s) for s in out["services"]], out["categories"])
        slugs = json.loads((CONFIG_DIR / "vocab" / "whats-new-slugs.json").read_text())
        un = [s for s in slugs if not cat.match_name(s)]
        print(f"\nWhat's New slugs unmatched: {len(un)}/{len(slugs)}\n  " + " ".join(un))
        un = [s for s in cat.botocore_names if not cat.match_botocore(s)]
        print(f"\nbotocore services unmatched: {len(un)}/{len(cat.botocore_names)}\n  " + " ".join(un))
    return 0


if __name__ == "__main__":
    sys.exit(main())
