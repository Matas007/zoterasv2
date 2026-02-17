from __future__ import annotations

import re

from .text_norm import BibliographySplit, looks_like_heading, norm_ws, split_lines, join_lines


_BIB_ITEM_BULLET_RE = re.compile(r"^\s*([\[\(]?\d+[\]\)]\.?|\-\s+|\u2022\s+)\s+")


def _is_bib_item_like(line: str) -> bool:
    """Heuristika: ar eilutė panaši į bibliografijos įrašą."""
    l = norm_ws(line)
    if not l:
        return False
    if _BIB_ITEM_BULLET_RE.match(line):
        return True
    # Autorius, metai...
    if re.search(r"\b(19|20)\d{2}\b", l) and ("," in l or "." in l):
        return True
    # DOI / URL
    if "doi:" in l.lower() or "http://" in l.lower() or "https://" in l.lower():
        return True
    return False


def split_bibliography(text: str) -> BibliographySplit:
    """
    Bando atskirti dokumento pagrindinį tekstą nuo literatūros sąrašo.

    Strategija:
    - ieškome antraščių (References/Literatūra/...) nuo galo
    - jei nėra, ieškome „bibliografijos zonos“ gale, kur daug bib-item eilučių
    """
    lines = split_lines(text)
    if not lines:
        return BibliographySplit(body_text="", bibliography_text="", bibliography_start_line=None)

    # 1) antraštė nuo galo
    for i in range(len(lines) - 1, -1, -1):
        if looks_like_heading(lines[i]):
            bib = join_lines(lines[i + 1 :]).strip()
            body = join_lines(lines[:i]).rstrip()
            return BibliographySplit(body_text=body, bibliography_text=bib, bibliography_start_line=i + 1)

    # 2) heuristika: surandame nuo galo ilgesnį segmentą su bib-item eilučių dauguma
    min_tail = min(80, len(lines))
    tail_start = len(lines) - min_tail
    tail = lines[tail_start:]

    # skaičiuojame „bib-like“ tankį slankiu langu
    best = None  # (score, start_idx_in_doc)
    for start in range(tail_start, len(lines)):
        seg = lines[start:]
        non_empty = [ln for ln in seg if norm_ws(ln)]
        if len(non_empty) < 5:
            continue
        bib_like = sum(1 for ln in non_empty if _is_bib_item_like(ln))
        score = bib_like / max(1, len(non_empty))
        if score >= 0.55:  # pakankamai „bibliografiška“
            # preferuojame anksčiau prasidedantį (didesnį) segmentą su geru score
            cand = (score, start)
            if best is None or cand[1] < best[1] or (cand[1] == best[1] and cand[0] > best[0]):
                best = cand

    if best is None:
        return BibliographySplit(body_text=text.rstrip(), bibliography_text="", bibliography_start_line=None)

    _, start = best
    body = join_lines(lines[:start]).rstrip()
    bib = join_lines(lines[start:]).strip()
    return BibliographySplit(body_text=body, bibliography_text=bib, bibliography_start_line=start)


def bibliography_to_entries(bibliography_text: str) -> list[str]:
    """
    Suskaldo bibliografijos tekstą į atskirus įrašus.
    Veikia „gerai enough“: grupuoja pagal tuščias eilutes arba numeraciją/bullet.
    """
    lines = split_lines(bibliography_text)
    entries: list[str] = []
    buf: list[str] = []

    def flush():
        nonlocal buf
        e = " ".join(norm_ws(x) for x in buf if norm_ws(x)).strip()
        if e:
            entries.append(e)
        buf = []

    for ln in lines:
        if not norm_ws(ln):
            flush()
            continue
        if buf and _BIB_ITEM_BULLET_RE.match(ln):
            flush()
        buf.append(ln)

    flush()
    # išmetam per trumpus
    return [e for e in entries if len(e) >= 10]

