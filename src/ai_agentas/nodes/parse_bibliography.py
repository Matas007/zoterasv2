from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from ai_agentas.utils.bibliography import bibliography_to_entries
from ai_agentas.utils.text_norm import norm_ws


@dataclass(frozen=True)
class ParsedReference:
    raw: str
    title: str | None = None
    year: str | None = None
    author: str | None = None
    authors: list[str] = field(default_factory=list)
    journal: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    publisher: str | None = None
    doi: str | None = None
    url: str | None = None
    confidence: float = 0.0
    parser: str = "regex-ensemble"


_YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
_DOI_RE = re.compile(r"(?:doi\s*:\s*|https?://doi\.org/)(10\.\d{4,9}/[^\s,;]+)", re.IGNORECASE)
_URL_RE = re.compile(r"(https?://[^\s,;]+)")
_PAGES_RE = re.compile(r"(?:pp?\.\s*)?(\d{1,5}\s*[-–]\s*\d{1,5})")
_VOL_ISSUE_RE = re.compile(r"(?:Vol\.?\s*)?(\d{1,4})\s*\((\d{1,4})\)")
_VOL_ONLY_RE = re.compile(r"(?:Vol\.?\s*)(\d{1,4})")
_NUM_PREFIX_RE = re.compile(r"^\s*(?:\[?\d{1,4}\]?[\.\)]\s*)")
_QUOTED_TITLE_RE = re.compile(r"[\"'«„](.+?)[\"'»“]")
_DOI_CLEAN_RE = re.compile(r"^https?://doi\.org/", re.IGNORECASE)

_IEEE_RE = re.compile(
    r"^\s*(?:\[\d+\]\s*)?"
    r"(?P<author>[^\"“”]+?)\s*,\s*"
    r"[\"“”](?P<title>.+?)[\"“”]\s*,\s*"
    r"(?P<rest>.+)$"
)
_INPROC_RE = re.compile(
    r"^\s*(?P<author>.+?)\.\s*(?P<year>(?:19|20)\d{2})\s+"
    r"(?P<title>.+?)\.\s+In\s+(?P<rest>.+)$",
    re.DOTALL,
)
_APA_RE = re.compile(
    r"^\s*(?P<author>.+?)\s*\(\s*(?P<year>(?:19|20)\d{2}[a-z]?)\s*\)\s*\.?\s*(?P<rest>.+)$",
    re.DOTALL,
)


def _extract_doi(text: str) -> str | None:
    m = _DOI_RE.search(text)
    if not m:
        return None
    doi = m.group(1).rstrip(".,;)")
    doi = _DOI_CLEAN_RE.sub("", doi)
    return doi.lower()


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
    return _NUM_PREFIX_RE.sub("", text)


def _split_authors(author_str: str | None) -> list[str]:
    if not author_str:
        return []
    s = norm_ws(author_str)
    if not s:
        return []

    for sep in ("; ", " and ", " & ", " ir "):
        if sep in s.lower():
            parts = re.split(re.escape(sep), s, flags=re.IGNORECASE)
            out = [norm_ws(p) for p in parts if norm_ws(p)]
            return out if out else [s]

    chunks = re.split(r",\s*(?=[A-Z][a-zA-Z\-']+\s*,\s*[A-Z]\.)", s)
    if len(chunks) > 1:
        return [norm_ws(c) for c in chunks if norm_ws(c)]

    return [s]


_STRIP_DOI_URL_RE = re.compile(
    r"\s*[\(\[]?\s*(?:doi\s*:\s*|https?://doi\.org/|https?://)\S+[\)\]]?$",
    re.IGNORECASE,
)


def _strip_doi_url_suffix(text: str) -> str:
    """Pasalina pasibaigiancio DOI/URL fragmenta is lauko pabaigos."""
    return _STRIP_DOI_URL_RE.sub("", text).rstrip(" .,;(")


def _extract_title(rest: str) -> str | None:
    if not rest:
        return None
    q_m = _QUOTED_TITLE_RE.search(rest)
    if q_m:
        return norm_ws(_strip_doi_url_suffix(q_m.group(1)))
    parts = re.split(r"(?<=[^A-Z])\.\s+", rest, maxsplit=1)
    if parts:
        candidate = norm_ws(_strip_doi_url_suffix(parts[0]))
        if len(candidate) >= 5:
            return candidate
    return norm_ws(_strip_doi_url_suffix(rest[:200])) if len(rest) > 5 else None


