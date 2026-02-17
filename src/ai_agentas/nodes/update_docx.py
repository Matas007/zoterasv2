from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from docx import Document

from ai_agentas.utils.text_norm import norm_ws


@dataclass(frozen=True)
class UpdateResult:
    output_path: str
    replacements: int


_AUTHOR_YEAR_PAREN_RE = re.compile(
    r"\(([^()]{1,80}?),\s*((?:19|20)\d{2}|n\.d\.)\)"  # (Petrauskas, 2020)
)
_NUMERIC_BRACKET_RE = re.compile(r"\[(\d{1,3}(?:\s*[-–]\s*\d{1,3})?(?:\s*,\s*\d{1,3})*)\]")


def _replace_in_text(text: str, citekey: str) -> tuple[str, int]:
    """
    Minimalus placeholder formatas: [@citekey]
    (Pandoc/Quarto stiliaus; patogu vėliau konvertuoti)
    """
    if not text:
        return text, 0

    cnt = 0

    def repl_author_year(m: re.Match) -> str:
        nonlocal cnt
        cnt += 1
        return f"[@{citekey}]"

    # Pakeičiam tik pirmą match'ą vienam citekey kvietimui
    new, n = _AUTHOR_YEAR_PAREN_RE.subn(repl_author_year, text, count=1)
    if n:
        return new, cnt

    # Jei numerinis – irgi pakeičiam pirmą
    def repl_num(m: re.Match) -> str:
        nonlocal cnt
        cnt += 1
        return f"[@{citekey}]"

    new2, n2 = _NUMERIC_BRACKET_RE.subn(repl_num, text, count=1)
    if n2:
        return new2, cnt
    return text, 0


def update_docx_placeholders(
    input_docx_path: str,
    citekeys_in_order: list[str],
    output_docx_path: str | None = None,
) -> UpdateResult:
    """
    MVP logika:
    - eina per pastraipas iš viršaus į apačią
    - kaskart radus citatos raštą (autorius–metai arba [1]) pakeičia į [@citekey]
      pagal `citekeys_in_order` eilę

    Tai nėra 100% teisingas citatų „matching“, bet praktiškai leidžia susieti
    citatas su bibliografijos įrašais minimaliai be API.
    """
    p = Path(input_docx_path)
    out = Path(output_docx_path) if output_docx_path else p.with_name(p.stem + ".zotero-mvp.docx")

    doc = Document(str(p))
    idx = 0
    total_repl = 0

    def next_ck() -> str | None:
        nonlocal idx
        if idx >= len(citekeys_in_order):
            return None
        ck = citekeys_in_order[idx]
        idx += 1
        return ck

    # Pagrindinės pastraipos
    for para in doc.paragraphs:
        t = para.text or ""
        if not t:
            continue
        # jei pastraipa atrodo kaip bibliografija – neliečiam
        if len(t) > 20 and (t.strip().startswith("[") or re.match(r"^\s*\d+[\.\)]\s+", t)):
            continue

        ck = next_ck()
        if ck is None:
            break
        new, n = _replace_in_text(t, ck)
        if n:
            para.text = new
            total_repl += n
        else:
            # jei nepavyko pakeisti – grąžinam ck atgal, kad nedingtų
            idx -= 1

    doc.save(str(out))
    return UpdateResult(output_path=str(out), replacements=total_repl)

