from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DocumentText:
    text: str
    source_path: str
    kind: str  # "docx" | "pdf" | "txt"


def read_docx(path: str) -> DocumentText:
    from docx import Document  # python-docx

    p = Path(path)
    doc = Document(str(p))
    parts: list[str] = []
    for para in doc.paragraphs:
        parts.append(para.text or "")
    # tables (dažnai literatūra nebūna, bet jei yra – įtraukiam)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                t = (cell.text or "").strip()
                if t:
                    parts.append(t)
    return DocumentText(text="\n".join(parts).strip(), source_path=str(p), kind="docx")


def read_pdf(path: str) -> DocumentText:
    import fitz  # pymupdf

    p = Path(path)
    doc = fitz.open(str(p))
    parts: list[str] = []
    for page in doc:
        parts.append(page.get_text("text"))
    return DocumentText(text="\n".join(parts).strip(), source_path=str(p), kind="pdf")


def read_text(path: str) -> DocumentText:
    p = Path(path)
    return DocumentText(text=p.read_text(encoding="utf-8", errors="ignore"), source_path=str(p), kind="txt")


def read_any(path: str) -> DocumentText:
    p = Path(path)
    suf = p.suffix.lower()
    if suf == ".docx":
        return read_docx(str(p))
    if suf == ".pdf":
        return read_pdf(str(p))
    return read_text(str(p))