def _extract_journal(rest: str) -> str | None:
    in_m = re.search(r"\bIn[:\s]+(.+?)(?:\.|,\s*(?:Vol|pp|\d))", rest, re.IGNORECASE)
    if in_m:
        return norm_ws(_strip_doi_url_suffix(in_m.group(1)))

    parts = re.split(r"(?<=[^A-Z])\.\s+", rest)
    if len(parts) >= 2:
        candidate = norm_ws(_strip_doi_url_suffix(parts[1].split(",")[0]))
        if 3 < len(candidate) < 120:
            return candidate

    comma_parts = [norm_ws(x) for x in rest.split(",") if norm_ws(x)]
    if len(comma_parts) >= 2 and len(comma_parts[0]) > 3:
        if not re.search(r"\b(vol|no|pp)\b", comma_parts[0], re.IGNORECASE):
            return norm_ws(_strip_doi_url_suffix(comma_parts[0]))
    return None


def _normalize_ocr_noise(text: str) -> str:
    """
    Lengvas, atgal suderinamas OCR/PDF triuksmo tvarkymas.
    Nekeicia strukturos, tik pataiso daznus suklijavimus.
    """
    s = norm_ws(text)
    # Pvz. "Privacy(sp" -> "Privacy (sp"
    s = re.sub(r"([A-Za-z])\(", r"\1 (", s)
    # Metai sulipdyti su raidėmis: "2024Federated" -> "2024 Federated"
    s = re.sub(r"(?<!\d)((?:19|20)\d{2})(?=[A-Za-z])", r"\1 ", s)
    # Raidės sulipdytos su metais: "computing2024" -> "computing 2024"
    s = re.sub(r"([A-Za-z])((?:19|20)\d{2})(?!\d)", r"\1 \2", s)
    # Vienas dazniausiu netycinis suklijavimas tame domene
    s = s.replace("largesparse", "large sparse")
    return s


def _confidence(ref: ParsedReference) -> float:
    score = 0.0
    if ref.title:
        score += 0.30
    if ref.year:
        score += 0.20
    if ref.author:
        score += 0.20
    if ref.journal:
        score += 0.10
    if ref.volume or ref.issue or ref.pages:
        score += 0.10
    if ref.doi or ref.url:
        score += 0.10
    if ref.title and len(ref.title) > 220:
        score -= 0.15
    return max(0.0, min(1.0, score))


def _with_confidence(ref: ParsedReference) -> ParsedReference:
    return ParsedReference(**{**ref.__dict__, "confidence": _confidence(ref)})


def _parse_apa(clean: str) -> ParsedReference | None:
    m = _APA_RE.match(clean)
    if not m:
        return None
    author_str = norm_ws(m.group("author"))
    rest = norm_ws(m.group("rest"))
    title = _extract_title(rest)
    year_raw = m.group("year")
    year = year_raw[:4] if year_raw else None
    journal = _extract_journal(rest)
    pages = _extract_pages(rest)
    vol, issue = _extract_vol_issue(rest)
    return _with_confidence(
        ParsedReference(
            raw=clean,
            title=title,
            year=year,
            author=author_str or None,
            authors=_split_authors(author_str),
            journal=journal,
            volume=vol,
            issue=issue,
            pages=pages,
            doi=_extract_doi(clean),
            url=_extract_url(clean),
            parser="apa-regex",
        )
    )


def _parse_ieee(clean: str) -> ParsedReference | None:
    m = _IEEE_RE.match(clean)
    if not m:
        return None
    author_str = norm_ws(m.group("author").rstrip(","))
    title = norm_ws(m.group("title"))
    rest = norm_ws(m.group("rest"))
    journal = _extract_journal(rest)
    pages = _extract_pages(rest)
    vol, issue = _extract_vol_issue(rest)
    year = _extract_year(rest) or _extract_year(clean)
    return _with_confidence(
        ParsedReference(
            raw=clean,
            title=title,
            year=year,
            author=author_str or None,
            authors=_split_authors(author_str),
            journal=journal,
            volume=vol,
            issue=issue,
            pages=pages,
            doi=_extract_doi(clean),
            url=_extract_url(clean),
            parser="ieee-regex",
        )
    )


