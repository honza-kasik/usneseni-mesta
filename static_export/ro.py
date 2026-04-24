from __future__ import annotations

import html
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .format import budget_change_count_label, format_full_date
from .paths import ro_slug_from_id, ro_url, resolution_url, rz_anchor
from .ro_summary import (
    amount_class,
    clean_budget_row_description,
    render_budget_change_totals,
    summarize_budget_change,
)
from .usneseni import render_back_link


BUDGET_CHANGE_RE = re.compile(
    r"\b(?:RZ\s+)?(?P<id>\d{1,4}\s*/\s*\d{4}\s*/\s*(?:RM|ZM))\b",
    re.IGNORECASE,
)


def format_amount(row: Dict) -> str:
    return row.get("amount") or ""


def render_resolution_link_list(resolution_ids: List[str]) -> str:
    if not resolution_ids:
        return ""
    lines = ["<ul>"]
    for rid in sorted(set(resolution_ids)):
        lines.append(f'<li><a href="{resolution_url(rid)}">{html.escape(rid)}</a></li>')
    lines.append("</ul>")
    return "\n".join(lines)


def opatreni_organ_name(opatreni: Dict) -> str:
    organ = (opatreni.get("organ") or "").upper()
    if organ == "RM":
        return "Rada města Litovel"
    if organ == "ZM":
        return "Zastupitelstvo města Litovel"

    approved_by = opatreni.get("approved_by") or ""
    replacements = {
        "Radou města Litovel": "Rada města Litovel",
        "Zastupitelstvem města Litovel": "Zastupitelstvo města Litovel",
    }
    return replacements.get(approved_by, approved_by)


def note_budget_change_id(note: Dict) -> Optional[str]:
    title = note.get("title") or ""
    match = BUDGET_CHANGE_RE.search(title)
    if match:
        return normalize_budget_change_id(match.group("id"))
    return None


def normalize_budget_change_id(value: str) -> str:
    return re.sub(r"\s+", "", value.upper())


def note_map_by_budget_change(notes: List[Dict]) -> Dict[str, Dict]:
    mapped = {}
    for note in notes:
        budget_change_id = note_budget_change_id(note)
        if budget_change_id and note.get("text"):
            mapped[budget_change_id] = note
    return mapped


def code_labels_for_row(section_type: str, total: int) -> List[str]:
    labels_by_section = {
        "prijmy": {1: ["POL"], 2: ["POL", "ORG"], 5: ["POL", "UZ", "NÁSTROJ", "ORJ", "ORG"], 6: ["POL", "UZ", "PJ", "NÁSTROJ", "ORJ", "ORG"]},
        "vydaje": {
            2: ["ODPA", "POL"],
            3: ["ODPA", "POL", "ORG"],
            4: ["ODPA", "POL", "ORJ", "ORG"],
            5: ["ODPA", "POL", "UZ", "ORJ", "ORG"],
            6: ["ODPA", "POL", "UZ", "NÁSTROJ", "ORJ", "ORG"],
            7: ["ODPA", "POL", "UZ", "PJ", "NÁSTROJ", "ORJ", "ORG"],
        },
        "financovani": {1: ["POL"]},
    }
    labels = labels_by_section.get(section_type, {}).get(total)
    if labels:
        return labels
    return [f"Kód {index + 1}" for index in range(total)]


def render_code_details(row: Dict, section_type: str) -> str:
    codes = row.get("raw_codes") or []
    if not codes:
        return ""

    labels = code_labels_for_row(section_type, len(codes))
    summary = ", ".join(f"{labels[index]} {code}" for index, code in enumerate(codes))
    terms = [
        "<div>"
        f"<dt>{html.escape(labels[index])}</dt>"
        f"<dd>{html.escape(code)}</dd>"
        "</div>"
        for index, code in enumerate(codes)
    ]
    return (
        '<details class="usn-code-details">'
        f"<summary>Kódy: {html.escape(summary)}</summary>"
        "<dl>"
        + "".join(terms)
        + "</dl>"
        "</details>"
    )


def render_code_help() -> str:
    return """
<details class="usn-code-help">
<summary>Co znamenají kódy rozpočtové skladby</summary>
<dl>
<div><dt>ODPA</dt><dd>Odvětvové/paragrafové členění výdaje nebo příjmu.</dd></div>
<div><dt>POL</dt><dd>Rozpočtová položka, tedy ekonomický druh příjmu, výdaje nebo financování.</dd></div>
<div><dt>UZ</dt><dd>Účelový znak, typicky vazba na dotaci nebo účelové prostředky.</dd></div>
<div><dt>NÁSTROJ, ORJ, ORG</dt><dd>Doplňkové členění používané v účetním systému města.</dd></div>
</dl>
</details>
"""


