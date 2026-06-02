#!/usr/bin/env python3
"""Promote modern-form archive documents into the normal phase1 dataset."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from archive_zm_common import read_json, write_json
except ImportError:
    from tools.archive_zm_common import read_json, write_json

from phase1_parse_pdf import parse_text, save_usneseni


INDEXABLE_QUALITY_FLAGS = {"text_ok", "short_text"}


def phase1_path(output: Path, resolution_id: str) -> Path:
    return output / f"{resolution_id.replace('/', '-')}.json"


def existing_resolution_data(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def load_inventory_by_id(root: Path) -> dict[str, dict]:
    inventory = read_json(root / "inventory.json", [])
    if not isinstance(inventory, list):
        return {}
    return {
        item.get("id"): item
        for item in inventory
        if isinstance(item, dict) and item.get("id")
    }


def load_text(root: Path, record: dict, extraction: dict) -> str:
    extraction_item = extraction.get(record.get("id"), {})
    text_path = extraction_item.get("text_path")
    if text_path:
        path = Path(text_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
    return record.get("search_text") or record.get("display_text") or ""


def provenance(record: dict, inventory_item: dict | None) -> dict:
    inventory_item = inventory_item or {}
    return {
        "legacy": True,
        "source": "archive",
        "archive_document_id": record.get("id"),
        "archive_title": record.get("title"),
        "source_url": record.get("source_url"),
        "original_file_url": record.get("original_file_url"),
        "source_pdf": inventory_item.get("local_path") or record.get("original_file_url"),
        "file_type": record.get("file_type"),
        "extraction_method": record.get("extraction_method"),
        "text_quality": record.get("text_quality") or {},
    }


def can_attempt_promotion(record: dict) -> str | None:
    if record.get("type") != "archive_document" or record.get("kind") != "usneseni":
        return "unsupported_kind"
    quality_flag = (record.get("text_quality") or {}).get("quality_flag")
    if quality_flag not in INDEXABLE_QUALITY_FLAGS:
        return "bad_quality"
    return None


def promote_record(
    *,
    root: Path,
    record: dict,
    extraction: dict,
    inventory_by_id: dict[str, dict],
    output: Path,
    written_ids: set[str],
) -> tuple[list[dict], dict]:
    record_id = record.get("id") or ""
    skip_reason = can_attempt_promotion(record)
    if skip_reason:
        return [], {"id": record_id, "status": "skipped", "reason": skip_reason, "resolution_count": 0}

    text = load_text(root, record, extraction)
    if not text.strip():
        return [], {"id": record_id, "status": "skipped", "reason": "no_text", "resolution_count": 0}

    records, error = parse_text(text, provenance(record, inventory_by_id.get(record_id)))
    if error:
        return [], {"id": record_id, "status": "skipped", "reason": "parse_failed", "error": error, "resolution_count": 0}

    promoted = []
    skipped_resolutions = Counter()
    skipped_resolution_ids: dict[str, list[str]] = defaultdict(list)

    for item in records:
        resolution_id = item["id"]
        destination = phase1_path(output, resolution_id)
        if resolution_id in written_ids:
            skipped_resolutions["duplicate_resolution"] += 1
            skipped_resolution_ids["duplicate_resolution"].append(resolution_id)
            continue

        if destination.exists():
            existing = existing_resolution_data(destination)
            same_promoted_source = (
                existing
                and existing.get("source") == "archive"
                and existing.get("archive_document_id") == record_id
            )
            if not same_promoted_source:
                skipped_resolutions["id_collision"] += 1
                skipped_resolution_ids["id_collision"].append(resolution_id)
                continue

        save_usneseni(item, output)
        written_ids.add(resolution_id)
        promoted.append(item)

    status = "promoted" if promoted else "skipped"
    reason = None if promoted else "all_resolutions_skipped"
    return promoted, {
        "id": record_id,
        "status": status,
        "reason": reason,
        "resolution_count": len(promoted),
        "skipped_resolutions": dict(skipped_resolutions),
        "skipped_resolution_ids": {
            key: sorted(values)
            for key, values in skipped_resolution_ids.items()
        },
    }


def promote_roots(archive_roots: list[Path], output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    written_ids: set[str] = set()
    promoted_resolution_ids: list[str] = []
    promoted_document_ids: list[str] = []
    outcomes = []
    skipped_documents = Counter()

    for root in archive_roots:
        records = read_json(root / "archive_documents.json", [])
        extraction = read_json(root / "extraction.json", {})
        if not root.exists() or not isinstance(records, list) or not isinstance(extraction, dict):
            outcomes.append({"archive_root": str(root), "status": "skipped", "reason": "missing_input"})
            skipped_documents["missing_input"] += 1
            continue

        inventory_by_id = load_inventory_by_id(root)
        for record in records:
            promoted, outcome = promote_record(
                root=root,
                record=record,
                extraction=extraction,
                inventory_by_id=inventory_by_id,
                output=output,
                written_ids=written_ids,
            )
            outcome["archive_root"] = str(root)
            outcomes.append(outcome)
            if promoted:
                promoted_document_ids.append(outcome["id"])
                promoted_resolution_ids.extend(item["id"] for item in promoted)
            else:
                skipped_documents[outcome.get("reason") or "unknown"] += 1

    return {
        "promoted_documents": len(promoted_document_ids),
        "promoted_resolutions": len(promoted_resolution_ids),
        "promoted_document_ids": sorted(promoted_document_ids),
        "promoted_resolution_ids": sorted(promoted_resolution_ids),
        "skipped_documents": dict(sorted(skipped_documents.items())),
        "outcomes": outcomes,
    }


def existing_archive_roots(workdir: Path) -> list[Path]:
    return [
        root
        for root in (workdir / "archive_rm", workdir / "archive_zm")
        if root.exists()
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive-root",
        type=Path,
        action="append",
        dest="archive_roots",
        help="Archive work root containing archive_documents.json and extraction.json. Can be repeated.",
    )
    parser.add_argument("--workdir", type=Path, default=Path("work"))
    parser.add_argument("--output", type=Path, default=Path("work/phase1"))
    parser.add_argument("--report", type=Path, default=Path("work/archive_current_promoted.json"))
    args = parser.parse_args()

    archive_roots = args.archive_roots or existing_archive_roots(args.workdir)
    if not archive_roots:
        report = {
            "promoted_documents": 0,
            "promoted_resolutions": 0,
            "promoted_document_ids": [],
            "promoted_resolution_ids": [],
            "skipped_documents": {"missing_input": 0},
            "outcomes": [],
        }
        write_json(args.report, report)
        print("No archive roots found for current-form promotion.")
        return 0

    report = promote_roots(archive_roots, args.output)
    write_json(args.report, report)

    print(f"Archive current-form promotion report written: {args.report}")
    print(f"Promoted archive documents: {report['promoted_documents']}")
    print(f"Promoted current resolutions: {report['promoted_resolutions']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
