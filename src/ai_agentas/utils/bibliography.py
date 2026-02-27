from __future__ import annotations

import re

from .text_norm import (
    BibliographySplit,
    looks_like_heading,
    looks_like_stop_heading,
    norm_ws,
    split_lines,
    join_lines,
)


_BIB_ITEM_BULLET_RE = re.compile(r"^\s*(?:\[\d{1,4}\]|\d{1,4}[\.\)]|[-\u2022])\s*")
_NUMBERED_ITEM_RE = re.compile(r"^\s*(?:\[\d{1,4}\]|\d{1,4}[\.\)])\s*")
_LEADING_INDEX_RE = re.compile(r"^\s*(?:\[?\s*([0-9Il|OoS]{1,4})\s*\]?[\.\)]?)\s+")
_PDF_MARGIN_NOISE_RE = re.compile(
    r"^\s*\d{1,3}\s*[a-z0-9.-]+\.[a-z]{2,}(?:/[^\s]+)?\s+"
    r"(?:r\.\s*soc\.\s*open\s*sci\.?|journal|vol\.?\s*\d+|\d+:\s*\d+)",
    re.IGNORECASE,
)
_PAGE_NO_RE = re.compile(r"^\s*\d{1,4}\s*$")
_NOISE_KEYWORDS_RE = re.compile(
    r"(?:copyright|all rights reserved|www\.[a-z0-9.-]+\.[a-z]{2,}|doi:\s*10\.|issn\b|ijarsct|journal)",
    re.IGNORECASE,
)


def _leading_index(line: str) -> int | None:
    m = _LEADING_INDEX_RE.match(line or "")
    if not m:
        return None
    g = m.group(1)
    if not g:
        return None
    # OCR / zmogiskos klaidos: I,l,| -> 1 ; O,o -> 0 ; S -> 5
    tr = str.maketrans({"I": "1", "l": "1", "|": "1", "O": "0", "o": "0", "S": "5"})
    g = g.translate(tr)
    if not re.fullmatch(r"\d{1,4}", g):
        return None
    try:
        return int(g)
    except ValueError:
        return None


def _is_probable_noise_line(line: str) -> bool:
    l = norm_ws(line)
    if not l:
        return True
    if _PAGE_NO_RE.match(l):
        return True
    if _PDF_MARGIN_NOISE_RE.match(l.lower()):
        return True
    return False


def _drop_repeated_page_noise(lines: list[str]) -> list[str]:
    """
    Pasalina pasikartojancias PDF antrastes/poraštes ir izoliuotus puslapiu numerius.
    """
    if not lines:
        return lines

    freq: dict[str, int] = {}
    for ln in lines:
        n = norm_ws(ln).lower()
        if not n:
            continue
        freq[n] = freq.get(n, 0) + 1

    out: list[str] = []
    for ln in lines:
        n = norm_ws(ln).lower()
        if not n:
            out.append(ln)
            continue
        if _PAGE_NO_RE.match(n):
            continue
        # Kartojasi >1 karto ir atrodo kaip techninis triuksmas
        if freq.get(n, 0) >= 2 and _NOISE_KEYWORDS_RE.search(n):
            continue
        out.append(ln)
    return out


def _find_numbered_sequence_start(lines: list[str], start_idx: int = 0) -> int | None:
    """
    Randa stabilios numeruotos sekos pradzia (pvz. [1], [2], [3], ...).
    Naudinga PDF atvejams, kai tankio heuristika paslenka bibliografijos starta per velai.
    """
    best_start = None
    best_hits = 0
    best_score = -10_000.0

    for i in range(max(0, start_idx), len(lines)):
        first = _leading_index(lines[i])
        if first is None:
            continue
        expected = first
        seq_hits = 0
        seq_gaps = 0
        noise_steps = 0
        j = i
        while j < len(lines):
            idx = _leading_index(lines[j])
            if idx is None:
                if _is_probable_noise_line(lines[j]):
                    noise_steps += 1
                j += 1
                continue
            if idx == expected or idx == expected + 1 or idx == expected + 2:
                seq_hits += 1
                if idx > expected:
                    seq_gaps += idx - expected
                expected = idx + 1
            elif idx > expected:
                break
            j += 1

        score = seq_hits * 1.0 - seq_gaps * 0.7 - noise_steps * 0.1
        if seq_hits > best_hits or (seq_hits == best_hits and score > best_score):
            best_hits = seq_hits
            best_score = score
            best_start = i

    # Praktiskai laikome patikima, jei turime bent 3 numeruotus irasus.
    if best_hits >= 3:
        return best_start
    return None


