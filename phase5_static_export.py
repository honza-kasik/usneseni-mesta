#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
phase5_static_export
====================

Statický export usnesení do struktury vhodné pro Jekyll.

Tento modul:
    - generuje jednotlivé stránky usnesení
    - generuje roční indexy
    - generuje sitemap.xml
    - vytváří obousměrné referenční vazby (out + in)
    - generuje indexy jednotlivých schůzí
    - pokud jsou k dispozici propojená rozpočtová opatření, generuje i jejich stránky

Negeneruje:
    - hlavní stránku /usneseni/ (ta existuje ručně)

Očekávaný vstup:
    JSON soubor obsahující seznam usnesení (výstup phase3)

Každé usnesení musí obsahovat minimálně:
    id, datum, organ

Použití:
    python phase5_static_export.py \
        -i phase3/usneseni.json \
        -o ../litovle.cz/

    python phase5_static_export.py \
        -i work/rozpoctova-opatreni-linked/usneseni.json \
        --opatreni work/rozpoctova-opatreni-linked/rozpoctova-opatreni \
        -o ../litovle.cz/

Architektura:
    phase1 → extrakce PDF
    phase2 → strukturální analýza
    phase3 → reference resolving
    phase4 → fulltext index
    phase5 → statický export (tento modul)
"""

from __future__ import annotations

import json
import argparse
import re
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import html


BASE_URL = "https://litovle.cz"
SEARCH_URL = "/usneseni/"
BUDGET_CHANGE_RE = re.compile(
    r"\b(?:RZ\s+)?(?P<id>\d{1,4}\s*/\s*\d{4}\s*/\s*(?:RM|ZM))\b",
    re.IGNORECASE,
)


# ============================================================
# UTILITIES
# ============================================================

def slug_from_id(resolution_id: str) -> str:
    """
    Convert resolution ID to URL-safe slug.

    Example:
        "RM/1/1/2022" → "RM-1-1-2022"
    """
    return resolution_id.replace("/", "-")


def ro_slug_from_id(opatreni_id: str) -> str:
    """
    Convert RO ID to URL-safe slug.

    Example:
        "RO/6/2026" -> "RO-6-2026"
    """
    return opatreni_id.replace("/", "-")


def ro_url(opatreni_id: str) -> str:
    return f"/rozpoctova-opatreni/{ro_slug_from_id(opatreni_id)}/"


def rz_anchor(budget_change_id: str) -> str:
    return "rz-" + budget_change_id.replace("/", "-").lower()


def resolution_url(resolution_id: str) -> str:
    slug = slug_from_id(resolution_id)
    year = resolution_id.split("/")[-1]
    return f"/usneseni/{year}/{slug}/"


def meeting_from_id(rid: str) -> Tuple[str, str, str]:
    """
    Extract (organ, meeting_number, year) from resolution ID.

    Example:
        "RM/1997/66/2026" → ("RM", "66", "2026")
    """
    org, _, meeting, year = rid.split("/")
    return org, meeting, year


def format_date(d: str) -> str:
    """
    Convert ISO date (YYYY-MM-DD) to Czech short format (D. M.)
    """
    try:
        return datetime.fromisoformat(d).strftime("%-d. %-m.")
    except Exception:
        return d or ""


def format_full_date(d: str) -> str:
    """
    Convert ISO date (YYYY-MM-DD) to Czech display format (D. M. YYYY).
    """
    try:
        return datetime.fromisoformat(d).strftime("%-d. %-m. %Y")
    except Exception:
        return d or ""


def budget_change_count_label(count: int) -> str:
    if count == 1:
        return "1 rozpočtová změna"
    if 2 <= count <= 4:
        return f"{count} rozpočtové změny"
    return f"{count} rozpočtových změn"


# ============================================================
# NAVIGATION
# ============================================================

def render_back_link() -> str:
    """
    Render a navigation link back to the search page.

    Uses referrer/history for UX, but keeps a static fallback
    for SEO and no-JS environments.
    """
    return """
