"""X (Twitter) posts from followed accounts. Needs a paid API token; see docs/sources.md."""

from __future__ import annotations

import os

from radar.collectors import Context, Skip


def collect(src: dict, ctx: Context) -> list[dict]:
    if not os.environ.get(src.get("auth_env", "X_BEARER_TOKEN")):
        raise Skip(f"set {src.get('auth_env')} to collect from X")
    raise Skip("X collector not implemented yet")
