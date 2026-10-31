"""AWS Radar: deterministic collectors, classifier and static site builder."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
SITE_DIR = ROOT / "site"

# Public URL of the GitHub Pages site (used for absolute links in Atom feeds).
SITE_URL = "https://pfeilbr.github.io/aws-radar/"
