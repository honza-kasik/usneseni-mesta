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
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import html


BASE_URL = "https://litovle.cz"
SEARCH_URL = "/usneseni/"


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
        slug = slug_from_id(rid)
        year = rid.split("/")[-1]
        url = f"/usneseni/{year}/{slug}/"
        lines.append(f'<li><a href="{url}">{html.escape(rid)}</a></li>')

    lines.append("</ul>")
    return "\n".join(lines)


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
    output_root: Path
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
    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit("Input JSON does not exist.")

    args.output.mkdir(parents=True, exist_ok=True)

    data = json.loads(args.input.read_text(encoding="utf-8"))

    if not isinstance(data, list):
        raise SystemExit("Input JSON must be a list of resolutions.")

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
            args.output
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

    write_sitemap(sitemap_urls, args.output)

    print("PHASE 5 complete ✔")
    print(f"Resolutions: {len(data)}")
    print(f"Years: {len(by_year)}")
    print(f"Meetings: {len(by_meeting)}")


if __name__ == "__main__":
    main()