<p>
  <a href="/usneseni/" id="back-link">← Zpět na vyhledávání</a>
</p>

<script>
(function() {
  const a = document.getElementById("back-link");
  if (!a) return;

  const back = new URLSearchParams(location.search).get("back");
  try {
    const url = new URL(back, location.origin);
    if (
      url.origin === location.origin &&
      (url.pathname === "/usneseni" || url.pathname.startsWith("/usneseni/"))
    ) {
      a.href = url.pathname + url.search;
    }
  } catch (e) {
    // ignoruj rozbité hodnoty
  }
})();
</script>
"""


def render_meeting_link(resolution: Dict) -> str:
    """
    Render link to all resolutions from the same meeting.
    """
    rid = resolution["id"]
    org, meeting, year = meeting_from_id(rid)
    url = f"/usneseni/{year}/{org}-{meeting}/"

    return f'''
<p>
  <a href="{url}">
    → Všechna usnesení z této schůze
  </a>
</p>
'''


# ============================================================
# CONTENT
# ============================================================

def render_resolution_content(resolution: Dict) -> str:
    """
    Render the main body of a resolution as HTML.

    Does not include layout wrapper or metadata.
    Only renders:
        - back-to-search link
        - meeting link
        - subject
        - items
        - tail
    """
    parts: List[str] = [
        render_back_link(),
        render_meeting_link(resolution),
    ]

    actions = resolution.get("actions", [])
    subject = resolution.get("subject")
    items = resolution.get("items", [])

    # --------------------------------------------------
    # Typ A: jedna globální akce + předmět
    # --------------------------------------------------
    if subject and len(actions) == 1 and not items:
        action = html.escape(actions[0])
        subject = html.escape(subject)
        parts.append(f"<p>{action} {subject}</p>")
        return "\n".join(parts)

    # --------------------------------------------------
    # Ostatní případy
    # --------------------------------------------------

    if subject:
        parts.append(f"<p>{html.escape(subject)}</p>")

    for item in items:
        label = html.escape(item.get("label", ""))
        text = html.escape(item.get("text", ""))
        parts.append(f"<p><strong>{label})</strong> {text}</p>")

    if resolution.get("tail"):
        parts.append(f"<p>{html.escape(resolution['tail'])}</p>")

    return "\n".join(parts)


def render_references_section(title: str, ids: List[str]) -> str:
    """
    Render reference section.

    Parameters
    ----------
    title : str
        Section heading.
    ids : list[str]
        List of referenced resolution IDs.

    Returns
    -------
    str
        HTML fragment or empty string.
    """
    if not ids:
        return ""

    lines = [f"<h2>{title}</h2>", "<ul>"]

    for rid in sorted(set(ids)):
        url = resolution_url(rid)
        lines.append(f'<li><a href="{url}">{html.escape(rid)}</a></li>')

    lines.append("</ul>")
    return "\n".join(lines)


def render_budget_links_section(resolution: Dict) -> str:
    """
    Render links between a resolution and parsed budget changes/opatreni.

    The section is shown only when the input data has been enriched by
    crosslink_rozpoctova_opatreni.py.
    """
    approved = resolution.get("budget_opatreni_approved") or []
    budget_links = resolution.get("budget_change_links") or []

    if not approved and not budget_links:
        return ""

    lines = ['<section class="usn-budget-links">', "<h2>Rozpočtová opatření</h2>"]

    seen_approved = set()
    approved_lines = []
    for link in approved:
        opatreni_id = link.get("opatreni_id")
        if not opatreni_id or opatreni_id in seen_approved:
            continue
        seen_approved.add(opatreni_id)
        url = ro_url(opatreni_id)
        approved_lines.append(
            f'<li>Odkazováno z rozpočtového opatření <a href="{url}">{html.escape(opatreni_id)}</a></li>'
        )

    seen_budget_changes = set()
    budget_change_lines = []
    for link in sorted(budget_links, key=lambda item: budget_change_sort_key(item.get("budget_change_id", ""))):
        budget_change_id = link.get("budget_change_id")
        opatreni_id = link.get("opatreni_id")
        if not budget_change_id or not opatreni_id:
            continue

        key = (budget_change_id, opatreni_id)
        if key in seen_budget_changes:
            continue
        seen_budget_changes.add(key)

        url = ro_url(opatreni_id) + "#" + rz_anchor(budget_change_id)
        budget_change_lines.append(
            "<li>"
            f'<a href="{url}">Rozpočtová změna {html.escape(budget_change_id)}</a> '
            f"v {html.escape(opatreni_id)}"
            "</li>"
        )

    if approved_lines:
        lines.append("<ul>")
        lines.extend(approved_lines)
        lines.append("</ul>")

    if budget_change_lines:
        lines.append(
            f'<details class="usn-budget-change-list" open>'
            f'<summary>{budget_change_count_label(len(budget_change_lines))}</summary>'
            "<ul>"
        )
        lines.extend(budget_change_lines)
        lines.append("</ul></details>")

    lines.append("</section>")
    return "\n".join(lines)


def budget_change_sort_key(value: str):
    match = re.match(r"^(\d+)/(\d{4})/(RM|ZM)$", value)
    if not match:
        return (9999, value)
    number, year, organ = match.groups()
    return (int(year), organ, int(number))


# ============================================================
# PAGE GENERATION
# ============================================================

def write_resolution(
    resolution: Dict,
    output_root: Path,
    refs_out_map: Dict[str, List[str]],
    refs_in_map: Dict[str, List[str]]
) -> Tuple[str, str, str]:
    """
    Generate single resolution page.

    Returns
    -------
    (year, resolution_id, permalink)
    """
    rid = resolution["id"]
    slug = slug_from_id(rid)
    year = resolution["datum"][:4]

    target_dir = output_root / "usneseni" / year / slug
    target_dir.mkdir(parents=True, exist_ok=True)

    permalink = f"/usneseni/{year}/{slug}/"

    subject = resolution.get("subject")

    if subject:
        raw_desc = f"{resolution.get('organ','')}, {resolution.get('datum','')}: {subject}"
    else:
        raw_desc = f"{resolution.get('organ','')}, {resolution.get('datum','')}, usnesení {rid}"

    # zkrácení na cca 160 znaků
    description = raw_desc[:157] + "…" if len(raw_desc) > 160 else raw_desc
    description = html.escape(description)

    frontmatter = (
        "---\n"
        "layout: usneseni\n"
        f"title: \"Usnesení {rid}\"\n"
        f"description: \"{description}\"\n"
        f"cislo: \"{rid}\"\n"
        f"organ: \"{resolution.get('organ','')}\"\n"
        f"datum: \"{resolution.get('datum','')}\"\n"
        f"permalink: {permalink}\n"
        "---\n\n"
    )

    content = render_resolution_content(resolution)

    # References OUT
    budget_links_section = render_budget_links_section(resolution)
    if budget_links_section:
        content += "\n" + budget_links_section

    # References OUT
    content += render_references_section(
        "Odkazuje na",
        refs_out_map.get(rid, [])
    )

    # References IN
    content += render_references_section(
        "Je odkazováno z",
        refs_in_map.get(rid, [])
    )

    (target_dir / "index.html").write_text(
        frontmatter + content,
        encoding="utf-8"
    )

    return year, rid, permalink


def write_year_index(
    year: str,
    entries: List[Tuple[str, str]],
    meetings: List[Tuple[str, str, str]],
    output_root: Path,
    opatreni_entries: Optional[List[Dict]] = None,
) -> None:
    """
    Generate yearly index page listing all resolutions of given year,
    including structured list of meetings with dates.
    """

    target_dir = output_root / "usneseni" / year
    target_dir.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------
    # Split meetings by organ
    # --------------------------------------------------

    rm = []
    zm = []

    for slug, url, date in meetings:
        if slug.startswith("RM-"):
            rm.append((slug, url, date))
        elif slug.startswith("ZM-"):
            zm.append((slug, url, date))

    def sort_meetings(items):
        return sorted(items, key=lambda x: int(x[0].split("-")[1]))

    # --------------------------------------------------
    # Render
    # --------------------------------------------------

    lines = [
        "---",
        "layout: usneseni_year",
        f"title: Usnesení {year}",
        f"permalink: /usneseni/{year}/",
        "---",
        "",
        f"<h1>Usnesení {year}</h1>",
    ]

    # --------------------------------------------------
    # Meetings section
    # --------------------------------------------------

    if meetings:
        lines += [
            "",
            "<h2>Schůze</h2>",
        ]

        if rm:
            lines += [
                "<h3>Rada města</h3>",
                '<div class="usn-meetings">'
            ]
            for slug, url, date in sort_meetings(rm):
                lines.append(
                    f'<a href="{url}">{slug} <span class="usn-date">({format_date(date)})</span></a>'
                )
            lines.append("</div>")

        if zm:
            lines += [
                "<h3>Zastupitelstvo</h3>",
                '<div class="usn-meetings">'
            ]
            for slug, url, date in sort_meetings(zm):
                lines.append(
                    f'<a href="{url}">{slug} <span class="usn-date">({format_date(date)})</span></a>'
                )
            lines.append("</div>")

    # --------------------------------------------------
    # Budget measures section
    # --------------------------------------------------

    if opatreni_entries:
        lines += [
            "",
            "<h2>Rozpočtová opatření</h2>",
            '<div class="usn-meetings">',
        ]

        for opatreni in sorted(
            opatreni_entries,
            key=lambda item: (
                item.get("approval_date") or "",
                item.get("year", 0),
                item.get("number", 0),
            ),
            reverse=True,
        ):
            oid = opatreni["id"]
            approval_date = opatreni.get("approval_date") or ""
            lines.append(
                f'<a href="{ro_url(oid)}">{html.escape(oid.replace("/", "-"))} '
                f'<span class="usn-date">({html.escape(format_date(approval_date))})</span></a>'
            )

        lines += [
            "</div>",
            '<p class="usn-more"><a href="/rozpoctova-opatreni/">Všechna rozpočtová opatření</a></p>',
        ]

    # --------------------------------------------------
    # Resolutions list
    # --------------------------------------------------

    MAX_ITEMS = 20
    recent = sorted(entries)[-MAX_ITEMS:]

    lines += [
        "",
        "<h2>Poslední usnesení</h2>",
        '<div class="usn-recent">'
    ]

    for rid, permalink in recent:
        lines.append(f'<a href="{permalink}">{html.escape(rid)}</a>')

    lines.append("</div>")

    lines += [
        "",
        "<h2>Všechna usnesení</h2>",
        f'<details class="usn-all">',
        f'<summary>Zobrazit všechna usnesení ({len(entries)})</summary>',
        "<ul>"
    ]

    for rid, permalink in sorted(entries):
        lines.append(f'<li><a href="{permalink}">{html.escape(rid)}</a></li>')

    lines += [
        "</ul>",
        "</details>"
    ]

    (target_dir / "index.html").write_text(
        "\n".join(lines),
        encoding="utf-8"
    )


def write_meeting_index(
    year: str,
    org: str,
    meeting: str,
    entries: List[Tuple[str, str, Optional[str], List[str]]],
    meta: Dict,
    output_root: Path
) -> None:
    """
    Generate index page for a single meeting using same HTML structure as search.
    """

    slug = f"{org}-{meeting}"
    target_dir = output_root / "usneseni" / year / slug
    target_dir.mkdir(parents=True, exist_ok=True)

    organ = meta.get("organ", "")
    datum = meta.get("datum", "")

    lines = [
        "---",
        "layout: usneseni_meeting",
        f"title: {organ} – schůze {meeting} ({year})",
        f"permalink: /usneseni/{year}/{slug}/",
        "---",
        "",
        f"<h1>{organ}: {meeting}. schůze</h1>",
        f'<p class="usn-meta">{datum} • {len(entries)} usnesení</p>',
        "",
        '<ul class="usn-results">'
    ]

    for rid, permalink, subject, actions in sorted(entries):
        summary = ", ".join(actions) if actions else ""
        snippet = (subject or "").strip()

        if len(snippet) > 180:
            snippet = snippet[:177] + "…"

        lines.append(f"""
