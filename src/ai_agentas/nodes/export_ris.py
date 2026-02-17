from __future__ import annotations

from .parse_bibliography import ParsedReference


_TYPE_MAP = {
    "article": "JOUR",
    "book": "BOOK",
    "inproceedings": "CONF",
    "incollection": "CHAP",
    "phdthesis": "THES",
    "mastersthesis": "THES",
    "misc": "GEN",
}


def _guess_ris_type(ref: ParsedReference) -> str:
    raw_lower = ref.raw.lower()
    if ref.journal:
        return "JOUR"
    if any(kw in raw_lower for kw in ("book", "knyga", "leidykla", "publisher", "press")):
        return "BOOK"
    if any(kw in raw_lower for kw in ("proceedings", "conference", "konferencija")):
        return "CONF"
    if ref.doi or ref.volume:
        return "JOUR"
    return "GEN"


def ref_to_ris(ref: ParsedReference) -> str:
    """Konvertuoja viena ParsedReference i RIS formato bloka."""
    lines: list[str] = []
    lines.append(f"TY  - {_guess_ris_type(ref)}")
    author_list = ref.authors if ref.authors else ([ref.author] if ref.author else [])
    if author_list:
        for a in author_list:
            a = a.strip()
            if a:
                lines.append(f"AU  - {a}")
    if ref.year:
        lines.append(f"PY  - {ref.year}")
    if ref.title:
        lines.append(f"TI  - {ref.title}")
    if ref.journal:
        lines.append(f"JO  - {ref.journal}")
    if ref.volume:
        lines.append(f"VL  - {ref.volume}")
    if ref.issue:
        lines.append(f"IS  - {ref.issue}")
    if ref.pages:
        parts = ref.pages.replace("--", "-").split("-", 1)
        lines.append(f"SP  - {parts[0].strip()}")
        if len(parts) > 1:
            lines.append(f"EP  - {parts[1].strip()}")
    if ref.publisher:
        lines.append(f"PB  - {ref.publisher}")
    if ref.doi:
        lines.append(f"DO  - {ref.doi}")
    if ref.url:
        lines.append(f"UR  - {ref.url}")
    lines.append("ER  - ")
    return "\n".join(lines)


def export_ris(refs: list[ParsedReference]) -> str:
    """Eksportuoja visus saltinuis i RIS formata (vienas string)."""
    blocks = [ref_to_ris(r) for r in refs]
    return "\n\n".join(blocks) + "\n"
