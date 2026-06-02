#!/usr/bin/env python3
"""Split Litovel ZM archive documents into conservative archive_resolution records."""

from __future__ import annotations

import argparse
import re
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from archive_zm_common import read_json, slug_part, write_json
except ImportError:
    from tools.archive_zm_common import read_json, slug_part, write_json


INDEXABLE_QUALITY_FLAGS = {"text_ok", "short_text"}
MIN_DOCUMENT_CHARS = 300
MIN_BLOCK_CHARS = 40
MIN_AVG_BLOCK_CHARS = 120
MAX_BOUNDARIES_PER_1000_CHARS = 18
UNSPLIT_REASONS = (
    "no_boundaries",
    "single_boundary",
    "suspicious_boundaries",
    "text_too_short",
    "unsupported_kind",
    "bad_quality",
)

DECISION_VERB_RE = re.compile(
    r"^(bere\s+na\s+vědomí|schvaluje|ukládá|souhlasí|neschvaluje|nepřijímá|přijímá|neakceptuje|volí|"
    r"stanoví|zřizuje|deleguje|pověřuje|jmenuje|revokuje)\b",
    re.IGNORECASE,
)
EXPLICIT_RESOLUTION_RE = re.compile(
    r"^\s*usnesen[ií]\s+(?:zm\s+)?(?:č\.|c\.)\s*"
    r"(?P<number>[0-9]+(?:\s*/\s*(?:19|20)[0-9]{2})?)?",
    re.IGNORECASE,
)
NUMBERED_STANDALONE_RE = re.compile(
    r"^\s*(?:č\.|c\.)\s*(?P<number>[0-9]{1,4}\s*/\s*(?:19|20)[0-9]{2})\s*[-–:.)]?\s*$",
    re.IGNORECASE,
)
BARE_STANDALONE_RE = re.compile(
    r"^\s*(?P<number>[0-9]{1,4}\s*/\s*(?:19|20)[0-9]{2})\s*[-–:.)]?\s*$"
)
SLASH_MEETING_HEADING_RE = re.compile(
    r"^\s*(?P<number>[0-9]{1,4}\s*/+\s*[0-9]{1,3})\s+"
    r"(?P<title>[^\s][^\n]{2,})$"
)
ORDINAL_VERB_RE = re.compile(
    r"^\s*(?P<number>[0-9]{1,3})[\.)]\s+"
    r"(?P<verb>Bere\s+na\s+vědomí|Schvaluje|Ukládá|Souhlasí|Neschvaluje|Nepřijímá|Přijímá|Neakceptuje|Volí|"
    r"Stanoví|Zřizuje|Deleguje|Pověřuje|Jmenuje|Revokuje)\b",
    re.IGNORECASE,
)
STANDALONE_ORDINAL_RE = re.compile(r"^\s*(?P<number>[0-9]{1,3})[\.)]?\s*$")


@dataclass(frozen=True)
class Line:
    text: str
    start: int
    end: int
    index: int


@dataclass(frozen=True)
class Boundary:
    start: int
    line_index: int
    method: str
    resolution_no: str | None
    ordinal_value: int | None


def iter_lines(text: str) -> list[Line]:
    lines = []
    offset = 0
    for index, raw_line in enumerate(text.splitlines(keepends=True)):
        end = offset + len(raw_line)
        lines.append(Line(raw_line.rstrip("\r\n"), offset, end, index))
        offset = end
    if text and not lines:
        lines.append(Line(text, 0, len(text), 0))
    return lines


def first_non_space_position(line: Line) -> int:
    stripped_len = len(line.text) - len(line.text.lstrip())
    return line.start + stripped_len


def next_nonempty_line(lines: list[Line], index: int) -> Line | None:
    for candidate in lines[index + 1:]:
        if candidate.text.strip():
            return candidate
    return None


def starts_with_decision_verb(value: str) -> bool:
    return bool(DECISION_VERB_RE.search(value.strip()))


def looks_like_rm_slash_heading(value: str, expected_meeting_no: int | None = None) -> bool:
    match = SLASH_MEETING_HEADING_RE.search(value)
    if not match:
        return False
    parts = re.split(r"/+", match.group("number"))
    if expected_meeting_no is not None and len(parts) == 2:
        try:
            if int(parts[1].strip()) != expected_meeting_no:
                return False
        except ValueError:
            return False
    title = match.group("title").strip()
    folded = title.casefold()
    if folded.startswith(("z:", "t:", "termín", "termin", "strana", "page")):
        return False
    return True


