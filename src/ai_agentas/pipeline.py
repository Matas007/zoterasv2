from __future__ import annotations

from dataclasses import dataclass

from ai_agentas.utils.bibliography import split_bibliography
from ai_agentas.utils.doc_readers import read_any

from ai_agentas.nodes.parse_bibliography import parse_bibliography_text, ParsedReference
from ai_agentas.nodes.export_bibtex import export_bibtex, BibtexExport
from ai_agentas.nodes.update_docx import update_docx_placeholders, UpdateResult


@dataclass(frozen=True)
class RunConfig:
    update_docx: bool = True


@dataclass(frozen=True)
class RunResult:
    extracted_body: str
    extracted_bibliography: str
    refs: list[ParsedReference]
    bibtex: BibtexExport
    updated_docx: UpdateResult | None


def run_pipeline(input_path: str, config: RunConfig) -> RunResult:
    doc = read_any(input_path)
    split = split_bibliography(doc.text)

    refs = parse_bibliography_text(split.bibliography_text)
    bib = export_bibtex(refs)

    updated = None
    if config.update_docx and doc.kind == "docx" and refs:
        citekeys_in_order = [bib.citekey_by_index[i] for i in range(len(refs))]
        updated = update_docx_placeholders(
            input_docx_path=input_path, citekeys_in_order=citekeys_in_order
        )

    return RunResult(
        extracted_body=split.body_text,
        extracted_bibliography=split.bibliography_text,
        refs=refs,
        bibtex=bib,
        updated_docx=updated,
    )