def _is_bib_item_like(line: str) -> bool:
    """Heuristika: ar eilute panasi i bibliografijos irasa."""
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


def _is_clearly_not_reference(entry: str) -> bool:
    """Atfiltruoja irasus, kurie tikrai nera bibliografijos saltiniai."""
    l = norm_ws(entry).lower()
    if not l:
        return True
    # PDF paraščių/headerių triukšmas (pvz. "20royalsocietypublishing.org/... R. Soc. Open Sci. ...")
    if _PDF_MARGIN_NOISE_RE.match(l):
        return True
    # Per trumpas
    if len(l) < 15:
        return True
    # Atrodo kaip antraste / priedas / klausimas
    if looks_like_stop_heading(entry):
        return True
    # Interviu / klausimyno turinys
    if l.startswith("sveiki") or l.startswith("ar galite") or l.startswith("ar j"):
        return True
    # DIDELES RAIDES be metu = greiciausiai antraste, ne saltinis
    upper_ratio = sum(1 for c in entry if c.isupper()) / max(1, sum(1 for c in entry if c.isalpha()))
    has_year = bool(re.search(r"\b(19|20)\d{2}\b", l))
    if upper_ratio > 0.6 and not has_year and len(l) < 100:
        return True
    # Nera nei metu, nei bent bazines skyrybos, nei DOI/URL
    has_punct = "." in l or "," in l or ":" in l
    has_doi_url = "doi" in l or "http" in l
    if not has_year and not has_punct and not has_doi_url and len(l) < 200:
        return True
    return False


def split_bibliography(text: str) -> BibliographySplit:
    """
    Atskiria dokumento pagrindini teksta nuo literaturos saraso.

    Strategija:
    1. Ieskome antrascuu (References/Literatura/...) nuo galo
    2. Po rastos antrastes imame eilutes IKI kitos stop-antrastes (Priedai, Santrauka...)
    3. Jei antrastes nera — heuristinis "bib-like" tankio paieska
    """
    lines = _drop_repeated_page_noise(split_lines(text))
    if not lines:
        return BibliographySplit(body_text="", bibliography_text="", bibliography_start_line=None)

    # 0) Jei matome stabilia [1],[2],[3]... seka — tai stiprus signalas.
    # Pirmiausia ieskome dokumento gale, jei neradome - per visa dokumenta.
    seq_start = _find_numbered_sequence_start(lines, max(0, len(lines) - min(160, len(lines))))
    if seq_start is None:
        seq_start = _find_numbered_sequence_start(lines, 0)

    # 1) Ieskome visu bibliografijos antrasciu ir renkam geriausia kandidata
    heading_candidates = [i for i, ln in enumerate(lines) if looks_like_heading(ln)]
    best_heading = None  # (score, heading_idx, bib_start, bib_end)
    for h_idx in heading_candidates:
        bib_start = h_idx + 1
        bib_end = len(lines)
        for j in range(bib_start, len(lines)):
            if looks_like_stop_heading(lines[j]):
                bib_end = j
                break

        seg = lines[bib_start:bib_end]
        non_empty = [ln for ln in seg if norm_ws(ln)]
        if len(non_empty) < 3:
            continue
        bib_like = sum(1 for ln in non_empty if _is_bib_item_like(ln))
        year_like = sum(1 for ln in non_empty if re.search(r"\b(19|20)\d{2}\b", ln))
        density = bib_like / max(1, len(non_empty))
        year_density = year_like / max(1, len(non_empty))
        score = density * 0.75 + year_density * 0.25
        if score < 0.35:
            continue
        cand = (score, h_idx, bib_start, bib_end)
        if best_heading is None:
            best_heading = cand
        else:
            # prioritetas: didesnis score; jei panasus - imame velesne (arciau dokumento galo)
            if cand[0] > best_heading[0] + 0.02:
                best_heading = cand
            elif abs(cand[0] - best_heading[0]) <= 0.02 and cand[1] > best_heading[1]:
                best_heading = cand

    if best_heading is not None:
        _, h_idx, bib_start, bib_end = best_heading
        if seq_start is not None and bib_start <= seq_start < bib_end:
            # Jei heading aptiktas, bet numeruota seka prasideda veliau, imam sekos pradzia.
            bib_start = seq_start
        bib = join_lines(lines[bib_start:bib_end]).strip()
        body = join_lines(lines[:h_idx]).rstrip()
        return BibliographySplit(body_text=body, bibliography_text=bib, bibliography_start_line=bib_start)

    # 2) Heuristika: surandame nuo galo ilgesni segmenta su bib-item eiluciu dauguma
    min_tail = min(80, len(lines))
    tail_start = len(lines) - min_tail

    best = None  # (score, start_idx_in_doc)
    for start in range(tail_start, len(lines)):
        seg = lines[start:]
        non_empty = [ln for ln in seg if norm_ws(ln)]
        if len(non_empty) < 5:
            continue
        bib_like = sum(1 for ln in non_empty if _is_bib_item_like(ln))
        score = bib_like / max(1, len(non_empty))
        if score >= 0.55:
            cand = (score, start)
            if best is None or cand[1] < best[1] or (cand[1] == best[1] and cand[0] > best[0]):
                best = cand

    if best is None:
        if seq_start is not None:
            body = join_lines(lines[:seq_start]).rstrip()
            bib = join_lines(lines[seq_start:]).strip()
            return BibliographySplit(body_text=body, bibliography_text=bib, bibliography_start_line=seq_start)
        return BibliographySplit(body_text=text.rstrip(), bibliography_text="", bibliography_start_line=None)

    _, start = best
    body = join_lines(lines[:start]).rstrip()
    bib = join_lines(lines[start:]).strip()
    return BibliographySplit(body_text=body, bibliography_text=bib, bibliography_start_line=start)


