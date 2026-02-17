# AI agentas: DOCX/PDF citatos → Zotero

Šis projektas yra **offline** agentas, kuris:

- nuskaito dokumentą (`.docx` arba `.pdf`)
- atpažįsta **literatūros sąrašą** (bibliografiją) dokumento gale
- kiekvieną šaltinį išparsuoja Python regex parseriais (autorius, metai, pavadinimas, DOI...)
- sugeneruoja **BibTeX** (`references.bib`) importui į Zotero
- (jei `.docx`) dokumente pakeičia citatas į **atsekamus placeholderius** `[@citekey]`

> **0 API. 0 interneto. 0 Ruby.**
> Viskas veikia lokaliai, tik su Python.

## Reikalavimai

- Python 3.10+

## Diegimas

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## Paleidimas

```bash
streamlit run app.py
```

Atsidarys naršyklė su Streamlit UI. Įkelkite `.docx` arba `.pdf` dokumentą.

## Kaip veikia

Pipeline (4 žingsniai):

1. **Reader** — ištraukia tekstą iš DOCX/PDF
2. **Bibliography splitter** — atskiria pagrindinio teksto kūną nuo literatūros sąrašo
3. **Python regex parser** — iš kiekvieno bibliografijos įrašo ištraukia: autorių, metus, pavadinimą, žurnalą, DOI, URL, puslapius, tomą
4. **BibTeX exporter** — sugeneruoja `references.bib`, kurį galite importuoti į Zotero: `File → Import → BibTeX`
5. **DOCX updater** — (pasirenkama) pakeičia citatas dokumente į `[@citekey]` placeholderius

## Importas į Zotero

1. Atsisiųskite `references.bib` iš Streamlit UI
2. Zotero: **File → Import…** → pasirinkite `.bib` failą
3. Pasirinkite kolekciją ir importuokite

## Projekto struktūra

```
app.py                           ← Streamlit UI
src/ai_agentas/
├── pipeline.py                  ← pagrindinis pipeline
├── nodes/
│   ├── parse_bibliography.py    ← Python regex bibliografijos parseris
│   ├── export_bibtex.py         ← BibTeX generavimas
│   └── update_docx.py           ← citatų keitimas DOCX'e
└── utils/
    ├── bibliography.py          ← bibliografijos atskyrimas
    ├── doc_readers.py           ← DOCX/PDF skaitymas
    ├── text_norm.py             ← teksto normalizavimas
    └── citekeys.py              ← citekey generavimas
```
