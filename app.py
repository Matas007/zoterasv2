from __future__ import annotations

import sys
from pathlib import Path

# Užtikriname, kad „src" paketas būtų randamas (svarbu Streamlit Cloud deploy'ui)
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import streamlit as st

from ai_agentas.pipeline import RunConfig, run_pipeline


st.set_page_config(page_title="Citatos → Zotero (offline MVP)", layout="wide")
st.title("Citatos → Zotero (offline MVP)")

st.write(
    "Įkelkite `.docx` (arba `.pdf`). Agentas:\n"
    "1. Atskirs **literatūros sąrašą** (bibliografiją) nuo pagrindinio teksto\n"
    "2. Kiekvieną šaltinį išparsuos (autorius, metai, pavadinimas, DOI...)\n"
    "3. Sugeneruos **`references.bib`** (importui į Zotero)\n"
    "4. (Jei DOCX) pakeis citatas į `[@citekey]` placeholderius"
)

uploaded = st.file_uploader("Dokumentas", type=["docx", "pdf", "txt"])

with st.sidebar:
    st.subheader("Nustatymai")
    update_docx = st.checkbox("Atnaujinti DOCX citatas (placeholderiai)", value=True)
    st.markdown("---")
    st.caption(
        "Šis agentas veikia **pilnai offline** — be jokių API ar interneto. "
        "Sugeneruotą `.bib` failą importuokite į Zotero: "
        "File → Import → BibTeX."
    )

if uploaded is None:
    st.stop()

workdir = Path("_uploaded")
workdir.mkdir(parents=True, exist_ok=True)
in_path = workdir / uploaded.name
in_path.write_bytes(uploaded.getvalue())

cfg = RunConfig(update_docx=update_docx)

with st.spinner("Apdorojama..."):
    try:
        res = run_pipeline(str(in_path), cfg)
    except Exception as e:
        st.error(f"Klaida: {e}")
        st.stop()

col1, col2 = st.columns(2)

with col1:
    st.subheader("Ištraukta bibliografija")
    if res.extracted_bibliography.strip():
        st.text_area("Bibliografija (raw tekstas)", res.extracted_bibliography, height=300)
    else:
        st.warning("Bibliografijos blokas nerastas. Patikrinkite, ar dokumente yra „Literatūra" / „References" skyrius.")

    st.subheader("BibTeX (importui į Zotero)")
    st.code(res.bibtex.bibtex, language="bibtex")
    st.download_button(
        "⬇ Atsisiųsti references.bib",
        data=res.bibtex.bibtex.encode("utf-8"),
        file_name="references.bib",
        mime="text/x-bibtex",
    )

with col2:
    st.subheader("Rastos nuorodos")
    st.write(f"Įrašų skaičius: **{len(res.refs)}**")
    if res.refs:
        st.dataframe(
            [
                {
                    "#": i + 1,
                    "citekey": res.bibtex.citekey_by_index.get(i, ""),
                    "autorius": r.author or "—",
                    "metai": r.year or "—",
                    "pavadinimas": r.title or "—",
                    "DOI": r.doi or "",
                    "raw": (r.raw[:180] + "…") if len(r.raw) > 180 else r.raw,
                }
                for i, r in enumerate(res.refs)
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Šaltinių nerasta.")

    st.subheader("Atnaujintas dokumentas")
    if res.updated_docx:
        out_path = Path(res.updated_docx.output_path)
        st.success(f"Pakeistų citatų: **{res.updated_docx.replacements}**")
        st.download_button(
            "⬇ Atsisiųsti atnaujintą DOCX",
            data=out_path.read_bytes(),
            file_name=out_path.name,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    else:
        st.info("DOCX neatnaujintas (ne DOCX formatas, išjungta, arba nerasta įrašų).")
