from __future__ import annotations

import sys
from pathlib import Path

# Uztikriname, kad "src" paketas butu randamas (svarbu Streamlit Cloud deploy'ui)
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import os

import streamlit as st
from dotenv import load_dotenv

from ai_agentas.pipeline import RunConfig, run_batch
from ai_agentas.nodes.csl_formatter import SUPPORTED_STYLES


load_dotenv()

st.set_page_config(page_title="Citatos -> Zotero (offline)", layout="wide")
st.title("Citatos -> Zotero (offline)")

st.write(
    "Ikelkite viena ar kelis `.docx` / `.pdf` dokumentus. Agentas:\n"
    "1. Atskirs **literaturos sarasa** nuo pagrindinio teksto\n"
    "2. Isparsuos saltinius (autorius, metai, pavadinimas, DOI...)\n"
    "3. Sugeneruos **BibTeX**, **RIS**, **CSL-JSON** importui i Zotero\n"
    "4. Suformatuos bibliografija pagal pasirinkta stilu (APA, IEEE, ISO 690, MLA)\n"
    "5. Aptiks **dublikatus** tarp keliu dokumentu\n"
    "6. (Jei DOCX) pakeis citatas i `[@citekey]` placeholderius"
)

# --- Sidebar ---
with st.sidebar:
    st.subheader("Nustatymai")
    csl_style = st.selectbox("Citavimo stilius", SUPPORTED_STYLES, index=0)
    parser_choice = st.selectbox(
        "Parseris",
        [
            "Auto (rekomenduojama)",
            "Regex (numatytas, be Ruby)",
            "AnyStyle CLI (reikia `anystyle-cli`)",
            "AnyStyle Server (self-hosted anystyle.io)",
        ],
        index=0,
    )

    anystyle_bin = os.getenv("ANYSTYLE_BIN", "anystyle")
    anystyle_base_url = os.getenv("ANYSTYLE_IO_BASE_URL", "")
    anystyle_access_token = os.getenv("ANYSTYLE_IO_ACCESS_TOKEN", "")

    if parser_choice.startswith("AnyStyle CLI"):
        anystyle_bin = st.text_input("AnyStyle komanda (ANYSTYLE_BIN)", value=anystyle_bin)

    if parser_choice.startswith("AnyStyle Server"):
        anystyle_base_url = st.text_input("AnyStyle serverio URL (ANYSTYLE_IO_BASE_URL)", value=anystyle_base_url)
        anystyle_access_token = st.text_input(
            "Access token (ANYSTYLE_IO_ACCESS_TOKEN)",
            value=anystyle_access_token,
            type="password",
            help="Tai NE anystyle.io UI slaptažodis. Self-hostintame anystyle.io jis saugomas `accounts.access_token`.",
        )

    update_docx = st.checkbox("Atnaujinti DOCX citatas (placeholderiai)", value=True)
    crossref_enabled = st.checkbox(
        "Crossref patikslinimas (internetu, rekomenduojama)",
        value=(os.getenv("CROSSREF_ENABLED", "true").lower() == "true"),
    )
    export_format = st.selectbox("Eksporto formatas", ["BibTeX (.bib)", "RIS (.ris)", "CSL-JSON (.json)", "Visi formatai"])
    st.markdown("---")
    st.caption(
        "Sis agentas veikia **offline**. Pagal nutylejima naudoja Python regex; "
        "pasirinkus AnyStyle galima naudoti lokalu CLI arba self-hostinta anystyle.io serveri. "
        "Sugeneruota faila importuokite i Zotero: File -> Import."
    )

# --- Upload ---
uploaded_files = st.file_uploader(
    "Dokumentai",
    type=["docx", "pdf", "txt"],
    accept_multiple_files=True,
)

if not uploaded_files:
    st.info("Ikelkite bent viena dokumenta.")
    st.stop()

workdir = Path("_uploaded")
workdir.mkdir(parents=True, exist_ok=True)
input_paths: list[str] = []

for uf in uploaded_files:
    p = workdir / uf.name
    p.write_bytes(uf.getvalue())
    input_paths.append(str(p))

parser_key = "regex-ensemble"
if parser_choice.startswith("Auto"):
    parser_key = "auto"
elif parser_choice.startswith("AnyStyle CLI"):
    parser_key = "anystyle"
elif parser_choice.startswith("AnyStyle Server"):
    parser_key = "anystyle-io"

cfg = RunConfig(
    update_docx=update_docx,
    csl_style=csl_style,
    parser=parser_key,
    anystyle_bin=anystyle_bin,
    anystyle_base_url=anystyle_base_url.strip() or None,
    anystyle_access_token=anystyle_access_token.strip() or None,
    crossref_enabled=crossref_enabled,
    crossref_mailto=(os.getenv("CROSSREF_MAILTO") or "").strip() or None,
    crossref_rows=int(os.getenv("CROSSREF_ROWS", "5")),
    crossref_timeout_seconds=float(os.getenv("CROSSREF_TIMEOUT_SECONDS", "20")),
)

with st.spinner("Apdorojama..."):
    try:
        batch = run_batch(input_paths, cfg)
    except Exception as e:
        st.error(f"Klaida: {e}")
        st.stop()

# --- Tabs ---
tab_overview, tab_export, tab_formatted, tab_duplicates, tab_details = st.tabs([
    "Apzvalga",
    "Eksportas",
    "Suformatuota bibliografija",
    "Dublikatai",
    "Dokumentu detales",
])

