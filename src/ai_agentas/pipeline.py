from __future__ import annotations

from dataclasses import dataclass, field

from ai_agentas.utils.bibliography import split_bibliography
from ai_agentas.utils.doc_readers import read_any

from ai_agentas.nodes.parse_bibliography import parse_bibliography_text, ParsedReference
from ai_agentas.nodes.export_bibtex import export_bibtex, BibtexExport
from ai_agentas.nodes.export_ris import export_ris
from ai_agentas.nodes.export_csljson import export_csljson
from ai_agentas.nodes.duplicates import find_duplicates, DuplicatePair
from ai_agentas.nodes.csl_formatter import format_bibliography
from ai_agentas.nodes.update_docx import update_docx_placeholders, UpdateResult
from ai_agentas.utils.crossref import enrich_refs_with_crossref


@dataclass(frozen=True)
class RunConfig:
    update_docx: bool = True
    csl_style: str = "APA 7"
    parser: str = "auto"
    anystyle_bin: str = "anystyle"
    anystyle_base_url: str | None = None
    anystyle_access_token: str | None = None
    anystyle_timeout_seconds: float = 25.0
    crossref_enabled: bool = True
    crossref_mailto: str | None = None
    crossref_rows: int = 5
    crossref_timeout_seconds: float = 20.0


@dataclass(frozen=True)
class RunResult:
    source_name: str
    extracted_body: str
    extracted_bibliography: str
    refs: list[ParsedReference]
    bibtex: BibtexExport
    ris: str
    csljson: str
    formatted_bibliography: str
    updated_docx: UpdateResult | None


def run_pipeline(input_path: str, config: RunConfig) -> RunResult:
    """Apdoroja viena dokumenta."""
    doc = read_any(input_path)
    split = split_bibliography(doc.text)

    refs = parse_bibliography_text(
        split.bibliography_text,
        parser=config.parser,
        anystyle_bin=config.anystyle_bin,
        anystyle_base_url=config.anystyle_base_url,
        anystyle_access_token=config.anystyle_access_token,
        anystyle_timeout_seconds=config.anystyle_timeout_seconds,
    )
    if config.crossref_enabled and refs:
        refs = enrich_refs_with_crossref(
            refs,
            mailto=config.crossref_mailto,
            timeout_seconds=config.crossref_timeout_seconds,
            rows=config.crossref_rows,
        )
    bib = export_bibtex(refs)
    ris = export_ris(refs)
    csljson = export_csljson(refs)
    formatted = format_bibliography(refs, config.csl_style)

    updated = None
    if config.update_docx and doc.kind == "docx" and refs:
        citekeys_in_order = [bib.citekey_by_index[i] for i in range(len(refs))]
        updated = update_docx_placeholders(
            input_docx_path=input_path, citekeys_in_order=citekeys_in_order
        )

    return RunResult(
        source_name=doc.source_path,
        extracted_body=split.body_text,
        extracted_bibliography=split.bibliography_text,
        refs=refs,
        bibtex=bib,
        ris=ris,
        csljson=csljson,
        formatted_bibliography=formatted,
        updated_docx=updated,
    )


@dataclass(frozen=True)
class BatchResult:
    results: list[RunResult]
    all_refs: list[ParsedReference]
    merged_bibtex: str
    merged_ris: str
    merged_csljson: str
    merged_formatted: str
    duplicates: list[DuplicatePair]


def run_batch(input_paths: list[str], config: RunConfig) -> BatchResult:
    """Apdoroja kelis dokumentus ir sujungia rezultatus."""
    results: list[RunResult] = []
    all_refs: list[ParsedReference] = []

    for path in input_paths:
        res = run_pipeline(path, config)
        results.append(res)
        all_refs.extend(res.refs)

    merged_bib = export_bibtex(all_refs)
    merged_ris = export_ris(all_refs)
    merged_csljson = export_csljson(all_refs)
    merged_formatted = format_bibliography(all_refs, config.csl_style)
    dupes = find_duplicates(all_refs)

    return BatchResult(
        results=results,
        all_refs=all_refs,
        merged_bibtex=merged_bib.bibtex,
        merged_ris=merged_ris,
        merged_csljson=merged_csljson,
        merged_formatted=merged_formatted,
        duplicates=dupes,
    )
