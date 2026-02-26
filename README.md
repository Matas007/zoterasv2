# AI agentas: DOCX/PDF citatos → Zotero

Šis projektas yra **offline** agentas, kuris:

- nuskaito dokumentą (`.docx` arba `.pdf`)
- atpažįsta **literatūros sąrašą** (bibliografiją) dokumento gale
- kiekvieną šaltinį išparsuoja **Python regex** parseriais (autorius, metai, pavadinimas, DOI...) arba (pasirinktinai) **AnyStyle**
- sugeneruoja **BibTeX** (`references.bib`) importui į Zotero
- (jei `.docx`) dokumente pakeičia citatas į **atsekamus placeholderius** `[@citekey]`

> **0 API. 0 interneto.**
> Viskas veikia lokaliai; **Ruby/AnyStyle yra tik pasirinktinai** (jei norite tikslesnio parsinimo).

## Reikalavimai

- Python 3.10+

### Pasirinktinai: AnyStyle (geresnis parsinimas)

Jei norite naudoti AnyStyle (tas pats variklis kaip `anystyle.io`), įsidiekite Ruby ir CLI:

```bash
gem install anystyle-cli
```

Tada Streamlit šoninėje juostoje pasirinkite **Parseris → AnyStyle**.

### Paprasčiausias režimas: Auto (rekomenduojama)

Jei pasirinksite **Parseris → Auto**, aplikacija:
- pirma bandys **AnyStyle Server** (jei sukonfigūruota `ANYSTYLE_IO_BASE_URL` + `ANYSTYLE_IO_ACCESS_TOKEN`)
- jei nėra — bandys **AnyStyle CLI** (jei įdiegtas `anystyle-cli`)
- jei nėra — naudos esamą **Python regex** fallback

### Tikslumui (be AnyStyle): Crossref patikslinimas

Jei norite geresnio tikslumo vien tik su Python (be Ruby/AnyStyle), įjunkite **Crossref patikslinimą**.
Tai vienas Streamlit deploy, bet reikalingas internetas (Crossref API).

`.env`:
- `CROSSREF_ENABLED=true`
- `CROSSREF_MAILTO=your-email@example.com` (rekomenduojama)

### Pasirinktinai: AnyStyle kaip serveris (self-hostintas anystyle.io)

`anystyle.io` web aplikacija yra atviro kodo (Rails). Ji turi HTTP endpoint'ą:
- `POST /parse.csl` su form parametru `input` ir `access_token`

Svarbu:
- Viešas `anystyle.io` paprastai reikalauja `access_token`, todėl „tiesiogiai naudoti jų hostą“ dažniausiai nepavyks be savo tokeno.
- Jei **self-hostinate** `anystyle.io`, tokeną galite susikurti per Rails konsolę, pvz.:

```bash
./bin/rails console
Account.create!(user: "you@example.com").access_token
```

Tada `.env` įrašykite:
- `ANYSTYLE_IO_BASE_URL=https://jusu-serveris`
- `ANYSTYLE_IO_ACCESS_TOKEN=...`

Ir Streamlit UI pasirinkite **Parseris → AnyStyle Server**.

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
3. **Parseris** — iš kiekvieno bibliografijos įrašo ištraukia: autorių, metus, pavadinimą, žurnalą, DOI, URL, puslapius, tomą
   - Numatyta: **Python regex** (be papildomų priklausomybių)
   - Pasirinktinai: **AnyStyle CLI** (`anystyle-cli`)
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