# ==================== Apzvalga ====================
with tab_overview:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Dokumentu", len(batch.results))
    col2.metric("Viso saltiniu", len(batch.all_refs))
    col3.metric("Galimi dublikatai", len(batch.duplicates))
    low_conf = sum(1 for r in batch.all_refs if r.confidence < 0.55)
    col4.metric("Zemo pasitikejimo", low_conf)

    st.subheader("Visi rasti saltiniai")
    if batch.all_refs:
        st.dataframe(
            [
                {
                    "#": i + 1,
                    "autorius": r.author or "--",
                    "metai": r.year or "--",
                    "pavadinimas": r.title or "--",
                    "zurnalas": r.journal or "",
                    "DOI": r.doi or "",
                    "pasitikejimas": f"{int(r.confidence * 100)}%",
                    "parseris": r.parser,
                }
                for i, r in enumerate(batch.all_refs)
            ],
            use_container_width=True,
            hide_index=True,
        )
        if low_conf:
            st.warning("Dalis irasu yra zemo pasitikejimo. Rekomenduojama juos perziureti ranka.")
    else:
        st.info("Saltiniu nerasta.")

# ==================== Eksportas ====================
with tab_export:
    st.subheader("Atsisiuskite saltinius pasirinktu formatu")

    show_bib = export_format in ("BibTeX (.bib)", "Visi formatai")
    show_ris = export_format in ("RIS (.ris)", "Visi formatai")
    show_csl = export_format in ("CSL-JSON (.json)", "Visi formatai")

    if show_bib:
        st.markdown("**BibTeX**")
        st.code(batch.merged_bibtex, language="bibtex")
        st.download_button(
            "Atsisiusti references.bib",
            data=batch.merged_bibtex.encode("utf-8"),
            file_name="references.bib",
            mime="text/x-bibtex",
            key="dl_bib",
        )

    if show_ris:
        st.markdown("**RIS**")
        st.code(batch.merged_ris)
        st.download_button(
            "Atsisiusti references.ris",
            data=batch.merged_ris.encode("utf-8"),
            file_name="references.ris",
            mime="application/x-research-info-systems",
            key="dl_ris",
        )

    if show_csl:
        st.markdown("**CSL-JSON**")
        st.code(batch.merged_csljson, language="json")
        st.download_button(
            "Atsisiusti references.json",
            data=batch.merged_csljson.encode("utf-8"),
            file_name="references.json",
            mime="application/json",
            key="dl_csljson",
        )

# ==================== Suformatuota bibliografija ====================
with tab_formatted:
    st.subheader(f"Bibliografija ({csl_style} stilius)")
    if batch.merged_formatted.strip():
        st.markdown(batch.merged_formatted)
        st.download_button(
            "Atsisiusti bibliografija.txt",
            data=batch.merged_formatted.encode("utf-8"),
            file_name=f"bibliografija_{csl_style.replace(' ', '_')}.txt",
            mime="text/plain",
            key="dl_formatted",
        )
    else:
        st.info("Nera saltiniu formatavimui.")

# ==================== Dublikatai ====================
with tab_duplicates:
    st.subheader("Galimi dublikatai tarp visu dokumentu")
    if batch.duplicates:
        st.warning(f"Rasta **{len(batch.duplicates)}** galimu dublikatu.")
        for d in batch.duplicates:
            with st.expander(
                f"Panasumas {d.score:.0f}% -- {d.ref_a.title or '?'} <-> {d.ref_b.title or '?'}"
            ):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown(f"**Saltinis A** (#{d.index_a + 1})")
                    st.text(d.ref_a.raw[:300])
                with c2:
                    st.markdown(f"**Saltinis B** (#{d.index_b + 1})")
                    st.text(d.ref_b.raw[:300])
                st.caption(f"Priezastis: {d.reason}")
    else:
        st.success("Dublikatu nerasta!")

# ==================== Dokumentu detales ====================
with tab_details:
    st.subheader("Kiekvieno dokumento detales")
    for res in batch.results:
        fname = Path(res.source_name).name
        with st.expander(f"{fname} -- {len(res.refs)} saltiniu"):
            if res.extracted_bibliography.strip():
                st.text_area(
                    "Bibliografija (raw)",
                    res.extracted_bibliography,
                    height=200,
                    key=f"bib_{fname}",
                )
            else:
                st.warning("Bibliografijos blokas nerastas.")

            if res.refs:
                st.dataframe(
                    [
                        {
                            "#": i + 1,
                            "autorius": r.author or "--",
                            "metai": r.year or "--",
                            "pavadinimas": r.title or "--",
                            "pasitikejimas": f"{int(r.confidence * 100)}%",
                            "parseris": r.parser,
                        }
                        for i, r in enumerate(res.refs)
                    ],
                    use_container_width=True,
                    hide_index=True,
                    key=f"df_{fname}",
                )

            if res.updated_docx:
                out_path = Path(res.updated_docx.output_path)
                st.success(f"Pakeistu citatu: **{res.updated_docx.replacements}**")
                st.download_button(
                    f"Atsisiusti atnaujinta {fname}",
                    data=out_path.read_bytes(),
                    file_name=out_path.name,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key=f"dl_docx_{fname}",
                )
