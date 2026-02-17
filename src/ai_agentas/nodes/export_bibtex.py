from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import bibtexparser
from bibtexparser.bwriter import BibTexWriter
from bibtexparser.bibdatabase import BibDatabase

from ai_agentas.utils.citekeys import make_citekey

from .parse_bibliography import ParsedReference


@dataclass(frozen=True)
class BibtexExport:
    bibtex: str
    citekey_by_index: dict[int, str]


def _guess_entry_type(ref: ParsedReference) -> str:
    """Supaprastinta heuristika: ar tai straipsnis, knyga, ar misc."""
    raw_lower = ref.raw.lower()
    if ref.journal:
        return "article"
    if any(kw in raw_lower for kw in ("book", "knyga", "leidykla", "publisher", "press")):
        return "book"
    if any(kw in raw_lower for kw in ("proceedings", "conference", "konferencija")):
        return "inproceedings"
    if ref.doi or ref.volume:
        return "article"
    return "misc"


def _to_bib_entry(ref: ParsedReference, fallback_index: int) -> tuple[str, dict[str, Any]]:
    entry_type = _guess_entry_type(ref)

    author_list = ref.authors if ref.authors else ([ref.author] if ref.author else ["Anon"])
    author = " and ".join(a for a in author_list if a)
    year = ref.year or "n.d."
    title = ref.title or f"Untitled {fallback_index}"
    citekey = make_citekey(author, year if year != "n.d." else None, title)

    fields: dict[str, Any] = {
        "ENTRYTYPE": entry_type,
        "ID": citekey,
        "title": title,
    }
    if author:
        fields["author"] = author
    if ref.year and ref.year.isdigit():
        fields["year"] = ref.year
    if ref.doi:
        fields["doi"] = ref.doi
    if ref.url:
        fields["url"] = ref.url
    if ref.journal:
        fields["journal"] = ref.journal
    if ref.volume:
        fields["volume"] = ref.volume
    if ref.issue:
        fields["number"] = ref.issue
    if ref.pages:
        fields["pages"] = ref.pages
    if ref.publisher:
        fields["publisher"] = ref.publisher

    return citekey, fields


def export_bibtex(refs: list[ParsedReference]) -> BibtexExport:
    db = BibDatabase()
    citekey_by_index: dict[int, str] = {}
    entries = []
    used: set[str] = set()

    for i, ref in enumerate(refs):
        ck, ent = _to_bib_entry(ref, fallback_index=i + 1)
        base = ck
        suffix = 0
        while ck in used:
            suffix += 1
            ck = f"{base}{suffix}"
            ent["ID"] = ck
        used.add(ck)
        citekey_by_index[i] = ck
        entries.append(ent)

    db.entries = entries
    writer = BibTexWriter()
    writer.indent = "  "
    bib = bibtexparser.dumps(db, writer)
    return BibtexExport(bibtex=bib, citekey_by_index=citekey_by_index)
