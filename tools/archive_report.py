#!/usr/bin/env python3
"""Generate quality reports for Litovel archive ingestion."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections import defaultdict
from pathlib import Path

try:
    from archive_zm_common import read_json, write_json
except ImportError:
    from tools.archive_zm_common import read_json, write_json


def counter(values) -> dict:
    return dict(sorted(Counter(value if value is not None else "unknown" for value in values).items()))


def duplicate_groups(items: list[dict], field: str) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        value = item.get(field)
        if value:
            groups[str(value)].append(item)
    return [
        {
            "value": value,
            "count": len(group),
            "ids": [item.get("id") for item in group],
            "titles": [item.get("title") for item in group],
        }
        for value, group in sorted(groups.items())
        if len(group) > 1
    ]


def same_title_different_url(items: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        title = item.get("title")
        if title:
            groups[str(title)].append(item)
    suspicious = []
    for title, group in sorted(groups.items()):
        urls = sorted({item.get("archive_url") for item in group if item.get("archive_url")})
        if len(urls) > 1:
            suspicious.append(
                {
                    "title": title,
                    "count": len(group),
                    "ids": [item.get("id") for item in group],
                    "archive_urls": urls,
                }
            )
    return suspicious


def metadata_quality(inventory: list[dict]) -> dict:
    return {
        "total_items": len(inventory),
        "items_with_date": sum(1 for item in inventory if item.get("meeting_date")),
        "items_without_date": sum(1 for item in inventory if not item.get("meeting_date")),
        "items_with_meeting_no": sum(1 for item in inventory if item.get("meeting_no") is not None),
        "items_without_meeting_no": sum(1 for item in inventory if item.get("meeting_no") is None),
        "items_with_year_inferred_from_section": sum(1 for item in inventory if item.get("year_source") == "section"),
        "items_with_year_inferred_from_title": sum(1 for item in inventory if item.get("year_source") == "title"),
        "items_with_year_inferred_from_date": sum(1 for item in inventory if item.get("year_source") == "date"),
        "items_without_year": sum(1 for item in inventory if item.get("year_source") in {None, "none"}),
    }


def period_year_matrix(inventory: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for item in inventory:
        key = (str(item.get("period") or "unknown"), str(item.get("year") or "unknown"))
        grouped[key][item.get("kind") or "unknown"] += 1

    rows = []
    for (period, year), values in sorted(grouped.items()):
        rows.append(
            {
                "period": period,
                "year": year,
                "usneseni": values.get("usneseni", 0),
                "hlasovani": values.get("hlasovani", 0),
                "hlasovani_aklamaci": values.get("hlasovani_aklamaci", 0),
                "unknown": values.get("unknown", 0),
            }
        )
    return rows


def build_report(inventory: list[dict], records: list[dict], extraction: dict, short_text_threshold: int) -> dict:
    errors = []
    for item in inventory:
        if item.get("download_error"):
            errors.append({"id": item["id"], "stage": "download", "error": item["download_error"]})
    for item_id, item in extraction.items():
        if item.get("error") and item.get("error") != "not_downloaded":
            errors.append({"id": item_id, "stage": "extract", "error": item["error"]})

    documents_without_date = [item["id"] for item in inventory if not item.get("meeting_date")]
    documents_without_date_by_reason = counter(
        item.get("date_missing_reason") for item in inventory if not item.get("meeting_date")
    )
    short_text_documents = [
        record["id"]
        for record in records
        if record.get("text_quality", {}).get("has_text")
        and record.get("text_quality", {}).get("text_chars", 0) < short_text_threshold
    ]
    text_quality_counts = counter(
        item.get("quality_flag") or ("text_ok" if item.get("has_text") else "empty_text")
        for item in extraction.values()
    )

    return {
        "total_links": len(inventory),
        "metadata_quality": metadata_quality(inventory),
        "by_period": counter(item.get("period") for item in inventory),
        "by_kind": counter(item.get("kind") for item in inventory),
        "by_file_type": counter(item.get("file_type") for item in inventory),
        "by_status": counter(item.get("status") for item in inventory),
        "period_year": period_year_matrix(inventory),
        "duplicates": {
            "duplicate_archive_url": duplicate_groups(inventory, "archive_url"),
            "duplicate_resolved_file_url": duplicate_groups(inventory, "resolved_file_url"),
            "duplicate_generated_id": duplicate_groups(inventory, "id"),
            "same_title_different_url": same_title_different_url(inventory),
        },
        "text_quality": text_quality_counts,
        "documents_with_text": sum(1 for record in records if record.get("text_quality", {}).get("has_text")),
        "documents_without_text": sum(1 for record in records if not record.get("text_quality", {}).get("has_text")),
        "documents_without_date": documents_without_date,
        "documents_without_date_by_reason": documents_without_date_by_reason,
        "short_text_threshold": short_text_threshold,
        "suspiciously_short_text": short_text_documents,
        "errors": errors,
    }


def markdown_counter(title: str, values: dict) -> list[str]:
    lines = [f"## {title}", ""]
    if not values:
        lines.append("_Žádné položky._")
    else:
        for key, value in values.items():
            lines.append(f"- `{key}`: {value}")
    lines.append("")
    return lines


def report_to_markdown(report: dict) -> str:
    title = report.get("report_title") or "Archiv Litovel - report"
    lines = [f"# {title}", ""]
    lines.append(f"- Nalezené odkazy: {report['total_links']}")
    lines.append(f"- Dokumenty s textem: {report['documents_with_text']}")
    lines.append(f"- Dokumenty bez textu: {report['documents_without_text']}")
    lines.append("")
    lines.append("## Metadata quality")
    lines.append("")
    for key, value in report["metadata_quality"].items():
        lines.append(f"- `{key}`: {value}")
    lines.append("")
    lines.extend(markdown_counter("Podle období", report["by_period"]))
    lines.extend(markdown_counter("Podle typu dokumentu", report["by_kind"]))
    lines.extend(markdown_counter("Podle typu souboru", report["by_file_type"]))
    lines.extend(markdown_counter("Podle stavu", report["by_status"]))
    lines.extend(markdown_counter("Text quality", report["text_quality"]))

    lines.append("## Podle období a roku")
    lines.append("")
    lines.append("| Period | Year | Usneseni | Hlasovani | Hlasovani aklamaci | Unknown |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for row in report["period_year"]:
        lines.append(
            f"| {row['period']} | {row['year']} | {row['usneseni']} | {row['hlasovani']} | "
            f"{row['hlasovani_aklamaci']} | {row['unknown']} |"
        )
    lines.append("")

    lines.append("## Dokumenty bez data")
    lines.append("")
    lines.extend(markdown_counter("Důvody chybějícího data", report["documents_without_date_by_reason"]))
    if report["documents_without_date"]:
        for item_id in report["documents_without_date"]:
            lines.append(f"- `{item_id}`")
    else:
        lines.append("_Žádné._")
    lines.append("")

    lines.append("## Podezřele krátký text")
    lines.append("")
    lines.append(f"Prahová hodnota: {report['short_text_threshold']} znaků")
    if report["suspiciously_short_text"]:
        for item_id in report["suspiciously_short_text"]:
            lines.append(f"- `{item_id}`")
    else:
        lines.append("_Žádné._")
    lines.append("")

    lines.append("## Duplicity")
    lines.append("")
    for title, key in (
        ("Duplicate archive_url", "duplicate_archive_url"),
        ("Duplicate resolved_file_url", "duplicate_resolved_file_url"),
        ("Duplicate generated id", "duplicate_generated_id"),
        ("Same title with different URL", "same_title_different_url"),
    ):
        lines.append(f"### {title}")
        lines.append("")
        entries = report["duplicates"][key]
        if entries:
            for entry in entries:
                if "value" in entry:
                    lines.append(f"- `{entry['value']}` ({entry['count']}): {', '.join(entry['ids'])}")
                else:
                    lines.append(f"- `{entry['title']}` ({entry['count']}): {', '.join(entry['ids'])}")
        else:
            lines.append("_Žádné._")
        lines.append("")

    lines.append("## Chyby")
    lines.append("")
    if report["errors"]:
        for error in report["errors"]:
            lines.append(f"- `{error['id']}` ({error['stage']}): {error['error']}")
    else:
        lines.append("_Žádné._")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=Path("work/archive_zm/inventory.json"))
    parser.add_argument("--records", type=Path, default=Path("work/archive_zm/archive_documents.json"))
    parser.add_argument("--extraction", type=Path, default=Path("work/archive_zm/extraction.json"))
    parser.add_argument("--json-output", type=Path, default=Path("work/archive_zm/report.json"))
    parser.add_argument("--md-output", type=Path, default=Path("work/archive_zm/report.md"))
    parser.add_argument("--short-text-threshold", type=int, default=200)
    args = parser.parse_args()

    inventory = read_json(args.inventory, [])
    records = read_json(args.records, [])
    extraction = read_json(args.extraction, {})
    if not isinstance(inventory, list) or not isinstance(records, list) or not isinstance(extraction, dict):
        raise SystemExit("Invalid report inputs.")

    report = build_report(inventory, records, extraction, args.short_text_threshold)
    if inventory:
        report["report_title"] = f"Archiv {inventory[0].get('org') or 'ZM'} Litovel - report"
    write_json(args.json_output, report)
    args.md_output.parent.mkdir(parents=True, exist_ok=True)
    args.md_output.write_text(report_to_markdown(report), encoding="utf-8")

    print(f"Report written: {args.json_output}")
    print(f"Markdown report written: {args.md_output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