def normalize_resolution_no(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = " ".join(value.replace("\xa0", " ").split())
    return re.sub(r"/+", "/", cleaned.replace(" ", ""))


def find_boundaries(text: str, expected_meeting_no: int | None = None) -> list[Boundary]:
    boundaries: list[Boundary] = []
    seen_starts: set[int] = set()
    lines = iter_lines(text)

    for line in lines:
        stripped = line.text.strip()
        if not stripped:
            continue

        start = first_non_space_position(line)
        boundary: Boundary | None = None

        explicit = EXPLICIT_RESOLUTION_RE.search(line.text)
        if explicit:
            boundary = Boundary(
                start=start,
                line_index=line.index,
                method="numbered_resolution",
                resolution_no=normalize_resolution_no(explicit.group("number")),
                ordinal_value=None,
            )

        if boundary is None:
            numbered = NUMBERED_STANDALONE_RE.search(line.text) or BARE_STANDALONE_RE.search(line.text)
            next_line = next_nonempty_line(lines, line.index)
            if numbered and next_line and starts_with_decision_verb(next_line.text):
                boundary = Boundary(
                    start=start,
                    line_index=line.index,
                    method="numbered_resolution",
                    resolution_no=normalize_resolution_no(numbered.group("number")),
                    ordinal_value=None,
                )

        if boundary is None and looks_like_rm_slash_heading(line.text, expected_meeting_no):
            slash_heading = SLASH_MEETING_HEADING_RE.search(line.text)
            boundary = Boundary(
                start=start,
                line_index=line.index,
                method="numbered_resolution",
                resolution_no=normalize_resolution_no(slash_heading.group("number") if slash_heading else None),
                ordinal_value=None,
            )

        if boundary is None:
            ordinal = ORDINAL_VERB_RE.search(line.text)
            if ordinal:
                value = int(ordinal.group("number"))
                boundary = Boundary(
                    start=start,
                    line_index=line.index,
                    method="heading_resolution",
                    resolution_no=str(value),
                    ordinal_value=value,
                )

        if boundary is None:
            standalone = STANDALONE_ORDINAL_RE.search(line.text)
            next_line = next_nonempty_line(lines, line.index)
            if standalone and next_line and starts_with_decision_verb(next_line.text):
                value = int(standalone.group("number"))
                boundary = Boundary(
                    start=start,
                    line_index=line.index,
                    method="heading_resolution",
                    resolution_no=str(value),
                    ordinal_value=value,
                )

        if boundary and boundary.start not in seen_starts:
            boundaries.append(boundary)
            seen_starts.add(boundary.start)

    return sorted(boundaries, key=lambda item: item.start)


def trim_span(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def boundary_blocks(text: str, boundaries: list[Boundary]) -> list[tuple[Boundary, int, int, str]]:
    blocks = []
    for index, boundary in enumerate(boundaries):
        raw_end = boundaries[index + 1].start if index + 1 < len(boundaries) else len(text)
        start, end = trim_span(text, boundary.start, raw_end)
        blocks.append((boundary, start, end, text[start:end]))
    return blocks


def boundaries_are_suspicious(text: str, boundaries: list[Boundary]) -> bool:
    if len(boundaries) < 2:
        return False

    density = len(boundaries) / max(len(text), 1) * 1000
    if density > MAX_BOUNDARIES_PER_1000_CHARS:
        return True

    blocks = boundary_blocks(text, boundaries)
    lengths = [len(block_text.strip()) for _boundary, _start, _end, block_text in blocks]
    if any(length < MIN_BLOCK_CHARS for length in lengths):
        return True
    if sum(lengths) / len(lengths) < MIN_AVG_BLOCK_CHARS:
        return True

    ordinal_values = [
        boundary.ordinal_value
        for boundary in boundaries
        if boundary.ordinal_value is not None
    ]
    if len(ordinal_values) >= 2:
        increasing = all(b > a for a, b in zip(ordinal_values, ordinal_values[1:]))
        if not increasing:
            return True

    return False


def quality_flag(record: dict) -> str | None:
    return (record.get("text_quality") or {}).get("quality_flag")


def source_text(record: dict) -> str:
    return record.get("search_text") or record.get("display_text") or ""


def unsplit_reason(record: dict) -> str | None:
    if record.get("type") != "archive_document" or record.get("kind") != "usneseni":
        return "unsupported_kind"
    if quality_flag(record) not in INDEXABLE_QUALITY_FLAGS:
        return "bad_quality"
    if len(source_text(record).strip()) < MIN_DOCUMENT_CHARS:
        return "text_too_short"
    return None


def split_confidence(method: str) -> float:
    return 0.95 if method == "numbered_resolution" else 0.85


def child_id(parent_id: str, ordinal: int, resolution_no: str | None) -> str:
    base = f"{parent_id}-resolution-{ordinal:03d}"
    if resolution_no:
        return f"{base}-{slug_part(resolution_no)}"
    return base


def child_title(parent: dict, ordinal: int, resolution_no: str | None) -> str:
    suffix = f"usnesení {resolution_no}" if resolution_no else f"usnesení {ordinal}"
    return f"{parent.get('title') or parent.get('id')} - {suffix}"


def make_child(parent: dict, boundary: Boundary, ordinal: int, start: int, end: int, text: str) -> dict:
    return {
        "id": child_id(parent["id"], ordinal, boundary.resolution_no),
        "type": "archive_resolution",
        "legacy": True,
        "parent_document_id": parent["id"],
        "org": parent.get("org") or "ZM",
        "organ": parent.get("organ") or "Zastupitelstvo města Litovel",
        "title": child_title(parent, ordinal, boundary.resolution_no),
        "date": parent.get("date"),
        "year": parent.get("year"),
        "period": parent.get("period"),
        "meeting_no": parent.get("meeting_no"),
        "kind": "usneseni",
        "ordinal": ordinal,
        "resolution_no": boundary.resolution_no,
        "source_url": parent.get("source_url"),
        "original_file_url": parent.get("original_file_url"),
        "source_span": {
            "start_char": start,
            "end_char": end,
        },
        "split_method": boundary.method,
        "split_confidence": split_confidence(boundary.method),
        "search_text": text,
        "display_text": text,
    }


def split_document(record: dict) -> tuple[list[dict], dict]:
    base_reason = unsplit_reason(record)
    if base_reason:
        return [], {"id": record.get("id"), "status": "unsplit", "reason": base_reason, "boundary_count": 0}

    text = source_text(record)
    boundaries = find_boundaries(text, record.get("meeting_no"))
    if not boundaries:
        return [], {"id": record.get("id"), "status": "unsplit", "reason": "no_boundaries", "boundary_count": 0}
    if len(boundaries) == 1:
        return [], {"id": record.get("id"), "status": "unsplit", "reason": "single_boundary", "boundary_count": 1}
    if boundaries_are_suspicious(text, boundaries):
        return [], {
            "id": record.get("id"),
            "status": "unsplit",
            "reason": "suspicious_boundaries",
            "boundary_count": len(boundaries),
        }

    children = []
    for ordinal, (boundary, start, end, block_text) in enumerate(boundary_blocks(text, boundaries), start=1):
        children.append(make_child(record, boundary, ordinal, start, end, block_text))

    return children, {
        "id": record.get("id"),
        "status": "split",
        "reason": None,
        "boundary_count": len(boundaries),
        "resolution_count": len(children),
    }


def split_records(records: list[dict]) -> tuple[list[dict], dict]:
    resolutions: list[dict] = []
    outcomes = []
    unsplit_examples: dict[str, list[dict]] = {reason: [] for reason in UNSPLIT_REASONS}
    unsplit_counts = Counter({reason: 0 for reason in UNSPLIT_REASONS})
    split_by_method = Counter()
    split_counts = []

    for record in sorted(records, key=lambda item: (item.get("year") or 0, item.get("meeting_no") or 0, item.get("id") or "")):
        children, outcome = split_document(record)
        outcomes.append(outcome)
        if children:
            resolutions.extend(children)
            split_counts.append(len(children))
            split_by_method.update(child["split_method"] for child in children)
            continue

        reason = outcome["reason"]
        unsplit_counts[reason] += 1
        if len(unsplit_examples[reason]) < 10:
            unsplit_examples[reason].append(
                {
                    "id": record.get("id"),
                    "title": record.get("title"),
                    "boundary_count": outcome.get("boundary_count", 0),
                }
            )

    resolutions.sort(key=lambda item: (item.get("year") or 0, item.get("meeting_no") or 0, item["parent_document_id"], item["ordinal"]))
    split_documents = sum(1 for outcome in outcomes if outcome["status"] == "split")
    unsplit_documents = len(outcomes) - split_documents
    stats = {
        "min": min(split_counts) if split_counts else 0,
        "max": max(split_counts) if split_counts else 0,
        "median": statistics.median(split_counts) if split_counts else 0,
    }

    report = {
        "total_documents": len(records),
        "total_candidate_documents": sum(1 for record in records if record.get("type") == "archive_document" and record.get("kind") == "usneseni"),
        "split_documents": split_documents,
        "unsplit_documents": unsplit_documents,
        "total_archive_resolutions": len(resolutions),
        "split_by_method": dict(sorted(split_by_method.items())),
        "unsplit_reasons": dict(sorted(unsplit_counts.items())),
        "unsplit_examples": {
            reason: examples
            for reason, examples in unsplit_examples.items()
            if examples
        },
        "resolutions_per_split_document": stats,
        "outcomes": outcomes,
    }
    return resolutions, report


def report_to_markdown(report: dict) -> str:
    lines = ["# Archiv ZM Litovel - split report", ""]
    lines.append(f"- Dokumenty celkem: {report['total_documents']}")
    lines.append(f"- Kandidátní dokumenty: {report['total_candidate_documents']}")
    lines.append(f"- Rozdělené dokumenty: {report['split_documents']}")
    lines.append(f"- Nerozdělené dokumenty: {report['unsplit_documents']}")
    lines.append(f"- Vzniklá archivní usnesení: {report['total_archive_resolutions']}")
    lines.append("")

    lines.append("## Split by method")
    lines.append("")
    if report["split_by_method"]:
        for method, count in report["split_by_method"].items():
            lines.append(f"- `{method}`: {count}")
    else:
        lines.append("_Žádné splitnuté dokumenty._")
    lines.append("")

    lines.append("## Unsplit reasons")
    lines.append("")
    for reason, count in report["unsplit_reasons"].items():
        lines.append(f"- `{reason}`: {count}")
    lines.append("")

    lines.append("## Resolutions per split document")
    lines.append("")
    stats = report["resolutions_per_split_document"]
    lines.append(f"- `min`: {stats['min']}")
    lines.append(f"- `max`: {stats['max']}")
    lines.append(f"- `median`: {stats['median']}")
    lines.append("")

    lines.append("## Examples")
    lines.append("")
    if report["unsplit_examples"]:
        for reason, examples in report["unsplit_examples"].items():
            lines.append(f"### {reason}")
            lines.append("")
            for example in examples:
                lines.append(f"- `{example['id']}` ({example['boundary_count']} boundaries): {example.get('title') or ''}")
            lines.append("")
    else:
        lines.append("_Žádné nerozdělené dokumenty._")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("work/archive_zm/archive_documents.json"))
    parser.add_argument("--output", type=Path, default=Path("work/archive_zm/archive_resolutions.json"))
    parser.add_argument("--report", type=Path, default=Path("work/archive_zm/split_report.json"))
    parser.add_argument("--report-md", type=Path, default=Path("work/archive_zm/split_report.md"))
    args = parser.parse_args()

    records = read_json(args.input, [])
    if not isinstance(records, list):
        raise SystemExit("Archive documents input must be a JSON list.")

    resolutions, report = split_records(records)
    write_json(args.output, resolutions)
    write_json(args.report, report)
    args.report_md.parent.mkdir(parents=True, exist_ok=True)
    args.report_md.write_text(report_to_markdown(report), encoding="utf-8")

    print(f"Archive resolutions written: {args.output}")
    print(f"Split report written: {args.report}")
    print(f"Split documents: {report['split_documents']}")
    print(f"Archive resolutions: {report['total_archive_resolutions']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
