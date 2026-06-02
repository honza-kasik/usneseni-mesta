# Archiv usnesení Litovel

Tato větev pipeline zpracovává historické stránky:

- https://www.litovel.eu/cs/mesto/zastupitelstvo-mesta/usneseni-zastupitelstva-archiv.html
- https://www.litovel.eu/cs/mesto/rada-mesta/usneseni-rady-archiv.html

Je oddělená od hlavní pipeline pro aktuální usnesení. Parent dokumenty
`archive_document` zůstávají auditním zdrojem. Konzervativní splitter z nich
tam, kde je to spolehlivé, vytváří child záznamy `archive_resolution`.

Výjimkou jsou archivní dokumenty se současným interním formátem: pokud
extrahovaný text obsahuje bloky `Číslo: RM/.../.../...` nebo
`Číslo: ZM/.../.../...`, lze je přes `tools/archive_promote_current.py`
doplnit do `work/phase1` jako běžná usnesení současné pipeline. Tyto dokumenty
se potom ve veřejném archivním indexu vynechávají, aby nevznikaly duplicitní
výsledky.

Praktická hranice je kanonické ID, ne zdrojová stránka. Záznamy, které mají
spolehlivý tvar `RM/.../.../...` nebo `ZM/.../.../...`, patří do současné
pipeline a zachovávají archivní původ v metadatech (`source=archive`,
`archive_document_id`, `source_pdf`). Archivní index zůstává pro dokumenty,
které takto bezpečně převést nejdou.

## Příkazy

ZM větev má výchozí cesty, takže ji lze spustit bez parametrů:

```bash
python tools/archive_crawl_zm.py
python tools/archive_download.py
python tools/archive_extract_text.py
python tools/archive_build_records.py
python tools/archive_report.py
python tools/archive_split_resolutions.py
```

RM větev používá stejné nástroje s vlastními cestami:

```bash
python tools/archive_crawl_rm.py
python tools/archive_download.py \
  --inventory work/archive_rm/inventory.json \
  --files-dir work/archive_rm/files \
  --output work/archive_rm/inventory.json
python tools/archive_extract_text.py \
  --inventory work/archive_rm/inventory.json \
  --text-dir work/archive_rm/text \
  --output work/archive_rm/extraction.json
python tools/archive_build_records.py \
  --inventory work/archive_rm/inventory.json \
  --extraction work/archive_rm/extraction.json \
  --output work/archive_rm/archive_documents.json
python tools/archive_report.py \
  --inventory work/archive_rm/inventory.json \
  --records work/archive_rm/archive_documents.json \
  --extraction work/archive_rm/extraction.json \
  --json-output work/archive_rm/report.json \
  --md-output work/archive_rm/report.md
python tools/archive_split_resolutions.py \
  --input work/archive_rm/archive_documents.json \
  --output work/archive_rm/archive_resolutions.json \
  --report work/archive_rm/split_report.json \
  --report-md work/archive_rm/split_report.md
```

Po obou větvích se doplní moderně strukturované archivní dokumenty do současné
pipeline a vyloučí se z veřejného archivního výstupu:

```bash
python tools/archive_promote_current.py --archive-root work/archive_zm --archive-root work/archive_rm
```

Výstupy:

- `work/archive_zm/inventory.json`
- `work/archive_zm/files/`
- `work/archive_zm/text/`
- `work/archive_zm/extraction.json`
- `work/archive_zm/archive_documents.json`
- `work/archive_zm/archive_resolutions.json`
- `work/archive_zm/report.json`
- `work/archive_zm/report.md`
- `work/archive_zm/split_report.json`
- `work/archive_zm/split_report.md`
- stejné soubory pod `work/archive_rm/`
- `work/archive_current_promoted.json`
- `work/archive_zm/search_index/`
- `work/archive_zm/search_index_report.json`

Veřejný archivní fulltextový index pro statický web se sestaví stejným nástrojem
s cílovým exportem. Výchozí `--resolutions` míří na
`work/archive_zm/archive_resolutions.json`, takže po spuštění splitteru ZM
větev automaticky indexuje jednotlivá child usnesení místo duplicitních parent
dokumentů. Pro společný RM+ZM export je potřeba uvést obě větve:

```bash
python tools/archive_build_search_index.py \
  --input work/archive_rm/archive_documents.json \
  --input work/archive_zm/archive_documents.json \
  --resolutions work/archive_rm/archive_resolutions.json \
  --resolutions work/archive_zm/archive_resolutions.json \
  --promoted-report work/archive_current_promoted.json \
  --output ../litovle.cz/assets/usneseni/archive \
  --report work/archive_zm/search_index_report.json
```

Detailní stránky a organizovaný archivní přehled se vyexportují zvlášť:

