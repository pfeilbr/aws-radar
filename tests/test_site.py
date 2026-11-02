"""The static site's Content-Security-Policy must keep allowing the page's own inline script."""

import base64
import hashlib
import re

from radar import SITE_DIR


def test_csp_hash_matches_inline_script():
    html = (SITE_DIR / "index.html").read_text()
    csp = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', html).group(1)
    for body in re.findall(r"<script>(.*?)</script>", html, re.S):
        digest = base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
        assert f"'sha256-{digest}'" in csp, "inline script changed: update its hash in the CSP"


def test_no_inline_event_handlers():
    # CSP blocks onclick="..." attributes; the app must bind events in app.js instead.
    for name in ("index.html", "app.js"):
        assert not re.search(r"\son[a-z]+=[\"']", (SITE_DIR / name).read_text()), name
