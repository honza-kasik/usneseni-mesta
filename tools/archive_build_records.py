#!/usr/bin/env python3
"""Build normalized archive_document records from Litovel archive inventory."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from archive_zm_common import ORGAN, read_json, write_json
except ImportError:
    from tools.archive_zm_common import ORGAN, read_json, write_json


def load_text(extraction_item: dict) -> str:
    text_path = extraction_item.get("text_path")
    if not text_path:
        return ""
    path = Path(text_path)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def build_records(inventory: list[dict], extraction: dict) -> list[dict]:
    records = []
    for item in sorted(
        inventory,
        key=lambda value: (
            value.get("year") or 0,
            value.get("meeting_no") or 0,
            value.get("kind") or "",
            value.get("id") or "",
        ),
    ):
        item_id = item["id"]
        extraction_item = extraction.get(item_id, {})
        text = load_text(extraction_item)
        text_chars = int(extraction_item.get("text_chars") or len(text))
        chars_per_page = extraction_item.get("chars_per_page")
        has_text = bool(extraction_item.get("has_text")) or bool(text)

        records.append(
            {
                "id": item_id,
                "type": "archive_document",
                "legacy": True,
                "org": item.get("org") or "ZM",
                "organ": item.get("organ") or ORGAN,
                "title": item.get("title"),
                "date": item.get("meeting_date"),
                "date_missing_reason": item.get("date_missing_reason"),
                "year": item.get("year"),
                "year_source": item.get("year_source"),
                "period": item.get("period"),
                "meeting_no": item.get("meeting_no"),
                "meeting_no_source": item.get("meeting_no_source"),
                "kind": item.get("kind"),
                "source_url": item.get("archive_url"),
                "original_file_url": item.get("resolved_file_url") or item.get("archive_url"),
                "file_type": item.get("file_type"),
                "extraction_method": extraction_item.get("method") or "none",
                "ocr_used": False,
                "text_quality": {
                    "text_chars": text_chars,
                    "chars_per_page": chars_per_page,
                    "has_text": has_text,
                    "confidence": 1.0 if has_text else 0.0,
                    "quality_flag": extraction_item.get("quality_flag") or ("text_ok" if has_text else "empty_text"),
                },
                "search_text": text,
                "display_text": text,
            }
        )
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=Path("work/archive_zm/inventory.json"))
    parser.add_argument("--extraction", type=Path, default=Path("work/archive_zm/extraction.json"))
    parser.add_argument("--output", type=Path, default=Path("work/archive_zm/archive_documents.json"))
    args = parser.parse_args()

    inventory = read_json(args.inventory, [])
    extraction = read_json(args.extraction, {})
    if not isinstance(inventory, list):
        raise SystemExit("Inventory must be a JSON list.")
    if not isinstance(extraction, dict):
        raise SystemExit("Extraction metadata must be a JSON object.")

    records = build_records(inventory, extraction)
    write_json(args.output, records)
    print(f"Archive documents written: {args.output}")
    print(f"Documents: {len(records)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
