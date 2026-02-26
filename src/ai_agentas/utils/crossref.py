from __future__ import annotations

import json
import urllib.parse
import urllib.request

from ai_agentas.nodes.parse_bibliography import ParsedReference
from ai_agentas.utils.text_norm import norm_ws


def _ua(mailto: str | None) -> str:
    base = "ai-agentas/0.0.1"
    m = norm_ws(mailto or "")
    return f"{base} (mailto:{m})" if m else base


def _get_json(url: str, *, mailto: str | None, timeout_seconds: float) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": _ua(mailto),
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    return json.loads(body)


def _first_str(v: object) -> str | None:
    if isinstance(v, str):
        s = norm_ws(v)
        return s or None
    if isinstance(v, list) and v:
        if isinstance(v[0], str):
            s = norm_ws(v[0])
            return s or None
    return None


def _year_from_issued(msg: dict) -> str | None:
    issued = msg.get("issued")
    if isinstance(issued, dict):
        dp = issued.get("date-parts")
        if isinstance(dp, list) and dp and isinstance(dp[0], list) and dp[0]:
            y = dp[0][0]
            if isinstance(y, int):
                return str(y)
            if isinstance(y, str) and y.isdigit():
                return y
    return None


def _authors(msg: dict) -> tuple[str | None, list[str]]:
    a = msg.get("author")
    if not isinstance(a, list) or not a:
        return None, []
    names: list[str] = []
    for item in a[:30]:
        if not isinstance(item, dict):
            continue
        family = norm_ws(item.get("family") or "")
        given = norm_ws(item.get("given") or "")
        if family and given:
            names.append(f"{family}, {given}")
        elif family:
            names.append(family)
        elif given:
            names.append(given)
    names = [n for n in (norm_ws(x) for x in names) if n]
    return ("; ".join(names) if names else None), names


def _merge(ref: ParsedReference, msg: dict, *, source: str) -> ParsedReference:
    title = _first_str(msg.get("title")) or ref.title
    year = _year_from_issued(msg) or ref.year
    journal = _first_str(msg.get("container-title")) or ref.journal
    doi = norm_ws(msg.get("DOI") or "") or ref.doi
    url = _first_str(msg.get("URL")) or ref.url
    volume = norm_ws(msg.get("volume") or "") or ref.volume
    issue = norm_ws(msg.get("issue") or "") or ref.issue
    pages = norm_ws(msg.get("page") or "") or ref.pages
    publisher = _first_str(msg.get("publisher")) or ref.publisher

    author_str, authors = _authors(msg)
    if not authors:
        author_str, authors = ref.author, ref.authors

    # Jei Crossref pridėjo DOI ar title/year – keliam pasitikėjimą
    conf = ref.confidence
    if doi and not ref.doi:
        conf = max(conf, 0.80)
    if title and not ref.title:
        conf = max(conf, 0.75)
    if year and not ref.year:
        conf = max(conf, 0.70)
    conf = min(1.0, conf + 0.05)

    return ParsedReference(
        raw=ref.raw,
        title=title,
        year=year,
        author=author_str,
        authors=authors,
        journal=journal,
        volume=volume or None,
        issue=issue or None,
        pages=pages or None,
        publisher=publisher,
        doi=doi.lower() if isinstance(doi, str) and doi else None,
        url=url,
        confidence=conf,
        parser=f"{ref.parser}+{source}",
    )


def enrich_reference_with_crossref(
    ref: ParsedReference,
    *,
    mailto: str | None = None,
    timeout_seconds: float = 20.0,
    rows: int = 5,
) -> ParsedReference:
    """
    Bando patikslinti metaduomenis per Crossref.
    - Jei turime DOI -> /works/{doi}
    - Kitu atveju -> /works?query.bibliographic=...
    """
    doi = norm_ws(ref.doi or "")
    try:
        if doi:
            url = f"https://api.crossref.org/works/{urllib.parse.quote(doi)}"
            data = _get_json(url, mailto=mailto, timeout_seconds=timeout_seconds)
            msg = data.get("message") if isinstance(data, dict) else None
            if isinstance(msg, dict):
                return _merge(ref, msg, source="crossref")

        q = norm_ws(ref.raw)
        if not q or len(q) < 10:
            return ref
        params = {
            "query.bibliographic": q,
            "rows": str(max(1, min(int(rows), 20))),
        }
        url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
        data = _get_json(url, mailto=mailto, timeout_seconds=timeout_seconds)
        msg = data.get("message") if isinstance(data, dict) else None
        items = msg.get("items") if isinstance(msg, dict) else None
        if isinstance(items, list) and items:
            top = items[0]
            if isinstance(top, dict):
                return _merge(ref, top, source="crossref")
    except Exception:
        return ref
    return ref


def enrich_refs_with_crossref(
    refs: list[ParsedReference],
    *,
    mailto: str | None = None,
    timeout_seconds: float = 20.0,
    rows: int = 5,
) -> list[ParsedReference]:
    return [
        enrich_reference_with_crossref(r, mailto=mailto, timeout_seconds=timeout_seconds, rows=rows)
        for r in refs
    ]