def _parse_inproceedings(clean: str) -> ParsedReference | None:
    """
    Konferenciniu irasu forma be kabuciu:
    "Author. 2008 Title. In 2008 IEEE Symp.... pp. 111-125. IEEE. (doi:...)"
    """
    m = _INPROC_RE.match(clean)
    if not m:
        return None
    author_str = norm_ws(m.group("author"))
    year = m.group("year")
    title = norm_ws(m.group("title"))
    rest = norm_ws(m.group("rest"))
    pages = _extract_pages(rest)
    vol, issue = _extract_vol_issue(rest)

    # Konferencijoms journal laukas naudojamas kaip "container/booktitle" pakaitalas
    journal = None
    in_part = re.split(r"(?:,?\s*pp?\.\s*\d|\.\s*(?:doi|https?://|ieee\b))", rest, maxsplit=1, flags=re.IGNORECASE)[0]
    in_part = norm_ws(in_part.rstrip(".,;"))
    if in_part and len(in_part) >= 6:
        journal = in_part
    if not journal:
        journal = _extract_journal(rest)

    return _with_confidence(
        ParsedReference(
            raw=clean,
            title=title or None,
            year=year or None,
            author=author_str or None,
            authors=_split_authors(author_str),
            journal=journal,
            volume=vol,
            issue=issue,
            pages=pages,
            doi=_extract_doi(clean),
            url=_extract_url(clean),
            parser="inproc-regex",
        )
    )


def _parse_generic(clean: str) -> ParsedReference:
    doi = _extract_doi(clean)
    url = _extract_url(clean)
    year = _extract_year(clean)
    pages = _extract_pages(clean)
    vol, issue = _extract_vol_issue(clean)

    author_str = ""
    rest = clean
    year_m = _YEAR_RE.search(clean)
    if year_m:
        cut = clean[: year_m.start()].rstrip(" ,.(")
        if len(cut) > 2:
            author_str = norm_ws(cut)
            rest = norm_ws(clean[year_m.end() :])
    else:
        first_dot = clean.find(".")
        if first_dot > 4:
            author_str = norm_ws(clean[:first_dot])
            rest = norm_ws(clean[first_dot + 1 :])

    title = _extract_title(rest)
    journal = _extract_journal(rest)
    return _with_confidence(
        ParsedReference(
            raw=clean,
            title=title,
            year=year,
            author=author_str or None,
            authors=_split_authors(author_str),
            journal=journal,
            volume=vol,
            issue=issue,
            pages=pages,
            publisher=None,
            doi=doi,
            url=url,
            parser="generic-regex",
        )
    )


def parse_reference(raw_entry: str) -> ParsedReference:
    clean = _normalize_ocr_noise(_strip_num_prefix(raw_entry))
    candidates: list[ParsedReference] = []

    apa = _parse_apa(clean)
    if apa is not None:
        candidates.append(apa)
    ieee = _parse_ieee(clean)
    if ieee is not None:
        candidates.append(ieee)
    inproc = _parse_inproceedings(clean)
    if inproc is not None:
        candidates.append(inproc)
    candidates.append(_parse_generic(clean))

    best = max(candidates, key=lambda r: r.confidence)
    return ParsedReference(**{**best.__dict__, "raw": raw_entry})


def _csl_first_str(v: object) -> str | None:
    if v is None:
        return None
    if isinstance(v, str):
        s = norm_ws(v)
        return s or None
    if isinstance(v, list) and v:
        first = v[0]
        if isinstance(first, str):
            s = norm_ws(first)
            return s or None
    return None


def _csl_year(item: dict[str, object]) -> str | None:
    for key in ("issued", "published-print", "published-online"):
        issued = item.get(key)
        if not isinstance(issued, dict):
            continue
        dp = issued.get("date-parts")
        if isinstance(dp, list) and dp and isinstance(dp[0], list) and dp[0]:
            y = dp[0][0]
            if isinstance(y, int):
                return str(y)
            if isinstance(y, str) and y.isdigit():
                return y
    return None


