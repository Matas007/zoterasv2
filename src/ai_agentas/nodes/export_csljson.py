from __future__ import annotations

import json
from typing import Any

from ai_agentas.utils.citekeys import make_citekey

from .parse_bibliography import ParsedReference


def _guess_csl_type(ref: ParsedReference) -> str:
    raw_lower = ref.raw.lower()
    if ref.journal:
        return "article-journal"
    if any(kw in raw_lower for kw in ("book", "knyga", "leidykla", "publisher", "press")):
        return "book"
    if any(kw in raw_lower for kw in ("proceedings", "conference", "konferencija")):
        return "paper-conference"
    return "article"


def _parse_author_names(authors: list[str], author_str: str | None) -> list[dict[str, str]]:
    source = authors if authors else ([author_str] if author_str else [])
    if not source:
        return [{"literal": "Anon"}]
    out = []
    for part in source:
        part = part.strip()
        if not part:
            continue
        words = part.split()
        if len(words) >= 2:
            out.append({"family": words[0], "given": " ".join(words[1:])})
        elif words:
            out.append({"literal": words[0]})
    return out if out else [{"literal": "Anon"}]


def ref_to_csl(ref: ParsedReference, index: int) -> dict[str, Any]:
    """Konvertuoja viena ParsedReference i CSL-JSON objekta."""
    author = ref.author or "Anon"
    year = ref.year or "n.d."
    title = ref.title or f"Untitled {index}"
    citekey = make_citekey(author, year if year != "n.d." else None, title)

    item: dict[str, Any] = {
        "id": citekey,
        "type": _guess_csl_type(ref),
        "title": title,
        "author": _parse_author_names(ref.authors, ref.author),
    }
    if ref.year and ref.year.isdigit():
        item["issued"] = {"date-parts": [[int(ref.year)]]}
    if ref.journal:
        item["container-title"] = ref.journal
    if ref.volume:
        item["volume"] = ref.volume
    if ref.issue:
        item["issue"] = ref.issue
    if ref.pages:
        item["page"] = ref.pages
    if ref.publisher:
        item["publisher"] = ref.publisher
    if ref.doi:
        item["DOI"] = ref.doi
    if ref.url:
        item["URL"] = ref.url
    return item


def export_csljson(refs: list[ParsedReference]) -> str:
    """Eksportuoja visus saltinius i CSL-JSON formata."""
    items = [ref_to_csl(r, i + 1) for i, r in enumerate(refs)]
    return json.dumps(items, indent=2, ensure_ascii=False)
