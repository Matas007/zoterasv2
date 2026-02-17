from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ai_agentas.utils.bibliography import bibliography_to_entries
from ai_agentas.utils.text_norm import norm_ws


@dataclass(frozen=True)
class ParsedReference:
    raw: str
    title: str | None = None
    year: str | None = None
    author: str | None = None
    journal: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    publisher: str | None = None
    doi: str | None = None
    url: str | None = None


# ---------------------------------------------------------------------------
# Regex rinkiniai dažniausiems citavimo stiliams
# ---------------------------------------------------------------------------

# Metai (1900–2099)
_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")

# DOI
_DOI_RE = re.compile(r"(?:doi\s*:\s*|https?://doi\.org/)(10\.\d{4,9}/[^\s,;]+)", re.IGNORECASE)

# URL
_URL_RE = re.compile(r"(https?://[^\s,;]+)")

# Puslapiai: pp. 12-34, p. 5, 123–145
_PAGES_RE = re.compile(r"(?:pp?\.\s*)?(\d{1,5}\s*[-–]\s*\d{1,5})")

# Tomas/numeris: Vol. 12, No. 3  arba  12(3)
_VOL_ISSUE_RE = re.compile(r"(?:Vol\.?\s*)?(\d{1,4})\s*\((\d{1,4})\)")
_VOL_ONLY_RE = re.compile(r"(?:Vol\.?\s*)(\d{1,4})")

# Numerinis prefiksas: [1], 1., 1)
_NUM_PREFIX_RE = re.compile(r"^\s*(?:\[?\d{1,4}\]?[\.\)]\s*)")


def _extract_doi(text: str) -> str | None:
    m = _DOI_RE.search(text)
    return m.group(1).rstrip(".") if m else None


def _extract_url(text: str) -> str | None:
    m = _URL_RE.search(text)
    return m.group(1).rstrip(".,;)") if m else None


def _extract_year(text: str) -> str | None:
    m = _YEAR_RE.search(text)
    return m.group(1) if m else None


def _extract_pages(text: str) -> str | None:
    m = _PAGES_RE.search(text)
    return m.group(1) if m else None


def _extract_vol_issue(text: str) -> tuple[str | None, str | None]:
    m = _VOL_ISSUE_RE.search(text)
    if m:
        return m.group(1), m.group(2)
    m2 = _VOL_ONLY_RE.search(text)
    if m2:
        return m2.group(1), None
    return None, None


def _strip_num_prefix(text: str) -> str:
    """Pašalina numerinį prefiksą ([1], 1., 1) ir pan.)"""
    return _NUM_PREFIX_RE.sub("", text)


def _split_author_rest(text: str) -> tuple[str, str]:
    """
    Bando atskirti autorių dalį nuo likusio teksto.

    Strategija:
    - APA: „Petrauskas, J. (2020). Pavadinimas..."
    - Bendras: „Petrauskas J., Jonaitis A. Pavadinimas..."
    - Ieškome pirmo taško po kurio eina didžioji raidė arba metų skliaustas
    """
    # APA: autorius (-iai), metai skliaustuose
    apa_m = re.match(
        r"^(.+?)\s*\(\s*((?:19|20)\d{2}[a-z]?)\s*\)\s*\.?\s*(.*)$",
        text,
        re.DOTALL,
    )
    if apa_m:
        return norm_ws(apa_m.group(1)), norm_ws(apa_m.group(3))

    # Bandome: autorius iki pirmo taško, po kurio eina didžioji raidė
    dot_positions = [i for i, ch in enumerate(text) if ch == "."]
    for pos in dot_positions:
        rest = text[pos + 1 :].lstrip()
        if rest and rest[0].isupper():
            # patikrinkime, ar prieš tašką nėra inicialų (pvz., „J.")
            before = text[:pos + 1].rstrip()
            # jei paskutinis žodis prieš tašką yra 1-2 simboliai — greičiausiai inicialas
            last_word = before.split()[-1] if before.split() else ""
            if len(last_word) <= 3:
                continue
            return norm_ws(text[: pos]), norm_ws(rest)

    # Fallback: paimam iki pirmos kableliu atskirtos dalies su metais
    year_m = _YEAR_RE.search(text)
    if year_m:
        idx = year_m.start()
        candidate_author = text[:idx].rstrip(" ,.(")
        if candidate_author and len(candidate_author) > 2:
            return norm_ws(candidate_author), norm_ws(text[idx:])

    return "", text


def _extract_title(rest: str) -> str | None:
    """
    Iš likusio teksto (po autoriaus) bando ištraukti pavadinimą.
    Paprastai tai pirmas sakinys (iki taško) arba tekstas tarp kabučių / kursyvu.
    """
    if not rest:
        return None

    # Jei yra kabutės / guillemets
    q_m = re.search(r'[""«„](.+?)[""»"]', rest)
    if q_m:
        return norm_ws(q_m.group(1))

    # Pirmas sakinys (iki taško, bet ne inicialų „A." tipo)
    parts = re.split(r"(?<=[^A-Z])\.\s+", rest, maxsplit=1)
    if parts:
        candidate = norm_ws(parts[0])
        if len(candidate) >= 5:
            return candidate

    # Fallback: paimam pirmus ~150 simbolių
    return norm_ws(rest[:150]) if len(rest) > 5 else None


def _extract_journal(rest: str) -> str | None:
    """
    Bando rasti žurnalo / šaltinio pavadinimą.
    Dažnai eina po pavadinimo, prieš tomo/puslapių numerius, kursyvu (bet tekste to nematom).
    Heuristika: tekstas tarp pavadinimo taško ir tomo/metų.
    """
    # Jei yra „In:" arba „In " — tai knygos/konferencijos pavadinimas
    in_m = re.search(r"\bIn[:\s]+(.+?)(?:\.|,\s*(?:Vol|pp|\d))", rest, re.IGNORECASE)
    if in_m:
        return norm_ws(in_m.group(1))

    # Bandome: po pirmo sakinio taško, prieš „, Vol" arba „, \d+("
    parts = re.split(r"(?<=[^A-Z])\.\s+", rest)
    if len(parts) >= 2:
        candidate = norm_ws(parts[1].split(",")[0])
        if 3 < len(candidate) < 120:
            return candidate

    return None


def parse_reference(raw_entry: str) -> ParsedReference:
    """Bando regex'ais išparsuoti vieną bibliografijos įrašą."""
    clean = _strip_num_prefix(raw_entry)

    doi = _extract_doi(clean)
    url = _extract_url(clean)
    year = _extract_year(clean)
    pages = _extract_pages(clean)
    vol, issue = _extract_vol_issue(clean)

    author_str, rest = _split_author_rest(clean)
    title = _extract_title(rest)
    journal = _extract_journal(rest)

    return ParsedReference(
        raw=raw_entry,
        title=title,
        year=year,
        author=norm_ws(author_str) if author_str else None,
        journal=journal,
        volume=vol,
        issue=issue,
        pages=pages,
        publisher=None,
        doi=doi,
        url=url,
    )


def parse_bibliography_text(bibliography_text: str) -> list[ParsedReference]:
    """
    Pagrindinis entry-point: suskaldo bibliografiją į įrašus ir kiekvieną
    išparsuoja Python regex parseriais (be jokių išorinių API/CLI).
    """
    entries = bibliography_to_entries(bibliography_text)
    if not entries:
        return []
    return [parse_reference(e) for e in entries]
