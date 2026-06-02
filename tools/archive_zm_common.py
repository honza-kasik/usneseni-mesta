#!/usr/bin/env python3
"""Shared helpers for Litovel ZM archive ingestion."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse


SOURCE = "litovel.eu"
ARCHIVE_URL = "https://www.litovel.eu/cs/mesto/zastupitelstvo-mesta/usneseni-zastupitelstva-archiv.html"
ORGAN = "Zastupitelstvo města Litovel"

MONTHS = {
    "ledna": "01",
    "unora": "02",
    "února": "02",
    "brezna": "03",
    "března": "03",
    "dubna": "04",
    "kvetna": "05",
    "května": "05",
    "cervna": "06",
    "června": "06",
    "cervence": "07",
    "července": "07",
    "srpna": "08",
    "zari": "09",
    "září": "09",
    "rijna": "10",
    "října": "10",
    "listopadu": "11",
    "prosince": "12",
}


def normalize_ws(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def fold_ascii(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii")


def slug_part(value: Any, fallback: str = "unknown") -> str:
    if value is None or value == "":
        return fallback
    text = fold_ascii(str(value)).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or fallback


def short_hash(value: str, length: int = 8) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:length]


def parse_cz_date(value: str) -> str | None:
    text = fold_ascii(normalize_ws(value.lower()))

    numeric = re.search(r"\b(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})\b", text)
    if numeric:
        day, month, year = numeric.groups()
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

    textual = re.search(r"\b(\d{1,2})\.\s*([a-z]+)\s+(\d{4})\b", text)
    if textual:
        day, month_raw, year = textual.groups()
        month = MONTHS.get(month_raw)
        if month:
            return f"{year}-{month}-{day.zfill(2)}"

    return None


def date_missing_reason(title: str, meeting_no: int | None) -> str | None:
    folded = fold_ascii(normalize_ws(title.lower()))
    if parse_cz_date(title):
        return None
    if folded == "hlasovani":
        return "generic_voting_title"
    if "hlasovani" in folded:
        return "no_date_in_title"
    if "usneseni" in folded and meeting_no is not None:
        return "meeting_only_historical_title"
    if "dne" in folded or "datum" in folded:
        return "unrecognized_date_format"
    return "no_date_in_title"


def classify_kind(title: str) -> str:
    folded = fold_ascii(title).lower()
    if "hlasovani" in folded and "aklamaci" in folded:
        return "hlasovani_aklamaci"
    if "hlasovani" in folded:
        return "hlasovani"
    if "usneseni" in folded:
        return "usneseni"
    return "unknown"


def parse_meeting_no(title: str) -> int | None:
    folded = fold_ascii(title).lower()
    match = re.search(r"\bz(?:e)?\s+(\d+)(?:\.|\s+zml\b|\s+zasedani\b)", folded)
    if match:
        return int(match.group(1))
    return None


def infer_year(title: str, meeting_date: str | None, context_year: int | None) -> int | None:
    year, _source = infer_year_with_source(title, meeting_date, context_year)
    return year


def infer_year_with_source(
    title: str,
    meeting_date: str | None,
    context_year: int | None,
) -> tuple[int | None, str]:
    if meeting_date:
        return int(meeting_date[:4]), "date"
    folded = fold_ascii(title)
    matches = re.findall(r"\b(19\d{2}|20\d{2})\b", folded)
    if matches:
        return int(matches[-1]), "title"
    if context_year is not None:
        return context_year, "section"
    return None, "none"


def parse_title_metadata(title: str, context_year: int | None = None) -> dict[str, Any]:
    clean = normalize_ws(title).strip(" ;")
    meeting_date = parse_cz_date(clean)
    meeting_no = parse_meeting_no(clean)
    year, year_source = infer_year_with_source(clean, meeting_date, context_year)
    return {
        "title": clean,
        "kind": classify_kind(clean),
        "meeting_no": meeting_no,
        "meeting_no_source": "title" if meeting_no is not None else "none",
        "meeting_date": meeting_date,
        "date_missing_reason": date_missing_reason(clean, meeting_no),
        "year": year,
        "year_source": year_source,
    }


def classify_url(url: str, title_attr: str = "") -> tuple[str, str | None, str, str | None]:
    parsed = urlparse(url)
    path = parsed.path.lower()
    query = parse_qs(parsed.query)

    filemanager_id = None
    if "filemanager/files/" in path:
        match = re.search(r"/filemanager/files/([^/?#]+)", parsed.path)
        if match:
            stem = Path(match.group(1)).stem
            filemanager_id = stem
        return "direct_file", filemanager_id, file_type_from_url_or_title(url, title_attr), url

    if "flipbook_new.inc.php" in path:
        ids = query.get("fileID") or query.get("fileid")
        filemanager_id = ids[0] if ids else None
        return "flipbook", filemanager_id, "pdf", None

    return "unknown", None, file_type_from_url_or_title(url, title_attr), None


def file_type_from_url_or_title(url: str, title_attr: str = "") -> str:
    path = urlparse(url).path.lower()
    suffix = Path(path).suffix.lower().lstrip(".")
    if suffix in {"pdf", "doc", "docx"}:
        return suffix
    title = title_attr.lower()
    for candidate in ("pdf", "docx", "doc"):
        if f"*.{candidate}" in title or f".{candidate}" in title:
            return candidate
    return "unknown"


def resolved_file_url_from_id(filemanager_id: str, file_type: str) -> str | None:
    if not filemanager_id or file_type not in {"pdf", "doc", "docx"}:
        return None
    return f"https://www.litovel.eu/filemanager/files/{filemanager_id}.{file_type}"


def stable_base_id(
    org_code: str,
    year: int | None,
    meeting_no: int | None,
    kind: str,
) -> str:
    return f"{slug_part(org_code).upper()}-archive-{slug_part(year)}-{slug_part(meeting_no)}-{slug_part(kind)}"


def uniquify_id(base_id: str, url: str, used: set[str]) -> str:
    if base_id not in used:
        used.add(base_id)
        return base_id
    unique = f"{base_id}-{short_hash(url)}"
    used.add(unique)
    return unique


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def absolute_url(href: str, base_url: str = ARCHIVE_URL) -> str:
    return urljoin(base_url, href)
