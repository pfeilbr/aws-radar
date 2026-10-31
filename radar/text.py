"""Turn source HTML/marketing copy into short plain text for the digest."""

from __future__ import annotations

import html
import re

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

# Openers that carry no information for an expert reader. Order matters: longest first.
_FILLER = [
    r"(?:today,?\s+)?(?:we(?:'re| are)|aws is|amazon is)\s+(?:excited|pleased|thrilled|happy|delighted)\s+to\s+"
    r"(?:announce|share|introduce|launch)\s+(?:that\s+)?(?:the\s+)?(?:general availability of\s+)?",
    r"(?:today,?\s+)?we(?:'re| are)\s+announcing\s+(?:that\s+)?",
    r"^today,?\s+",
    r"^(?:starting|beginning)\s+today,?\s+",
    r"^(?:we(?:'re| are)\s+)?(?:excited|pleased)\s+to\s+announce\s+",
]
_FILLER_RX = [re.compile(p, re.I) for p in _FILLER]


def html_to_text(value: str | None) -> str:
    if not value:
        return ""
    text = _TAG.sub(" ", value)
    text = html.unescape(text).replace("\xa0", " ")
    return _WS.sub(" ", text).strip()


def strip_filler(text: str) -> str:
    for rx in _FILLER_RX:
        text = rx.sub("", text, count=1).strip()
    return text[:1].upper() + text[1:] if text else text


def first_sentences(text: str, limit: int = 240) -> str:
    """Whole sentences up to `limit` chars; hard-truncate with an ellipsis if one is longer."""
    text = strip_filler(text)
    if len(text) <= limit:
        return text
    out = ""
    for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z])", text):
        if len(out) + len(sentence) + 1 > limit:
            break
        out = f"{out} {sentence}".strip()
    return out or text[: limit - 1].rstrip() + "…"
