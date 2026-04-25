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
    description_title_candidate,
    format_amount_value,
    is_expense_funded_from_financing_totals,
    is_expense_transfer_totals,
    is_generic_budget_title,
    positive_expense_title,
    section_total_values,
    summarize_budget_change,
    summarize_affected_places,
    budget_change_titles_from_opatreni,
    summarize_opatreni_plain,
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


def section_label(section_type: str) -> str:
    return {
        "prijmy": "Příjmy",
        "vydaje": "Výdaje",
        "financovani": "Financování",
    }.get(section_type, section_type)


def meeting_chip_text(meeting: Dict) -> str:
    number = meeting.get("number")
    meeting_type = (meeting.get("type") or "").strip().lower()
    if not number:
        return ""
    if "schůz" in meeting_type or "schůzi" in meeting_type:
        return f"{number}. schůze"
    if "zased" in meeting_type:
        return f"{number}. zasedání"
    return f"{number}. {meeting_type}".strip()


def transfer_target_phrase(rows: List[Dict], budget_change_id: str) -> str:
    return transfer_row_phrase(rows, budget_change_id, positive=True)


def transfer_source_phrase(rows: List[Dict], budget_change_id: str) -> str:
    return transfer_row_candidate(rows, budget_change_id, positive=False)


def transfer_row_phrase(rows: List[Dict], budget_change_id: str, positive: bool) -> str:
    target = transfer_row_candidate(rows, budget_change_id, positive)
    if not target:
        return ""

    lowered = target.lower()
    if re.match(r"^(dar|dotace)\b", lowered):
        return target
    if " - " in target:
        head, tail = target.split(" - ", 1)
        if head and tail:
            return f"{tail.strip()} pro {head.strip()}"
    return target


def transfer_row_candidate(rows: List[Dict], budget_change_id: str, positive: bool) -> str:
    for row in rows:
        amount_value = row.get("amount_value")
        if not isinstance(amount_value, (int, float)):
            continue
        if positive and float(amount_value) <= 0:
            continue
        if not positive and float(amount_value) >= 0:
            continue
        description = clean_budget_row_description(row.get("description") or "", budget_change_id)
        candidate = description_title_candidate(description).strip(" .")
        if candidate and not is_generic_budget_title(candidate):
            return candidate
    return ""


def has_same_transfer_labels(rows: List[Dict], budget_change_id: str) -> bool:
    sources = {
        clean_budget_row_description(row.get("description") or "", budget_change_id)
        for row in rows
        if isinstance(row.get("amount_value"), (int, float))
        and float(row.get("amount_value")) < 0
    }
    targets = {
        clean_budget_row_description(row.get("description") or "", budget_change_id)
        for row in rows
        if isinstance(row.get("amount_value"), (int, float))
        and float(row.get("amount_value")) > 0
    }
    sources = {
        description_title_candidate(value).strip(" .").casefold()
        for value in sources
        if description_title_candidate(value).strip(" .")
        and not is_generic_budget_title(description_title_candidate(value).strip(" ."))
    }
    targets = {
        description_title_candidate(value).strip(" .").casefold()
        for value in targets
        if description_title_candidate(value).strip(" .")
        and not is_generic_budget_title(description_title_candidate(value).strip(" ."))
    }
    return bool(sources & targets)


def grouped_budget_changes_from_opatreni(opatreni: Dict) -> List[Tuple[str, List[Dict]]]:
    grouped: List[Tuple[str, List[Dict]]] = []
    index_by_id: Dict[str, int] = {}
    for section in opatreni.get("sections") or []:
        section_type = section.get("type") or ""
        for row in section.get("rows") or []:
            budget_change_id = row.get("budget_change_id") or ""
            if budget_change_id not in index_by_id:
                index_by_id[budget_change_id] = len(grouped)
                grouped.append((budget_change_id, []))
            grouped[index_by_id[budget_change_id]][1].append({**row, "section_type": section_type})
    return grouped