<li class="usn-result">
  <a href="{permalink}" class="usn-card">
    <div class="usn-head">
      <strong>{html.escape(rid)}</strong>
      <span class="usn-date">{html.escape(datum)}</span>
    </div>

    {f'<div class="usn-summary">{html.escape(summary)}</div>' if summary else ''}
    {f'<div class="usn-snippet">{html.escape(snippet)}</div>' if snippet else ''}
  </a>
</li>
""")

    lines.append("</ul>")

    (target_dir / "index.html").write_text(
        "\n".join(lines),
        encoding="utf-8"
    )


def format_amount(row: Dict) -> str:
    return row.get("amount") or ""


def render_resolution_link_list(resolution_ids: List[str]) -> str:
    if not resolution_ids:
        return ""

    lines = ["<ul>"]
    for rid in sorted(set(resolution_ids)):
        lines.append(
            f'<li><a href="{resolution_url(rid)}">{html.escape(rid)}</a></li>'
        )
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


def amount_class(row: Dict) -> str:
    value = row.get("amount_value")
    if isinstance(value, (int, float)):
        if value < 0:
            return " usn-amount-negative"
        if value > 0:
            return " usn-amount-positive"
    return ""


def code_labels_for_row(section_type: str, total: int) -> List[str]:
    labels_by_section = {
        "prijmy": {
            1: ["POL"],
            2: ["POL", "ORG"],
            5: ["POL", "UZ", "NÁSTROJ", "ORJ", "ORG"],
            6: ["POL", "UZ", "PJ", "NÁSTROJ", "ORJ", "ORG"],
        },
        "vydaje": {
            2: ["ODPA", "POL"],
            3: ["ODPA", "POL", "ORG"],
            4: ["ODPA", "POL", "ORJ", "ORG"],
            5: ["ODPA", "POL", "UZ", "ORJ", "ORG"],
            6: ["ODPA", "POL", "UZ", "NÁSTROJ", "ORJ", "ORG"],
            7: ["ODPA", "POL", "UZ", "PJ", "NÁSTROJ", "ORJ", "ORG"],
        },
        "financovani": {
            1: ["POL"],
        },
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
    summary = ", ".join(
        f"{labels[index]} {code}"
        for index, code in enumerate(codes)
    )
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


def clean_budget_row_description(description: str, budget_change_id: str) -> str:
    if not description:
        return ""

    escaped_id = re.escape(budget_change_id).replace(r"\/", r"\s*/\s*")
    description = re.sub(
        r"\s*\(?\s*RZ\s+" + escaped_id + r"\s*\)?\s*$",
        "",
        description,
        flags=re.IGNORECASE,
    )
    return description.strip()


def render_budget_change_article(
    budget_change_id: str,
    rows: List[Dict],
    note: Optional[Dict],
    anchor: str,
    section_type: str,
) -> str:
    article_attrs = f' id="{anchor}"' if anchor else ""
    row_label = "účetní řádek" if len(rows) == 1 else "účetní řádky"
    lines = [
        f'<article{article_attrs} class="usn-rz-group">',
        '<header class="usn-rz-group-head">',
        f'<h3><a href="#{html.escape(anchor)}">Rozpočtová změna {html.escape(budget_change_id)}</a></h3>' if anchor else f'<h3>Rozpočtová změna {html.escape(budget_change_id)}</h3>',
        f'<p class="usn-rz-count">{len(rows)} {row_label}</p>',
        "</header>",
    ]

    if note:
        lines += [
            '<aside class="usn-rz-note">',
            f'<p>{html.escape(note.get("text") or "")}</p>',
            "</aside>",
        ]

    lines += [
        '<div class="usn-rz-rows">',
    ]

    for row in rows:
        description = clean_budget_row_description(
            row.get("description") or "",
            budget_change_id,
        )
        lines += [
            '<div class="usn-rz-row">',
            '<div class="usn-rz-row-main">',
            f'<strong class="usn-amount{amount_class(row)}">{html.escape(format_amount(row))}</strong>',
            f'<p>{html.escape(description)}</p>',
            "</div>",
            render_code_details(row, section_type),
            "</div>",
        ]

    lines.append("</div>")

    lines.append("</article>")
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
    description = html.escape(
        f"{title}, {approval_date_display or approval_date}, {organ_name}"
    )

    frontmatter = (
        "---\n"
        "layout: usneseni\n"
        f"title: \"{title}\"\n"
        f"description: \"{description}\"\n"
        f"cislo: \"{oid}\"\n"
        f"organ: \"{organ_name}\"\n"
        f"datum: \"{approval_date}\"\n"
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
        '<p class="usn-back"><a href="/rozpoctova-opatreni/">← Zpět na rozpočtová opatření</a></p>',
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
    section_titles = {
        "prijmy": "Příjmy",
        "vydaje": "Výdaje",
        "financovani": "Financování",
    }

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

            note = notes_by_rz.get(budget_change_id)
            article_note = None
            if note and budget_change_id not in rendered_notes:
                rendered_notes.add(budget_change_id)
                article_note = note

            lines.append(
                render_budget_change_article(
                    budget_change_id,
                    budget_rows,
                    article_note,
                    group_anchor,
                    section_type,
                )
            )

        lines += ["</div>", "</section>"]

    notes = opatreni.get("notes") or []
    remaining_notes = [
        note for note in notes
        if note_budget_change_id(note) not in rendered_notes
    ]
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

    (target_dir / "index.html").write_text(
        frontmatter + "\n".join(lines),
        encoding="utf-8",
    )

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

    (target_dir / "index.html").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    return "/rozpoctova-opatreni/"


def load_opatreni_dir(input_json: Path, explicit_dir: Optional[Path]) -> List[Dict]:
    opatreni_dir = explicit_dir
    if opatreni_dir is None:
        candidate = input_json.parent / "rozpoctova-opatreni"
        if candidate.exists():
            opatreni_dir = candidate

    if opatreni_dir is None or not opatreni_dir.exists():
        return []

    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(opatreni_dir.glob("*.json"))
    ]


def group_opatreni_by_approval_year(opatreni_list: List[Dict]) -> Dict[str, List[Dict]]:
    grouped: Dict[str, List[Dict]] = defaultdict(list)
    for opatreni in opatreni_list:
        approval_date = opatreni.get("approval_date") or ""
        if len(approval_date) >= 4:
            grouped[approval_date[:4]].append(opatreni)
    return grouped


def write_sitemap(urls: List[str], output_root: Path) -> None:
    """
    Generate sitemap.xml including all resolution and index URLs.
    """
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    ]

    for url in sorted(set(urls)):
        lines.append("  <url>")
        lines.append(f"    <loc>{BASE_URL}{url}</loc>")
        lines.append("  </url>")

    lines.append("</urlset>")

    (output_root / "sitemap.xml").write_text(
        "\n".join(lines),
        encoding="utf-8"
    )


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    """
    Entry point.

    Steps:
        1. Load resolution list
        2. Build reference graph
        3. Generate resolution pages
        4. Generate yearly indexes
        5. Generate meeting indexes
        6. Generate sitemap
    """

    parser = argparse.ArgumentParser(
        description="Phase 5 – static export of municipal resolutions"
    )
    parser.add_argument("-i", "--input", type=Path, required=True)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument(
        "--opatreni",
        type=Path,
        help="Adresář s propojenými JSON rozpočtových opatření; výchozí je sourozenec inputu rozpoctova-opatreni/",
    )
    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit("Input JSON does not exist.")

    args.output.mkdir(parents=True, exist_ok=True)

    data = json.loads(args.input.read_text(encoding="utf-8"))

    if not isinstance(data, list):
        raise SystemExit("Input JSON must be a list of resolutions.")

    opatreni_list = load_opatreni_dir(args.input, args.opatreni)

    # --------------------------------------------------
    # Build reference graph
    # --------------------------------------------------

    refs_out_map: Dict[str, List[str]] = defaultdict(list)
    refs_in_map: Dict[str, List[str]] = defaultdict(list)

    for resolution in data:
        source = resolution.get("id")
        for ref in resolution.get("references_out", []):
            target = ref.get("resolved")
            if not target:
                continue
            refs_out_map[source].append(target)
            refs_in_map[target].append(source)

    # --------------------------------------------------
    # Prepare containers
    # --------------------------------------------------

    by_year: Dict[str, List[Tuple[str, str]]] = defaultdict(list)

    by_meeting: Dict[
        str,
        List[Tuple[str, str, Optional[str], List[str]]]
    ] = defaultdict(list)

    by_meeting_meta: Dict[str, Dict] = {}

    meetings_by_year: Dict[str, List[Tuple[str, str, str]]] = defaultdict(list)

    sitemap_urls: List[str] = []

    opatreni_by_approval_year = group_opatreni_by_approval_year(opatreni_list)

    # --------------------------------------------------
    # Generate resolution pages + collect data
    # --------------------------------------------------

    for resolution in data:
        if not all(k in resolution for k in ("id", "datum", "organ")):
            continue

        year, rid, permalink = write_resolution(
            resolution,
            args.output,
            refs_out_map,
            refs_in_map
        )

        # ---------------------------
        # Year index
        # ---------------------------

        by_year[year].append((rid, permalink))
        sitemap_urls.append(permalink)

        # ---------------------------
        # Meeting index
        # ---------------------------

        org, meeting, year = meeting_from_id(rid)
        key = f"{year}/{org}-{meeting}"

        by_meeting[key].append((
            rid,
            permalink,
            resolution.get("subject"),
            resolution.get("actions", [])
        ))

        # metadata (uloží se jen jednou)
        if key not in by_meeting_meta:
            by_meeting_meta[key] = {
                "organ": resolution.get("organ"),
                "datum": resolution.get("datum"),
            }

        # ---------------------------
        # Meetings by year (with date)
        # ---------------------------

        meeting_slug = f"{org}-{meeting}"
        meeting_url = f"/usneseni/{year}/{meeting_slug}/"
        meeting_date = resolution.get("datum")

        if not any(slug == meeting_slug for slug, _, _ in meetings_by_year[year]):
            meetings_by_year[year].append(
                (meeting_slug, meeting_url, meeting_date)
            )

    # --------------------------------------------------
    # Generate yearly indexes
    # --------------------------------------------------

    for year, entries in by_year.items():
        write_year_index(
            year,
            entries,
            meetings_by_year.get(year, []),
            args.output,
            opatreni_by_approval_year.get(year, []),
        )
        sitemap_urls.append(f"/usneseni/{year}/")

    # --------------------------------------------------
    # Generate meeting indexes
    # --------------------------------------------------

    for key, entries in by_meeting.items():
        year, rest = key.split("/")
        org, meeting = rest.split("-")

        write_meeting_index(
            year,
            org,
            meeting,
            entries,
            by_meeting_meta[key],
            args.output
        )

        sitemap_urls.append(f"/usneseni/{year}/{org}-{meeting}/")

    # --------------------------------------------------
    # Generate sitemap
    # --------------------------------------------------

    if opatreni_list:
        sitemap_urls.append(write_ro_index(opatreni_list, args.output))
        for opatreni in opatreni_list:
            sitemap_urls.append(write_ro_page(opatreni, args.output))

    write_sitemap(sitemap_urls, args.output)

    print("PHASE 5 complete ✔")
    print(f"Resolutions: {len(data)}")
    print(f"Years: {len(by_year)}")
    print(f"Meetings: {len(by_meeting)}")
    if opatreni_list:
        print(f"Rozpočtová opatření: {len(opatreni_list)}")


if __name__ == "__main__":
    main()