def _csl_authors(item: dict[str, object]) -> tuple[str | None, list[str]]:
    authors_val = item.get("author")
    if not isinstance(authors_val, list) or not authors_val:
        return None, []

    names: list[str] = []
    for a in authors_val:
        if not isinstance(a, dict):
            continue
        lit = a.get("literal")
        if isinstance(lit, str) and norm_ws(lit):
            names.append(norm_ws(lit))
            continue
        family = a.get("family")
        given = a.get("given")
        fam_s = norm_ws(family) if isinstance(family, str) else ""
        giv_s = norm_ws(given) if isinstance(given, str) else ""
        if fam_s and giv_s:
            names.append(f"{fam_s}, {giv_s}")
        elif fam_s:
            names.append(fam_s)
        elif giv_s:
            names.append(giv_s)

    names = [n for n in (norm_ws(x) for x in names) if n]
    return ("; ".join(names) if names else None), names


def _ref_from_csl_item(raw: str, item: dict[str, object], *, parser_name: str) -> ParsedReference:
    author_str, authors = _csl_authors(item)
    title = _csl_first_str(item.get("title"))
    journal = _csl_first_str(item.get("container-title"))
    year = _csl_year(item)
    doi = _csl_first_str(item.get("DOI")) or _csl_first_str(item.get("doi"))
    url = _csl_first_str(item.get("URL")) or _csl_first_str(item.get("url"))
    volume = _csl_first_str(item.get("volume"))
    issue = _csl_first_str(item.get("issue"))
    pages = _csl_first_str(item.get("page"))
    publisher = _csl_first_str(item.get("publisher"))

    base = ParsedReference(
        raw=raw,
        title=title,
        year=year,
        author=author_str,
        authors=authors,
        journal=journal,
        volume=volume,
        issue=issue,
        pages=pages,
        publisher=publisher,
        doi=doi.lower() if doi else None,
        url=url,
        parser=parser_name,
    )

    # Lengvas pasitikejimas: AnyStyle tipiskai pateikia daugiau struktūros
    conf = 0.90
    if base.title:
        conf += 0.05
    if base.author or base.authors:
        conf += 0.03
    if base.year:
        conf += 0.02
    return ParsedReference(**{**base.__dict__, "confidence": min(1.0, conf)})


def _parse_bibliography_anystyle_cli(entries: list[str], *, anystyle_bin: str = "anystyle") -> list[ParsedReference]:
    """
    Naudoja AnyStyle CLI (`anystyle-cli`) ir grazina normalizuota CSL-JSON.
    Reikalauja, kad sistemoje butu prieinamas `anystyle` vykdomasis failas.
    """
    if not entries:
        return []

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as f:
        tmp_path = f.name
        for e in entries:
            f.write(norm_ws(e))
            f.write("\n")

    try:
        proc = subprocess.run(
            [anystyle_bin, "--stdout", "-f", "csl", "parse", tmp_path],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            "Nepavyko rasti `anystyle` komandos. Irasykite AnyStyle CLI: "
            "`gem install anystyle-cli` (reikes Ruby)."
        ) from e
    finally:
        try:
            import os

            os.unlink(tmp_path)
        except Exception:
            pass

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"AnyStyle CLI klaida (exit {proc.returncode}): {err[:500]}")

    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        out = (proc.stdout or "").strip()
        raise RuntimeError(f"AnyStyle CLI negrazino JSON (pirmos 500 zenk.): {out[:500]}") from e

    if not isinstance(parsed, list):
        raise RuntimeError("AnyStyle CLI grazino netiketa formata (tikejomes JSON masyvo).")

    refs: list[ParsedReference] = []
    for i, raw in enumerate(entries):
        item = parsed[i] if i < len(parsed) else None
        if not isinstance(item, dict):
            refs.append(parse_reference(raw))
            continue

        refs.append(_ref_from_csl_item(raw, item, parser_name="anystyle-cli"))

    return refs