def render_budget_change_article(
    budget_change_id: str,
    rows: List[Dict],
    note: Optional[Dict],
    anchor: str,
) -> str:
    """Render one merged RZ card with human explanation first and accounting rows below."""
    article_attrs = f' id="{anchor}"' if anchor else ""
    row_label = "účetní řádek" if len(rows) == 1 else "účetní řádky"
    summary = summarize_budget_change(rows, note, budget_change_id)
    title = str(summary["title"] or "")
    lines = [
        f'<article{article_attrs} class="usn-rz-group">',
        '<header class="usn-rz-group-head">',
        f'<h3><a href="#{html.escape(anchor)}">Rozpočtová změna {html.escape(budget_change_id)}</a></h3>' if anchor else f'<h3>Rozpočtová změna {html.escape(budget_change_id)}</h3>',
        f'<p class="usn-rz-count">{len(rows)} {row_label}</p>',
        "</header>",
    ]

    if title:
        lines.append(f'<p class="usn-rz-title">{html.escape(title)}</p>')
    if note:
        # For RO pages the note is the human-readable explanation, so render it whole.
        note_text = str(note.get("text") or "").strip()
        if note_text:
            lines += ['<aside class="usn-rz-note">', f'<p>{html.escape(note_text)}</p>', "</aside>"]

    explanation_html = render_budget_change_explanation(summary["totals"], rows, budget_change_id)
    if explanation_html:
        lines.append(explanation_html)

    lines += [
        '<details class="usn-rz-details">',
        f"<summary>Účetní řádky a kódy ({len(rows)})</summary>",
        '<div class="usn-rz-rows">',
    ]
    for row in rows:
        description = clean_budget_row_description(row.get("description") or "", budget_change_id)
        row_section_type = row.get("section_type") or ""
        row_section_label = section_label(str(row_section_type)) if row_section_type else ""
        lines += [
            '<div class="usn-rz-row">',
            '<div class="usn-rz-row-main">',
            f'<strong class="usn-amount{amount_class(row)}">{html.escape(format_amount(row))}</strong>',
            '<div class="usn-rz-row-copy">',
            f'<p>{html.escape(description)}</p>',
            f'<p class="usn-rz-row-section">{html.escape(row_section_label)}</p>' if row_section_label else "",
            "</div>",
            "</div>",
            render_code_details(row, str(row_section_type)),
            "</div>",
        ]
    lines += ["</div>", "</details>", "</article>"]
    return "\n".join(lines)