def group_rows_by_budget_change(rows: List[Dict]) -> List[Tuple[str, List[Dict]]]:
    grouped = []
    index_by_id = {}
    for row in rows:
        budget_change_id = row.get("budget_change_id") or ""
        if budget_change_id not in index_by_id:
            index_by_id[budget_change_id] = len(grouped)
            grouped.append((budget_change_id, []))
        grouped[index_by_id[budget_change_id]][1].append(row)
    return grouped


def render_budget_change_article(
    budget_change_id: str,
    rows: List[Dict],
    note: Optional[Dict],
    anchor: str,
    section_type: str,
) -> str:
    """Render one RZ group with full explanatory note and underlying accounting rows."""
    article_attrs = f' id="{anchor}"' if anchor else ""
    row_label = "účetní řádek" if len(rows) == 1 else "účetní řádky"
    summary = summarize_budget_change(rows, note, budget_change_id)
    lines = [
        f'<article{article_attrs} class="usn-rz-group">',
        '<header class="usn-rz-group-head">',
        f'<h3><a href="#{html.escape(anchor)}">Rozpočtová změna {html.escape(budget_change_id)}</a></h3>' if anchor else f'<h3>Rozpočtová změna {html.escape(budget_change_id)}</h3>',
        f'<p class="usn-rz-count">{len(rows)} {row_label}</p>',
        "</header>",
    ]

    if summary["title"]:
        lines.append(f'<p class="usn-rz-title">{html.escape(str(summary["title"]))}</p>')
    if note:
        # For RO pages the note is the human-readable explanation, so render it whole.
        note_text = str(note.get("text") or "").strip()
        if note_text:
            lines += ['<aside class="usn-rz-note">', f'<p>{html.escape(note_text)}</p>', "</aside>"]

    totals_html = render_budget_change_totals(summary["totals"])
    if totals_html:
        lines.append(totals_html)

    lines.append('<div class="usn-rz-rows">')
    for row in rows:
        description = clean_budget_row_description(row.get("description") or "", budget_change_id)
        lines += [
            '<div class="usn-rz-row">',
            '<div class="usn-rz-row-main">',
            f'<strong class="usn-amount{amount_class(row)}">{html.escape(format_amount(row))}</strong>',
            f'<p>{html.escape(description)}</p>',
            "</div>",
            render_code_details(row, section_type),
            "</div>",
        ]
    lines += ["</div>", "</article>"]
    return "\n".join(lines)


