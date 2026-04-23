from __future__ import annotations

import html
import re
from typing import Dict, List, Optional


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def format_amount_value(value: float) -> str:
    formatted = f"{abs(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", " ")
    sign = "+" if value > 0 else "-" if value < 0 else ""
    return f"{sign}{formatted} Kč"


def first_sentence(text: str) -> str:
    text = normalize_whitespace(text)
    if not text:
        return ""
    match = re.search(r"(.+?[.!?])(\s|$)", text)
    if match:
        return match.group(1).strip()
    return text


def plain_reason_from_note(note: Optional[Dict]) -> str:
    if not note:
        return ""
    return first_sentence(note.get("text") or "")


def description_title_candidate(description: str) -> str:
    description = normalize_whitespace(description)
    if not description:
        return ""
    description = re.sub(r"^\)\s*", "", description)
    description = re.sub(r"\b-\s*čerpání\b", "", description, flags=re.IGNORECASE)
    description = re.sub(r"\b-\s*převod dotace příjemci\b", "", description, flags=re.IGNORECASE)
    description = re.sub(r"\b-\s*související výdaje\b", "", description, flags=re.IGNORECASE)
    description = re.sub(r"\s+", " ", description).strip(" ,-")
    return description


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


def row_title_candidates(rows: List[Dict], budget_change_id: str) -> List[str]:
    candidates = []
    for row in rows:
        description = clean_budget_row_description(row.get("description") or "", budget_change_id)
        candidate = description_title_candidate(description)
        if candidate:
            candidates.append(candidate)
    return candidates


def common_prefix(values: List[str]) -> str:
    if not values:
        return ""
    prefix = values[0]
    for value in values[1:]:
        while prefix and not value.startswith(prefix):
            prefix = prefix[:-1]
    return prefix.rstrip(" ,-")


def plain_title_from_rows(rows: List[Dict], budget_change_id: str) -> str:
    candidates = row_title_candidates(rows, budget_change_id)
    if not candidates:
        return ""
    if len(candidates) == 1:
        return candidates[0]

    prefix = common_prefix(candidates)
    if len(prefix) >= 18:
        return prefix
    if len(set(candidates)) >= 3:
        return ""
    return candidates[0]


def plain_title_from_note(note: Optional[Dict]) -> str:
    if not note:
        return ""
    sentence = first_sentence(note.get("text") or "")
    if not sentence:
        return ""

    patterns = [
        (r"^V průběhu [^.]+ obdrželo město Litovel na svůj účet\s+", ""),
        (r"^Dne [^.]+ přijalo město Litovel na svůj účet\s+", ""),
        (r"^Dne [^.]+ obdrželo město Litovel na svůj účet\s+", ""),
        (r"^Dne [^.]+ obdrželo město Litovel\s+", ""),
        (r"^Na základě rozhodnutí o poskytnutí dotace byla městu Litovel schválena dotace (?:na akci|na realizaci projektu)\s+", ""),
        (r"^Město přijalo účelovou neinvestiční dotaci od [^.]+ určenou pro\s+", ""),
        (r"^Dne [^,]+ požádal [^.]+ o rozpočtovou změnu\.?\s*", ""),
        (r"^Na základě usnesení [^.]+\.\s*", ""),
        (r"^Dary a dotace poskytnuté na základě žádosti\.?\s*", ""),
    ]
    for pattern, replacement in patterns:
        candidate = re.sub(pattern, replacement, sentence, flags=re.IGNORECASE).strip(" .,-")
        if candidate and candidate != sentence:
            return candidate[:1].upper() + candidate[1:]
    return ""


def should_prefer_note_title(rows: List[Dict], budget_change_id: str) -> bool:
    candidates = row_title_candidates(rows, budget_change_id)
    if len(candidates) < 3:
        return False
    if len(set(candidates)) < 3:
        return False
    return len(common_prefix(candidates)) < 18


def summarize_budget_change(rows: List[Dict], note: Optional[Dict], budget_change_id: str) -> Dict[str, object]:
    totals: Dict[str, Dict[str, float]] = {}
    for row in rows:
        section_type = row.get("section_type")
        amount_value = row.get("amount_value")
        if section_type and isinstance(amount_value, (int, float)):
            section_totals = totals.setdefault(section_type, {"positive": 0.0, "negative": 0.0})
            value = float(amount_value)
            if value > 0:
                section_totals["positive"] += value
            elif value < 0:
                section_totals["negative"] += abs(value)

    row_title = plain_title_from_rows(rows, budget_change_id)
    note_title = plain_title_from_note(note)
    if should_prefer_note_title(rows, budget_change_id) and note_title:
        title = note_title
    else:
        title = row_title or note_title

    reason = plain_reason_from_note(note)
    if title:
        title = title.rstrip(".")
    return {"title": title, "reason": reason, "totals": totals}


def amount_class(row: Dict) -> str:
    value = row.get("amount_value")
    if isinstance(value, (int, float)):
        if value < 0:
            return " usn-amount-negative"
        if value > 0:
            return " usn-amount-positive"
    return ""


def render_budget_change_totals(totals: Dict[str, Dict[str, float]]) -> str:
    labels = {
        "prijmy": ("Navýšení příjmů", "Snížení příjmů", "Přesun v rámci příjmů bez změny celku"),
        "vydaje": ("Navýšení výdajů", "Snížení výdajů", "Přesun v rámci výdajů bez změny celku"),
        "financovani": ("Navýšení financování", "Snížení financování", "Přesun v rámci financování bez změny celku"),
    }
    parts = []
    for key in ("prijmy", "vydaje", "financovani"):
        section_totals = totals.get(key)
        if not section_totals:
            continue
        positive = section_totals.get("positive", 0.0)
        negative = section_totals.get("negative", 0.0)
        increase_label, decrease_label, transfer_label = labels[key]

        if positive >= 0.005:
            parts.append(
                '<li>'
                f'<span class="usn-rz-total-label">{increase_label}</span> '
                f'<strong class="usn-amount{amount_class({"amount_value": positive})}">{html.escape(format_amount_value(positive))}</strong>'
                '</li>'
            )
        if negative >= 0.005:
            parts.append(
                '<li>'
                f'<span class="usn-rz-total-label">{decrease_label}</span> '
                f'<strong class="usn-amount{amount_class({"amount_value": -negative})}">{html.escape(format_amount_value(-negative))}</strong>'
                '</li>'
            )
        if positive >= 0.005 and negative >= 0.005 and abs(positive - negative) < 0.005:
            parts.append(f'<li><span class="usn-rz-total-label">{transfer_label}</span></li>')
    if not parts:
        return ""
    return '<ul class="usn-rz-totals">' + "".join(parts) + '</ul>'
