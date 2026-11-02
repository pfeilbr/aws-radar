"""Config sanity: catches a broken sources.yaml or catalog before the scheduled job does."""

import re

import pytest
import yaml

from radar import CONFIG_DIR, SITE_DIR
from radar.collect import parse_cadence
from radar.collectors import registry

SOURCES = yaml.safe_load((CONFIG_DIR / "sources.yaml").read_text())
GROUPS = {"aws-official", "aws-code", "aws-roadmap", "aws-media", "community", "social"}


def test_source_ids_unique():
    ids = [s["id"] for s in SOURCES["sources"]]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("src", SOURCES["sources"], ids=lambda s: s["id"])
def test_source_entry(src):
    assert re.fullmatch(r"[a-z0-9-]+", src["id"])
    assert src["name"] and src["group"] in GROUPS
    assert src["type"] in registry()
    if src.get("enabled") or "url" in src:   # disabled stubs (x-following) may lack a URL
        assert src["url"].startswith("https://")
    parse_cadence(src.get("cadence"))
    # Secrets come from the environment; the YAML only names the variable.
    if "auth_env" in src:
        assert re.fullmatch(r"[A-Z][A-Z0-9_]*", src["auth_env"])
    assert not {"token", "secret", "password", "api_key"} & set(src)


def test_catalog_ids_parents_and_icons(cat):
    for s in cat.services.values():
        assert re.fullmatch(r"[a-z0-9-]+", s.id), s.id
        assert s.parent is None or s.parent in cat.services, f"{s.id}: unknown parent {s.parent}"
        if s.icon:
            assert (SITE_DIR / s.icon).is_file(), f"{s.id}: missing {s.icon}"
        assert s.category in cat.categories, f"{s.id}: unknown category {s.category}"


def test_catalog_keywords_compile(cat):
    for s in cat.services.values():
        for kw in s.keywords:
            re.compile(kw)
