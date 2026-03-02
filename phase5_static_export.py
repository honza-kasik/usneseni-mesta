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
from typing import Dict, List, Tuple
import html


BASE_URL = "https://litovle.cz"


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


def render_resolution_content(resolution: Dict) -> str:
    """
    Render the main body of a resolution as HTML.

    Does not include layout wrapper or metadata.
    Only renders:
        - subject
        - items
        - tail
    """
    parts: List[str] = []

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

    frontmatter = (
        "---\n"
        "layout: usneseni\n"
        f"title: \"Usnesení {rid}\"\n"
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
    output_root: Path
) -> None:
    """
    Generate yearly index page listing all resolutions of given year.
    """
    target_dir = output_root / "usneseni" / year
    target_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        "---",
        "layout: usneseni_year",
        f"title: Usnesení {year}",
        f"permalink: /usneseni/{year}/",
        "---",
        "",
        f"<h1>Usnesení {year}</h1>",
        "",
        "<ul>"
    ]

    for rid, permalink in sorted(entries):
        lines.append(f'<li><a href="{permalink}">{html.escape(rid)}</a></li>')

    lines.append("</ul>")

    (target_dir / "index.html").write_text(
        "\n".join(lines),
        encoding="utf-8"
    )


def write_sitemap(urls: List[str], output_root: Path) -> None:
    """
    Generate sitemap.xml including all resolution and yearly URLs.
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
        5. Generate sitemap
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
    # Generate pages
    # --------------------------------------------------

    by_year: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    sitemap_urls: List[str] = []

    for resolution in data:
        if not all(k in resolution for k in ("id", "datum", "organ")):
            continue

        year, rid, permalink = write_resolution(
            resolution,
            args.output,
            refs_out_map,
            refs_in_map
        )

        by_year[year].append((rid, permalink))
        sitemap_urls.append(permalink)

    # --------------------------------------------------
    # Generate yearly indexes
    # --------------------------------------------------

    for year, entries in by_year.items():
        write_year_index(year, entries, args.output)
        sitemap_urls.append(f"/usneseni/{year}/")

    # --------------------------------------------------
    # Generate sitemap
    # --------------------------------------------------

    write_sitemap(sitemap_urls, args.output)

    print("PHASE 5 complete ✔")
    print(f"Resolutions: {len(data)}")
    print(f"Years: {len(by_year)}")


if __name__ == "__main__":
    main()
