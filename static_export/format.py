from __future__ import annotations

from datetime import datetime


def format_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%-d. %-m.")
    except Exception:
        return value or ""


def format_full_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%-d. %-m. %Y")
    except Exception:
        return value or ""


def budget_change_count_label(count: int) -> str:
    if count == 1:
        return "1 rozpočtová změna"
    if 2 <= count <= 4:
        return f"{count} rozpočtové změny"
    return f"{count} rozpočtových změn"