def bibliography_to_entries(bibliography_text: str) -> list[str]:
    """
    Suskaldo bibliografijos teksta i atskirus irasus.
    Grupuoja pagal tuscias eilutes arba numeracija/bullet.
    Isfiltruoja aiksiai ne-saltininius irasus.
    """
    lines = _drop_repeated_page_noise(split_lines(bibliography_text))
    entries: list[str] = []
    buf: list[str] = []

    # PDF numeruotu sarasu rezimas: jei bent kelios eilutes prasideda "1." / "2)" / "[3]"
    numbered_lines = sum(1 for ln in lines if _NUMBERED_ITEM_RE.match(ln))
    numbered_mode = numbered_lines >= 2

    def flush():
        nonlocal buf
        e = " ".join(norm_ws(x) for x in buf if norm_ws(x)).strip()
        if e:
            entries.append(e)
        buf = []

    def split_numbered_entries(processed: list[str]) -> list[str]:
        """
        Skaido numeruotus irasus pagal markerio perejima.
        Islaiko vientisuma net jei tarp eiluciu yra tarpai ar OCR triuksmas.
        """
        out: list[str] = []
        local_buf: list[str] = []
        current_idx: int | None = None

        def flush_local():
            nonlocal local_buf
            e = " ".join(norm_ws(x) for x in local_buf if norm_ws(x)).strip()
            if e:
                out.append(e)
            local_buf = []

        for ln in processed:
            idx = _leading_index(ln)
            if idx is not None and (current_idx is None or idx != current_idx):
                flush_local()
                current_idx = idx
                local_buf = [ln]
                continue
            local_buf.append(ln)

        flush_local()
        return out

    processed_lines: list[str] = []
    for ln in lines:
        stripped = norm_ws(ln)
        if not stripped:
            # Numeruotuose sarasuose tuscios eilutes daznai yra PDF lauzymo artefaktas.
            # Neflushinam, nes reali iraso riba vis tiek ateina su sekanciu [n]/n. markeriu.
            if not numbered_mode:
                flush()
            continue
        # Jei sutinkame stop-antraste — stabdom viska
        if looks_like_stop_heading(ln):
            flush()
            break
        processed_lines.append(ln)
        if numbered_mode:
            continue
        if buf and _BIB_ITEM_BULLET_RE.match(ln):
            flush()
        buf.append(ln)

    flush()

    # Jei numeruotu eiluciu buvo pakankamai, bet del PDF lauzymo dalis irasu susiliejo,
    # atliekame papildoma skaidyma pagal numerinius markerius.
    if numbered_mode:
        forced_entries = [norm_ws(p) for p in split_numbered_entries(processed_lines) if norm_ws(p)]
        # Numeruotuose sarasuose filtruojame svelniau, kad neprarastume validziu irasu.
        forced_entries = [
            e
            for e in forced_entries
            if len(e) >= 10 and (_leading_index(e) is not None or not _is_clearly_not_reference(e))
        ]
        if len(forced_entries) > len(entries):
            entries = forced_entries

    # Filtruojame: ismetame per trumpus ir aiskiai ne-saltininius.
    # Numeruotuose sarasuose taikome svelnesne logika, kad neprarastume [n] irasu.
    if numbered_mode:
        return [
            e
            for e in entries
            if len(e) >= 10 and (_leading_index(e) is not None or not _is_clearly_not_reference(e))
        ]

    return [e for e in entries if len(e) >= 15 and not _is_clearly_not_reference(e)]
