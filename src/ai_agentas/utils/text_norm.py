from __future__ import annotations

import re
from dataclasses import dataclass


_WS_RE = re.compile(r"\s+")


def norm_ws(s: str) -> str:
    """Normalizuoja whitespace (naudinga palyginimui)."""
    return _WS_RE.sub(" ", (s or "").strip())


def looks_like_heading(line: str) -> bool:
    l = norm_ws(line).lower()
    return l in {
        "literatūra",
        "literaturos sarasas",
        "literatūros sąrašas",
        "šaltiniai",
        "saltiniai",
        "references",
        "bibliography",
        "literature",
        "works cited",
    }


def split_lines(text: str) -> list[str]:
    return [ln.rstrip("\n") for ln in (text or "").splitlines()]


def join_lines(lines: list[str]) -> str:
    return "\n".join(lines)


@dataclass(frozen=True)
class BibliographySplit:
    body_text: str
    bibliography_text: str
    bibliography_start_line: int | None

