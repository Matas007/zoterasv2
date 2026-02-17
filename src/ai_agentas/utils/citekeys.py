from __future__ import annotations

import re
import unicodedata


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def make_citekey(author: str | None, year: str | None, title: str | None) -> str:
    a = _slug((author or "").split(",")[0].split(" ")[0]) or "anon"
    y = _slug(year or "")[:4] or "nd"
    t = _slug(title or "")[:12] or "work"
    return f"{a}{y}{t}"