def render_budget_change_explanation(
    totals: Dict[str, Dict[str, float]],
    rows: List[Dict],
    budget_change_id: str,
) -> str:
    """Return a short resident-facing helper sentence for common accounting patterns.

    The RO page already shows the official note as the primary explanation. This
    helper is intentionally secondary and only appears when the raw accounting
    rows would otherwise be hard to interpret:

    - income mirrored by expense: accepted money is immediately assigned to spending
    - income mirrored by financing: accepted money affects account balances, not expenses
    - expense funded from financing: money from city account balances is newly used for an expense
    - expense transfer: money moves between two expense lines
    - same-label expense transfer: accounting reclassification without changing total spending

    When the pattern is already obvious from the official note and rows, the
    function returns an empty string to avoid adding another competing summary.
    """
    values = section_total_values(totals)
    prijmy_positive = values["prijmy_positive"]
    prijmy_negative = values["prijmy_negative"]
    vydaje_positive = values["vydaje_positive"]
    vydaje_negative = values["vydaje_negative"]
    financovani_positive = values["financovani_positive"]
    financovani_negative = values["financovani_negative"]

    if (
        prijmy_positive >= 0.005
        and vydaje_positive >= 0.005
        and abs(prijmy_positive - vydaje_positive) < 0.005
        and prijmy_negative < 0.005
        and vydaje_negative < 0.005
        and financovani_positive < 0.005
        and financovani_negative < 0.005
    ):
        amount = html.escape(format_amount_value(prijmy_positive).lstrip("+"))
        return (
            '<p class="usn-rz-explanation">'
            f'Rozpočtově: město přijalo {amount} a stejnou částku zařadilo do výdajů.'
            "</p>"
        )

    if (
        prijmy_positive >= 0.005
        and prijmy_negative < 0.005
        and vydaje_positive < 0.005
        and vydaje_negative < 0.005
        and financovani_positive < 0.005
        and financovani_negative < 0.005
    ):
        return ""

    if (
        prijmy_positive >= 0.005
        and financovani_negative >= 0.005
        and abs(prijmy_positive - financovani_negative) < 0.005
        and prijmy_negative < 0.005
        and vydaje_positive < 0.005
        and vydaje_negative < 0.005
        and financovani_positive < 0.005
    ):
        amount = html.escape(format_amount_value(prijmy_positive).lstrip("+"))
        return (
            '<p class="usn-rz-explanation">'
            f'Rozpočtově: město přijalo {amount}. Tato změna nezvyšuje výdaje; promítá se do peněz na účtech města.'
            "</p>"
        )

    if is_expense_funded_from_financing_totals(totals):
        amount = html.escape(format_amount_value(vydaje_positive).lstrip("+"))
        target = positive_expense_title(rows, budget_change_id)
        target_html = f" Účel: {html.escape(target)}." if target else ""
        return (
            '<p class="usn-rz-explanation">'
            f'Rozpočtově: do výdajů se zapojuje {amount} z peněz na účtech města.{target_html}'
            "</p>"
        )

    if is_expense_transfer_totals(totals):
        amount = html.escape(format_amount_value(vydaje_positive).lstrip("+"))
        if has_same_transfer_labels(rows, budget_change_id):
            return (
                '<p class="usn-rz-explanation">'
                f'Rozpočtově: mění se rozpočtové zařazení výdajů v celkové výši {amount}. Celková výše výdajů se nemění.'
                "</p>"
            )
        target = transfer_target_phrase(rows, budget_change_id)
        if target:
            source = transfer_source_phrase(rows, budget_change_id)
            sentence_end = "" if target.endswith((".", "!", "?")) else "."
            source_html = f" z položky {html.escape(source)}" if source else ""
            return (
                f'<p class="usn-rz-explanation">Rozpočtově: přesun {amount}{source_html} na {html.escape(target)}{sentence_end}</p>'
            )
        return f'<p class="usn-rz-explanation">Rozpočtově: přesun {amount} na jiný účel.</p>'

    return ""


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
        "rozpoctove_opatreni: true\n"
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

    meeting_text = meeting_chip_text(meeting) if meeting else ""

    lines = [
        render_back_link(
            default_href="/rozpoctova-opatreni/",
            default_label="← Zpět na rozpočtová opatření",
            allowed_prefixes=("/usneseni", "/rozpoctova-opatreni"),
            wrapper_class="usn-back",
        ),
        '<header class="usn-ro-hero">',
        '<p class="usn-ro-kicker">Rozpočet města</p>',
        f"<h1>{html.escape(oid)}</h1>",
        (
            f'<p class="usn-ro-lead">Obsahuje {html.escape(budget_change_count_label(len(budget_change_ids)))}. '
            f'Schváleno {html.escape(approval_date_display or approval_date)}.</p>'
        ),
        '<div class="usn-ro-facts">',
        f'<span>{html.escape(organ_name)}</span>',
        f'<span>{html.escape(budget_change_count_label(len(budget_change_ids)))}</span>',
        f'<span>{html.escape(meeting_text)}</span>' if meeting_text else "",
        "</div>",
        "</header>",
    ]

    if source_resolution_ids:
        lines.append("<h2>Schvalující usnesení</h2>")
        lines.append(render_resolution_link_list(source_resolution_ids))

    anchored_rz = set()
    rendered_notes = set()
    notes_by_rz = note_map_by_budget_change(opatreni.get("notes") or [])
    lines += ["<section class=\"usn-ro-section\">", "<h2>Rozpočtové změny</h2>", '<div class="usn-rz-list">']
    for budget_change_id, budget_rows in grouped_budget_changes_from_opatreni(opatreni):
        group_anchor = ""
        if budget_change_id and budget_change_id not in anchored_rz:
            group_anchor = rz_anchor(budget_change_id)
            anchored_rz.add(budget_change_id)

        note = notes_by_rz.get(budget_change_id)
        article_note = None
        if note and budget_change_id not in rendered_notes:
            rendered_notes.add(budget_change_id)
            article_note = note

        lines.append(render_budget_change_article(budget_change_id, budget_rows, article_note, group_anchor))
    lines += ["</div>", "</section>"]

    lines.append(render_code_help())

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
        plain_summary = summarize_opatreni_plain(opatreni)
        affected_places = summarize_affected_places(opatreni)
        title_candidates = budget_change_titles_from_opatreni(opatreni)
        snippet = plain_summary or ", ".join(title_candidates[:2])
        affected_html = f'<div class="usn-summary">Týká se: {html.escape(affected_places)}</div>' if affected_places else ""
        lines.append(
            '<li class="usn-result">'
            f'<a href="{ro_url(oid)}" class="usn-card">'
            '<div class="usn-head">'
            f'<strong>{html.escape(oid)}</strong>'
            f'<span class="usn-date">{html.escape(opatreni.get("approval_date") or "")}</span>'
            '</div>'
            f'<div class="usn-summary">{html.escape(opatreni.get("approved_by") or "")}</div>'
            f'<div class="usn-snippet">{html.escape(snippet or f"{len(opatreni.get("budget_change_ids") or [])} rozpočtových změn")}</div>'
            f"{affected_html}"
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