```bash
python tools/archive_export_static.py \
  --input work/archive_rm/archive_documents.json \
  --input work/archive_zm/archive_documents.json \
  --resolutions work/archive_rm/archive_resolutions.json \
  --resolutions work/archive_zm/archive_resolutions.json \
  --promoted-report work/archive_current_promoted.json \
  --output ../litovle.cz
```

Pokud je potřeba přegenerovat jen split child záznamy pro jednu větev, splitter
lze spustit samostatně:

```bash
python tools/archive_split_resolutions.py \
  --input work/archive_zm/archive_documents.json \
  --output work/archive_zm/archive_resolutions.json \
  --report work/archive_zm/split_report.json \
  --report-md work/archive_zm/split_report.md
```

Do veřejného indexu se zařadí jen archivní záznamy splňující:

- `type=archive_document` nebo `type=archive_resolution`
- `kind=usneseni`
- neprázdný `search_text`
- u parent dokumentu `text_quality.quality_flag` je `text_ok` nebo
  `short_text`

Pokud má parent dokument child `archive_resolution`, indexují se child usnesení
a parent dokument se vynechá, aby neduplikoval výsledky. Pokud dokument
splitter nerozdělí, zůstává ve vyhledávání jako fallback `archive_document`.
Oba typy výsledků mají vlastní permalink pod `/usneseni/archiv/...`; původní
PDF/DOC je na detailu jen jako sekundární odkaz.

Veřejná stránka `/usneseni/archiv/` není serverový listing. Export vytváří
přehled po rocích, orgánech a schůzích/dokumentech. Nejnovější rok je otevřený,
starší roky jsou sbalené. U rozdělených dokumentů vede řádek na stránku schůze
se seznamem jednotlivých archivních usnesení a vpravo ukazuje počet usnesení.
U nerozdělených fallback dokumentů řádek vede přímo na detail dokumentu; v řádku
není samostatný štítek `dokument`, počet nerozdělených dokumentů je jen v
horním souhrnu.

## Zpracování odkazů

- Přímé odkazy `/filemanager/files/...` se ukládají jako `direct_file`.
- Flipbook odkazy `flipbook_new.inc.php?...fileID=...` se berou jen jako
  ukazatel na původní soubor.
- Pokud je u flipbooku v HTML sousední přímý `link_soubor` se stejným
  `fileID`, použije se jako `resolved_file_url`.
- Pokud se soubor nepodaří rozřešit ani ve stahovací fázi, položka zůstane ve
  stavu `needs_resolution`.

## Extrakce textu

- PDF: `pdfplumber`
- DOCX: `python-docx`
- DOC: `libreoffice --headless`, potom fallback `antiword`, potom `catdoc`

OCR zatím není součástí pipeline. Dokumenty bez textu nebo s krátkým textem jsou
vidět v quality reportu. Extrakce každému dokumentu přiřadí jeden
`quality_flag`:

- `text_ok`
- `short_text`
- `empty_text`
- `probably_binary_garbage`
- `extraction_failed`

## Audit metadat

Inventář ukládá kromě `year`, `meeting_no` a `meeting_date` také zdroj nebo
důvod:

- `year_source`: `date`, `title`, `section`, `none`
- `meeting_no_source`: `title`, `none`
- `date_missing_reason`: například `no_date_in_title`,
  `generic_voting_title`, `meeting_only_historical_title`

Report obsahuje souhrn `metadata_quality`, duplicity URL/ID, tabulku podle
období a roku a počty podle `quality_flag`.

## Splitter usnesení

Splitter je záměrně konzervativní. Dělí jen jasné bloky jako `Usnesení č.`,
`Usnesení ZM č.`, samostatné číslo usnesení následované rozhodovacím slovesem
nebo číslované body typu `1. Bere na vědomí`. Každé child usnesení obsahuje
přesný textový výřez z parent dokumentu a `source_span` s pozicí ve zdrojovém
textu.

Pokud najde žádnou nebo jen jednu hranici, příliš krátké bloky, konfliktní
číslování nebo podezřele husté hranice, dokument nerozdělí a důvod zapíše do
`split_report`.

## Limity MVP

- Archivní dokumenty bez současného interního formátu nejsou přimíchány do
  současného indexu moderních usnesení; mají samostatný výstup
  `assets/usneseni/archive/`.
- Hlasování se ukládá jako `kind=hlasovani` nebo `kind=hlasovani_aklamaci`, ale
  neindexuje se jako usnesení.
- Splitter se nesnaží uhodnout každé historické usnesení; nejisté dokumenty
  nechává jako fallback dokumenty.
- Chyba jednoho souboru nezastaví celý ingest; chyba je zapsaná do reportu.
