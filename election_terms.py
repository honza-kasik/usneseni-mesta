from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_TERMS = [
    {
        "id": "2018-2022",
        "label": "Volební období 2018-2022",
        "start": "2018-10-06",
        "end": "2022-09-24",
    },
    {
        "id": "2022-2026",
        "label": "Volební období 2022-2026",
        "start": "2022-09-24",
        "end": "2026-10-10",
    },
    {
        "id": "2026-2030",
        "label": "Volební období 2026-2030",
        "start": "2026-10-10",
        "end": None,
    },
]


def load_terms(path: Path | None = None) -> list[dict[str, Any]]:
    if path is None:
        return list(DEFAULT_TERMS)
    if not path.exists():
        raise FileNotFoundError(f"Election term config does not exist: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Election term config must be a JSON list.")
    return data


def term_for_date(date_value: str | None, terms: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    if not date_value:
        return None
    terms = DEFAULT_TERMS if terms is None else terms
    for term in terms:
        start = term.get("start")
        end = term.get("end")
        if start and date_value < start:
            continue
        if end and date_value >= end:
            continue
        return term
    return None


def apply_term_metadata(record: dict, terms: list[dict[str, Any]] | None = None) -> dict:
    term = term_for_date(record.get("datum") or record.get("date"), terms)
    if not term:
        return record
    record["term_id"] = term.get("id")
    record["term_label"] = term.get("label")
    return record