def write_ro_page(opatreni: Dict, output_root: Path) -> str:
    oid = opatreni["id"]
    slug = ro_slug_from_id(oid)
    permalink = ro_url(oid)
    target_dir = output_root / "rozpoctova-opatreni" / slug
    target_dir.mkdir(parents=True, exist_ok=True)

    title = f"Rozpočtové opatření {oid}"
    organ_name = opatreni_organ_name(opatreni)
    approval_date = opatreni.get("approval_date") or ""
    approval_date_display = format_full_date(approval_date)
    budget_change_ids = opatreni.get("budget_change_ids") or []
    description = html.escape(f"{title}, {approval_date_display or approval_date}, {organ_name}")

    frontmatter = (
        "---\n"
        "layout: usneseni\n"
        f'title: "{title}"\n'
        f'description: "{description}"\n'
        f'cislo: "{oid}"\n'
        f'organ: "{organ_name}"\n'
        f'datum: "{approval_date}"\n'
        f"permalink: {permalink}\n"
        "---\n\n"
    )

    meeting = opatreni.get("meeting") or {}
    source_resolution_ids = [
        link.get("resolution_id")
        for link in opatreni.get("resolution_links") or []
        if link.get("relation") == "approves_opatreni" and link.get("resolution_id")
    ]
    mentioned_resolution_ids = [
        link.get("resolution_id")
        for link in opatreni.get("resolution_links") or []
        if link.get("relation") == "mentions_budget_change" and link.get("resolution_id")
    ]

    lines = [
        render_back_link(
            default_href="/rozpoctova-opatreni/",
            default_label="← Zpět na rozpočtová opatření",
            allowed_prefixes=("/usneseni", "/rozpoctova-opatreni"),
            wrapper_class="usn-back",
        ),
        f"<h1>{html.escape(title)}</h1>",
        f'<p class="usn-meta">{html.escape(approval_date_display or approval_date)} • {html.escape(organ_name)}</p>',
        '<dl class="usn-summary-list">',
        f"<div><dt>Orgán</dt><dd>{html.escape(organ_name)}</dd></div>",
        f"<div><dt>Datum schválení</dt><dd>{html.escape(approval_date_display or approval_date)}</dd></div>",
        f"<div><dt>Rozpočtové změny</dt><dd>{html.escape(budget_change_count_label(len(budget_change_ids)))}</dd></div>",
        "</dl>",
    ]

    if meeting:
        meeting_text = (
            f'{meeting.get("number", "")}. {meeting.get("type", "")}, '
            f'{format_full_date(meeting.get("date", "")) or meeting.get("date", "")}'
        ).strip(" ,")
        if meeting_text:
            lines.append(f'<p class="usn-meta-detail">Schváleno: {html.escape(meeting_text)}</p>')

    if source_resolution_ids:
        lines.append("<h2>Schvalující usnesení</h2>")
        lines.append(render_resolution_link_list(source_resolution_ids))

    lines.append(render_code_help())

    anchored_rz = set()
    rendered_notes = set()
    notes_by_rz = note_map_by_budget_change(opatreni.get("notes") or [])
    section_titles = {"prijmy": "Příjmy", "vydaje": "Výdaje", "financovani": "Financování"}

    for section in opatreni.get("sections") or []:
        rows = section.get("rows") or []
        if not rows:
            continue

        section_type = section.get("type") or ""
        title = section_titles.get(section_type, section.get("label") or section_type)
        grouped_rows = group_rows_by_budget_change(rows)
        lines += [
            f'<section class="usn-ro-section usn-ro-section-{html.escape(section_type)}">',
            f"<h2>{html.escape(title)}</h2>",
            '<div class="usn-rz-list">',
        ]

        for budget_change_id, budget_rows in grouped_rows:
            group_anchor = ""
            if budget_change_id and budget_change_id not in anchored_rz:
                group_anchor = rz_anchor(budget_change_id)
                anchored_rz.add(budget_change_id)

            budget_rows = [{**row, "section_type": section_type} for row in budget_rows]
            note = notes_by_rz.get(budget_change_id)
            article_note = None
            if note and budget_change_id not in rendered_notes:
                rendered_notes.add(budget_change_id)
                article_note = note

            lines.append(render_budget_change_article(budget_change_id, budget_rows, article_note, group_anchor, section_type))

        lines += ["</div>", "</section>"]

    notes = opatreni.get("notes") or []
    remaining_notes = [note for note in notes if note_budget_change_id(note) not in rendered_notes]
    if remaining_notes:
        lines.append("<h2>Další poznámky</h2>")
        for note in remaining_notes:
            if note.get("title"):
                lines.append(f"<h3>{html.escape(note['title'])}</h3>")
            if note.get("text"):
                lines.append(f"<p>{html.escape(note['text'])}</p>")

    if mentioned_resolution_ids:
        lines.append("<h2>Usnesení odkazující na RZ</h2>")
        lines.append(render_resolution_link_list(mentioned_resolution_ids))

    (target_dir / "index.html").write_text(frontmatter + "\n".join(lines), encoding="utf-8")
    return permalink


def write_ro_index(opatreni_list: List[Dict], output_root: Path) -> str:
    target_dir = output_root / "rozpoctova-opatreni"
    target_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        "---",
        "layout: usneseni_year",
        "title: Rozpočtová opatření",
        "permalink: /rozpoctova-opatreni/",
        "---",
        "",
        "<h1>Rozpočtová opatření</h1>",
        '<ul class="usn-results">',
    ]

    for opatreni in sorted(opatreni_list, key=lambda item: (item.get("year", 0), item.get("number", 0)), reverse=True):
        oid = opatreni["id"]
        lines.append(
            '<li class="usn-result">'
            f'<a href="{ro_url(oid)}" class="usn-card">'
            '<div class="usn-head">'
            f'<strong>{html.escape(oid)}</strong>'
            f'<span class="usn-date">{html.escape(opatreni.get("approval_date") or "")}</span>'
            '</div>'
            f'<div class="usn-summary">{html.escape(opatreni.get("approved_by") or "")}</div>'
            f'<div class="usn-snippet">{len(opatreni.get("budget_change_ids") or [])} rozpočtových změn</div>'
            '</a>'
            '</li>'
        )

    lines.append("</ul>")
    (target_dir / "index.html").write_text("\n".join(lines), encoding="utf-8")
    return "/rozpoctova-opatreni/"


def load_opatreni_dir(input_json: Path, explicit_dir: Optional[Path]) -> List[Dict]:
    opatreni_dir = explicit_dir
    if opatreni_dir is None:
        candidate = input_json.parent / "rozpoctova-opatreni"
        if candidate.exists():
            opatreni_dir = candidate

    if opatreni_dir is None or not opatreni_dir.exists():
        return []

    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(opatreni_dir.glob("*.json"))]


def group_opatreni_by_content_year(opatreni_list: List[Dict]) -> Dict[str, List[Dict]]:
    grouped: Dict[str, List[Dict]] = defaultdict(list)
    for opatreni in opatreni_list:
        year = opatreni.get("year")
        if year is not None:
            grouped[str(year)].append(opatreni)
    return grouped