def _parse_bibliography_anystyle_io(
    entries: list[str],
    *,
    base_url: str,
    access_token: str,
    timeout_seconds: float = 25.0,
) -> list[ParsedReference]:
    """
    Kviecia self-hostinta `anystyle.io` Rails aplikacija.

    Endpoint'as: POST {base_url}/parse.csl
    Parametrai: input=<tekstas>, access_token=<token>
    Atsakymas: CSL-JSON (list[dict]) kaip JSON.
    """
    if not entries:
        return []
    base = base_url.rstrip("/")
    url = f"{base}/parse.csl"

    payload = urllib.parse.urlencode(
        {"input": "\n".join(entries), "access_token": access_token}
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        raise RuntimeError(f"Nepavyko pasiekti AnyStyle serverio ({url}): {e}") from e

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"AnyStyle serveris negrazino JSON (pirmos 500 zenk.): {body[:500]}"
        ) from e

    if not isinstance(parsed, list):
        raise RuntimeError("AnyStyle serveris grazino netiketa formata (tikejomes JSON masyvo).")

    refs: list[ParsedReference] = []
    for i, raw in enumerate(entries):
        item = parsed[i] if i < len(parsed) else None
        if not isinstance(item, dict):
            refs.append(parse_reference(raw))
            continue
        refs.append(_ref_from_csl_item(raw, item, parser_name="anystyle-io"))

    return refs


def _try_parse_bibliography_anystyle_cli(entries: list[str], *, anystyle_bin: str) -> list[ParsedReference] | None:
    """
    Grazina None, jei CLI nepasiekiamas / nepavyksta paleisti.
    """
    bin_path = shutil.which(anystyle_bin) if anystyle_bin else None
    if not bin_path:
        return None
    try:
        return _parse_bibliography_anystyle_cli(entries, anystyle_bin=anystyle_bin)
    except Exception:
        return None


def _try_parse_bibliography_anystyle_io(
    entries: list[str],
    *,
    anystyle_base_url: str | None,
    anystyle_access_token: str | None,
    anystyle_timeout_seconds: float,
) -> list[ParsedReference] | None:
    """
    Grazina None, jei truksta konfigo arba serveris nepasiekiamas.
    """
    if not anystyle_base_url or not anystyle_access_token:
        return None
    try:
        return _parse_bibliography_anystyle_io(
            entries,
            base_url=anystyle_base_url,
            access_token=anystyle_access_token,
            timeout_seconds=anystyle_timeout_seconds,
        )
    except Exception:
        return None


def parse_bibliography_text(
    bibliography_text: str,
    parser: str = "regex-ensemble",
    *,
    anystyle_bin: str = "anystyle",
    anystyle_base_url: str | None = None,
    anystyle_access_token: str | None = None,
    anystyle_timeout_seconds: float = 25.0,
) -> list[ParsedReference]:
    entries = bibliography_to_entries(bibliography_text)
    if not entries:
        return []
    if parser == "auto":
        # 1) Jei sukonfiguruotas serveris — jis patogiausias (nereikia Ruby lokaliai)
        io_res = _try_parse_bibliography_anystyle_io(
            entries,
            anystyle_base_url=anystyle_base_url,
            anystyle_access_token=anystyle_access_token,
            anystyle_timeout_seconds=anystyle_timeout_seconds,
        )
        if io_res is not None:
            return io_res

        # 2) Kitu atveju bandom CLI (tikslus AnyStyle, bet reikia Ruby)
        cli_res = _try_parse_bibliography_anystyle_cli(entries, anystyle_bin=anystyle_bin)
        if cli_res is not None:
            return cli_res

        # 3) Fallback
        return [parse_reference(e) for e in entries]
    if parser == "regex-ensemble":
        return [parse_reference(e) for e in entries]
    if parser == "anystyle":
        return _parse_bibliography_anystyle_cli(entries, anystyle_bin=anystyle_bin)
    if parser in ("anystyle-io", "anystyle-http"):
        if not anystyle_base_url or not anystyle_access_token:
            raise ValueError("AnyStyle serveriui reikia `anystyle_base_url` ir `anystyle_access_token`.")
        return _parse_bibliography_anystyle_io(
            entries,
            base_url=anystyle_base_url,
            access_token=anystyle_access_token,
            timeout_seconds=anystyle_timeout_seconds,
        )
    raise ValueError(f"Nezinomas parseris: {parser}")
