# Readability plan for resolutions and budget measures

## Goal

Make the public pages understandable to residents without weakening the audit trail.

The current export is technically useful: it preserves IDs, dates, links, RZ rows, amounts, codes, and notes. The next step is to add a human-readable layer that answers:

- What changed?
- Why did it change?
- How much money moved?
- Which public service, place, school, association, or project is affected?
- Where can I verify the official source?

The official data must remain visible, but it should not be the first thing a non-specialist has to decode.

## Principles

- Keep the official record intact. Do not hide IDs, links, source PDFs, or accounting codes.
- Put plain-language meaning first, accounting detail second.
- Prefer deterministic extraction before manual editing.
- Make every generated summary traceable to parsed source text.
- Avoid pretending the system understands more than it does. If confidence is low, show a neutral fallback.
- Add manual overrides later only where deterministic summaries are awkward or misleading.

## Current state

Resolution pages can now link to budget measures in two ways:

- `Odkazováno z rozpočtového opatření RO/...` when the RO PDF header lists the resolution.
- `Rozpočtová změna ...` when the resolution text explicitly mentions an RZ identifier or range.

RO detail pages are grouped by RZ. Each RZ has:

- a clickable heading and anchor,
- an explanatory note when available,
- one or more accounting rows,
- hidden technical codes in expandable details.

Year pages such as `/usneseni/2026/` show RO links in the same compact chip style as RM/ZM meetings.

This is a good base, but the pages still read as administrative records, not as citizen-facing explanations.

## Phase 1: Better deterministic RZ summaries

Add a generated `summary` object for each RZ during RO parsing or export preparation.

Target shape:

```json
{
  "budget_change_id": "69/2026/RM",
  "plain_title": "Dotace pro ZŠ a MŠ Nasobůrky z OP JAK",
  "plain_reason": "Město přijalo účelovou dotaci od MŠMT určenou pro školu.",
  "money_summary": {
    "income_total": 576810.80,
    "expense_total": 576810.80,
    "financing_total": 0
  },
  "confidence": "generated"
}
```

Rendering target:

```text
RZ 69/2026/RM
Dotace pro ZŠ a MŠ Nasobůrky z OP JAK

Město přijalo účelovou dotaci od MŠMT určenou pro školu.

Příjmy: +576 810,80 Kč
Výdaje: +576 810,80 Kč
2 účetní řádky
```

Implementation rules:

- Use the note text as the primary source for `plain_reason`.
- Derive `plain_title` from the shortest meaningful row description or first sentence of the note.
- Strip repeated administrative prefixes such as `Dne ... požádal`, where a better object phrase is present in row descriptions.
- Keep current row descriptions below the summary.
- Aggregate amounts by section type: `prijmy`, `vydaje`, `financovani`.
- Show totals only when they are meaningful. If a section has both positive and negative rows, show net and movement separately only if needed.

Fallbacks:

- If no note exists, use the first non-empty row description as title.
- If title cannot be shortened safely, display the existing RZ heading only.
- If amounts are ambiguous, omit totals rather than showing misleading totals.

## Phase 2: Improve yearly pages for people

Keep RO chips on `/usneseni/YYYY/`, but add lightweight context.

Current:

```text
RO-7-2026 (2. 4.)
```

Target:

```text
RO-7-2026 (2. 4.)
14 změn: školy, dotace, ČOV, dary, místní části
```

Implementation:

- Add an optional short `plain_summary` for each RO.
- Generate it from top RZ titles/categories.
- Render as small secondary text if it fits the existing layout.
- If the chip layout becomes crowded, keep chips compact and show summary only on the `/rozpoctova-opatreni/` index.

Candidate category labels:

- školy
- doprava
- životní prostředí
- ČOV / voda
- dary a dotace
- místní části
- krizové řízení
- kultura a sport
- převody rezerv

These categories should be derived by keyword rules first, not by manual annotation.

## Phase 3: Add manual readability overrides

Introduce an optional tracked file for curated text, for example:

```text
resources/readability-overrides.json
```

Example:

```json
{
  "rz": {
    "69/2026/RM": {
      "plain_title": "Dotace pro ZŠ a MŠ Nasobůrky z OP JAK",
      "plain_reason": "Město přijalo účelovou dotaci od MŠMT a převádí ji škole."
    }
  },
  "ro": {
    "RO/7/2026": {
      "plain_summary": "Dotace pro školu, dopravní opatření, ČOV, dary a přesuny rezerv."
    }
  }
}
```

Rules:

- Overrides are optional.
- Overrides must never remove official parsed data.
- Overrides should be visibly marked in JSON as curated or manual.
- Export should still work without the file.
- Tests should cover deterministic output with and without overrides.

## Phase 4: UX refinements

RO detail page:

- Put the plain title and reason before accounting rows.
- Keep codes collapsed by default.
- Add section-level totals for `Příjmy`, `Výdaje`, and `Financování`.
- Add an anchor icon or stable self-link affordance for each RZ heading.
- Consider a small “Zobrazit účetní řádky” details wrapper when an RZ has many rows.

Resolution detail page:

- Split RO links into two clearly named groups:
  - `Odkazováno z rozpočtového opatření`
  - `Zmiňuje rozpočtové změny`
- For concrete RZ links, include the generated plain title if available:
  - `RZ 69/2026/RM: Dotace pro ZŠ a MŠ Nasobůrky`

RO index page:

- Show date, organ, number of RZs, and `plain_summary`.
- Group or filter by year if the list grows.

Search/year pages:

- Keep RM/ZM/RO navigation compact.
- Avoid mixing RO documents into “Všechna usnesení”; they are a related document type, not resolutions.

## Data and code changes

Likely implementation locations:

- `parse_rozpoctova_opatreni.py`
  - add deterministic RZ summary extraction after rows and notes are parsed,
  - normalize text used for resident-facing summaries.
- `crosslink_rozpoctova_opatreni.py`
  - pass summary metadata through linked output,
  - optionally add RZ titles to `budget_change_index.json`.
- `phase5_static_export.py`
  - render summaries in RO pages, resolution pages, RO index, and year pages.
- `tests/test_static_export_ro.py`
  - add summary rendering and fallback tests.

## Acceptance criteria

- A resident can understand the main purpose of each RZ without opening code details.
- RO pages still expose exact accounting rows, codes, anchors, and links.
- Generated summaries are deterministic and reproducible.
- Pages remain useful when no note exists.
- No manual override is required for the pipeline to run.
- Existing RO links from resolutions continue to work.
- `/usneseni/YYYY/` keeps compact RM/ZM/RO navigation.

## Suggested first implementation slice

Start with Phase 1 only:

1. Add a helper that groups rows by RZ and computes totals per section.
2. Add a helper that derives a plain title from note text or row descriptions.
3. Render title, note/reason, and totals at the top of each RZ article.
4. Keep all current rows and code details unchanged below.
5. Add tests for:
   - RZ with note and multiple rows,
   - RZ without note,
   - positive/negative movement,
   - no misleading total when data is incomplete.

This gives the biggest readability improvement without introducing editorial workflow or manual data maintenance.
