"""LLM (Gemini) fallback for low-confidence bibliography parsing."""
from __future__ import annotations

import json
import re

from ai_agentas.nodes.parse_bibliography import ParsedReference


_PROMPT = """Extract bibliographic fields from this reference string. Return ONLY a JSON object with these keys (use null for missing): author, title, year, journal, volume, issue, pages, publisher, doi, url.
Authors: separate multiple with "; ". Use "Family, Given" or "Family, G." format.
Year: 4-digit string.
Do not add explanation, only the JSON object.

Reference:
"""
_JSON_BLOCK_RE = re.compile(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", re.DOTALL)


def _parse_llm_json(text: str) -> dict | None:
    """Ištraukia JSON objektą iš LLM atsakymo."""
    if not text or not text.strip():
        return None
    s = text.strip()
    m = _JSON_BLOCK_RE.search(s)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


def _norm(s: str | None) -> str | None:
    if s is None:
        return None
    t = (s or "").strip()
    return t if t else None


def _authors_list(author_str: str | None) -> list[str]:
    if not author_str:
        return []
    parts = [p.strip() for p in re.split(r";\s*|\s+and\s+|\s*&\s*", author_str) if p.strip()]
    return parts[:50]


def refine_reference_with_llm(
    ref: ParsedReference,
    *,
    api_key: str,
    model: str = "gemini-1.5-flash",
    max_output_tokens: int = 1024,
) -> ParsedReference | None:
    """
    Siunčia ref.raw į Gemini ir grąžina ParsedReference iš LLM JSON.
    Grąžina None jei API klaida ar nepavyksta parse'inti.
    """
    if not api_key or not ref.raw or len(ref.raw) < 10:
        return None
    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        gemini = genai.GenerativeModel(model)
        response = gemini.generate_content(
            _PROMPT + ref.raw[:4000],
            generation_config={"max_output_tokens": max_output_tokens, "temperature": 0.1},
        )
        text = (response.text or "").strip()
    except Exception:
        return None

    data = _parse_llm_json(text)
    if not isinstance(data, dict):
        return None

    author_str = _norm(data.get("author"))
    authors = _authors_list(author_str) if author_str else ref.authors
    if not author_str and ref.author:
        author_str = ref.author

    title = _norm(data.get("title")) or ref.title
    year = _norm(data.get("year")) or ref.year
    journal = _norm(data.get("journal")) or ref.journal
    volume = _norm(data.get("volume")) or ref.volume
    issue = _norm(data.get("issue")) or ref.issue
    pages = _norm(data.get("pages")) or ref.pages
    publisher = _norm(data.get("publisher")) or ref.publisher
    doi = _norm(data.get("doi")) or ref.doi
    url = _norm(data.get("url")) or ref.url
    if doi:
        doi = doi.lower().replace("https://doi.org/", "").strip()

    return ParsedReference(
        raw=ref.raw,
        title=title,
        year=year,
        author=author_str,
        authors=authors,
        journal=journal,
        volume=volume,
        issue=issue,
        pages=pages,
        publisher=publisher,
        doi=doi,
        url=url,
        confidence=0.85,
        parser=f"{ref.parser}+llm",
    )


def refine_refs_with_llm(
    refs: list[ParsedReference],
    *,
    api_key: str | None,
    model: str = "gemini-1.5-flash",
    confidence_threshold: float = 0.70,
    max_output_tokens: int = 1024,
) -> list[ParsedReference]:
    """
    Tiems refs, kurių confidence < threshold arba trūksta title/author,
    bando patikslinti per Gemini. Jei LLM nepavyksta — palieka originalą.
    """
    if not api_key or not refs:
        return refs

    out: list[ParsedReference] = []
    for r in refs:
        need_llm = (
            r.confidence < confidence_threshold
            or not r.title
            or not (r.author or r.authors)
        )
        if not need_llm:
            out.append(r)
            continue
        refined = refine_reference_with_llm(
            r,
            api_key=api_key,
            model=model,
            max_output_tokens=max_output_tokens,
        )
        out.append(refined if refined is not None else r)
    return out
