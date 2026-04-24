"""Helpers for deriving resident-facing RO/RZ titles and totals.

The raw RO rows often contain one bookkeeping line and one meaningful line.
These helpers try to surface the specific citizen-relevant label while keeping
the accounting rows available below it.
"""

from __future__ import annotations

import html
import re
from collections import Counter
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

    sentence_end_re = re.compile(r"[.!?](?=\s+(?:[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ„\"(]|$))")
    match = sentence_end_re.search(text)
    if match:
        return text[: match.end()].strip()
    return text


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


def is_generic_budget_title(candidate: str) -> bool:
    """Heuristics for source/transfer lines that should lose to specific targets."""
    candidate = normalize_whitespace(candidate).lower()
    generic_patterns = (
        r"\brezerva\b",
        r"\btransfery dle rozhodn",
        r"\bostatni zalezitosti\b",
        r"\bzmena stavu\b",
        r"\buroky z prijatych uveru\b",
        r"\bpresun mezi polozkami\b",
    )
    return any(re.search(pattern, candidate) for pattern in generic_patterns)


def common_prefix(values: List[str]) -> str:
    if not values:
        return ""
    prefix = values[0]
    for value in values[1:]:
        while prefix and not value.startswith(prefix):
            prefix = prefix[:-1]
    return prefix.rstrip(" ,-")


def plain_title_from_rows(rows: List[Dict], budget_change_id: str) -> str:
    """Pick the most specific row-derived title for an RZ bundle."""
    candidates = row_title_candidates(rows, budget_change_id)
    if not candidates:
        return ""
    if len(candidates) == 1:
        return candidates[0]

    specific_candidates = [candidate for candidate in candidates if not is_generic_budget_title(candidate)]
    if len(specific_candidates) == 1:
        return specific_candidates[0]

    prefix = common_prefix(candidates)
    if len(prefix) >= 18:
        return prefix
    if len(set(candidates)) >= 3:
        return ""
    return specific_candidates[0] if specific_candidates else candidates[0]


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
    """Prefer note wording when row bundle has multiple unrelated row labels."""
    candidates = row_title_candidates(rows, budget_change_id)
    if len(candidates) < 3:
        return False
    if len(set(candidates)) < 3:
        return False
    return len(common_prefix(candidates)) < 18


def summarize_budget_change(rows: List[Dict], note: Optional[Dict], budget_change_id: str) -> Dict[str, object]:
    """Return presentation metadata for one rendered RZ group."""
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

    if title:
        title = title.rstrip(".")
    return {"title": title, "totals": totals}


def amount_class(row: Dict) -> str:
    value = row.get("amount_value")
    if isinstance(value, (int, float)):
        if value < 0:
            return " usn-amount-negative"
        if value > 0:
            return " usn-amount-positive"
    return ""


def render_budget_change_totals(totals: Dict[str, Dict[str, float]]) -> str:
    """Render user-facing totals for one RZ across income/expense/financing rows."""
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


CATEGORY_RULES = [
    ("školy", (r"\bzš\b", r"\bmš\b", r"\bškol", r"\bškolk", r"\bdružin", r"\bnasobůr", r"\bgemersk", r"\bjungmann")),
    ("doprava", (r"\bdoprav", r"\bkomunikac", r"\bsilnic", r"\bchodník", r"\bparkov", r"\bcykl", r"\bmost")),
    ("životní prostředí", (r"\bzeleň", r"\bstrom", r"\bpark", r"\bodpad", r"\beko", r"\bživotní prostředí")),
    ("ČOV / voda", (r"\bčov\b", r"\bkanaliz", r"\bvodovod", r"\bvoda\b", r"\bdešťov", r"\bčistírn")),
    ("dary a dotace", (r"\bdotac", r"\bdar", r"\bgrant", r"\btransfer", r"\bpojistné plnění", r"\bpříspěvk")),
    ("místní části", (r"\bunčovic", r"\bnasobůrk", r"\bmyslechovic", r"\bchořelic", r"\bsavín", r"\bvísk", r"\bnov(?:á|e) ves")),
    ("krizové řízení", (r"\bpovode", r"\bkriz", r"\bbezpeč", r"\bpožár", r"\bhasič")),
    ("kultura a sport", (r"\bkultur", r"\bsport", r"\bsokolovn", r"\bknihovn", r"\bmuze", r"\bhřišt", r"\bdivadl")),
    ("převody rezerv", (r"\brezerv", r"\bpřesun", r"\bpřevod", r"\bzměna stavu\b")),
]

UPPERCASE_SOURCE_RE = re.compile(r"^[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]{2,}(?:\s+[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]{2,})*$")
PERSON_INITIALS_RE = re.compile(
    r"^[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]\.?\s*[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]\.?(?:\s*[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]\.?)?$"
)
GENERIC_MENTION_RE = re.compile(
    r"^(?:"
    r"účelová\s+(?:ne)?inv\.\s+dotace|"
    r"dotace|"
    r"dotace\s+.+|"
    r"dar|grant|transfer|"
    r"technické úpravy|"
    r"údržba a vybavenost|"
    r"oprava vstupního schodiště|"
    r"vratka(?:\s+účelově\s+vázaného\s+příspěvku)?|"
    r"transfery dle rozhodnutí RM|"
    r"změna stavu finančních prostředků na BÚ|"
    r"přijaté pojistné plnění"
    r")$",
    flags=re.IGNORECASE,
)

GENERIC_PREFIX_RE = re.compile(
    r"^(?:"
    r"účelová\s+(?:ne)?inv\.\s+dotace\s*-\s*|"
    r"dotace na\s+|"
    r"dotace\s*-\s*|"
    r"finanční příspěvek na\s+"
    r")",
    flags=re.IGNORECASE,
)

TRAILING_STAGE_RE = re.compile(r"\s*-\s*\d+\.\s*etapa$", flags=re.IGNORECASE)
AMOUNT_PAREN_RE = re.compile(r"\(\s*\d[\d\s.,]*\s*Kč\s*\)")
ACTIVITY_PREFIX_RE = re.compile(r"^(?:činnost družstva|činnost)\s+(.+)$", flags=re.IGNORECASE)


def clean_relatable_segment(segment: str) -> str:
    segment = normalize_whitespace(segment)
    if not segment:
        return ""
    segment = AMOUNT_PAREN_RE.sub("", segment)
    segment = TRAILING_STAGE_RE.sub("", segment)
    segment = GENERIC_PREFIX_RE.sub("", segment)
    segment = re.sub(r"\borg\.?\s*zaj\.[^,;]*", "", segment, flags=re.IGNORECASE)
    segment = re.sub(r"\s*\+\s*", ", ", segment)
    segment = segment.strip(" ,-")

    lowered = segment.lower()
    if lowered.startswith(("dne ", "na základě ", "v průběhu ", "město přijalo ")):
        return ""
    if "rozpočtovou změnu" in lowered:
        return ""
    activity_match = ACTIVITY_PREFIX_RE.match(segment)
    if activity_match:
        segment = activity_match.group(1).strip(" ,-")
    if GENERIC_MENTION_RE.match(segment):
        return ""
    return segment


def budget_change_note_map(notes: List[Dict]) -> Dict[str, Dict]:
    mapped: Dict[str, Dict] = {}
    for note in notes:
        title = note.get("title") or ""
        match = re.search(r"\b(?:RZ\s+)?(?P<id>\d{1,4}\s*/\s*\d{4}\s*/\s*(?:RM|ZM))\b", title, re.IGNORECASE)
        if match and note.get("text"):
            mapped[re.sub(r"\s+", "", match.group("id").upper())] = note
    return mapped


def budget_change_groups_from_opatreni(opatreni: Dict) -> List[Dict[str, object]]:
    notes_by_rz = budget_change_note_map(opatreni.get("notes") or [])
    grouped: List[Dict[str, object]] = []
    rows_by_id: Dict[str, List[Dict]] = {}
    order: List[str] = []
    for section in opatreni.get("sections") or []:
        for row in section.get("rows") or []:
            budget_change_id = row.get("budget_change_id") or ""
            if not budget_change_id:
                continue
            if budget_change_id not in rows_by_id:
                rows_by_id[budget_change_id] = []
                order.append(budget_change_id)
            rows_by_id[budget_change_id].append({**row, "section_type": section.get("type")})

    for budget_change_id in order:
        rows = rows_by_id[budget_change_id]
        note = notes_by_rz.get(budget_change_id)
        summary = summarize_budget_change(rows, note, budget_change_id)
        grouped.append(
            {
                "budget_change_id": budget_change_id,
                "rows": rows,
                "note": note,
                "title": str(summary["title"]) if summary["title"] else "",
                "affected_place": affected_place_service_from_title(str(summary["title"]) if summary["title"] else ""),
            }
        )
    return grouped


def budget_change_titles_from_opatreni(opatreni: Dict) -> List[str]:
    titles: List[str] = []
    for group in budget_change_groups_from_opatreni(opatreni):
        title = group.get("title") or ""
        if title:
            titles.append(str(title))
    return titles


def affected_place_service_from_title(title: str) -> str:
    title = normalize_whitespace(title)
    if not title:
        return ""

    if UPPERCASE_SOURCE_RE.match(title) or PERSON_INITIALS_RE.match(title):
        return ""

    parts = [part.strip(" ,.") for part in re.split(r"\s+-\s+", title) if part.strip(" ,.")]
    cleaned_parts = []
    for part in parts:
        if UPPERCASE_SOURCE_RE.match(part) or PERSON_INITIALS_RE.match(part):
            continue
        cleaned = clean_relatable_segment(part)
        if cleaned:
            cleaned_parts.append(cleaned)

    if not cleaned_parts:
        cleaned = clean_relatable_segment(title)
        return cleaned

    if (
        len(cleaned_parts) >= 2
        and len(cleaned_parts[0]) <= 32
        and len(cleaned_parts[1]) <= 32
        and not GENERIC_MENTION_RE.match(cleaned_parts[0])
        and not GENERIC_MENTION_RE.match(cleaned_parts[1])
    ):
        return " / ".join(cleaned_parts[:2])

    return cleaned_parts[0]

    return ""


def budget_change_affected_places_from_opatreni(opatreni: Dict) -> List[str]:
    labels: List[str] = []
    seen = set()
    for group in budget_change_groups_from_opatreni(opatreni):
        label = affected_place_service_from_title(str(group.get("title") or ""))
        if label and label not in seen:
            labels.append(label)
            seen.add(label)
    return labels


def summarize_affected_places(opatreni: Dict, limit: int = 3) -> str:
    labels = budget_change_affected_places_from_opatreni(opatreni)
    if not labels:
        return ""
    summary = ", ".join(labels[:limit])
    if len(labels) > limit:
        summary += ", …"
    return summary


def categories_from_texts(texts: List[str]) -> List[str]:
    found: List[str] = []
    haystack = " ".join(normalize_whitespace(text).lower() for text in texts if text)
    if not haystack:
        return found
    for label, patterns in CATEGORY_RULES:
        if any(re.search(pattern, haystack, flags=re.IGNORECASE) for pattern in patterns):
            found.append(label)
    return found


def budget_change_categories(opatreni: Dict) -> List[List[str]]:
    categorized: List[List[str]] = []
    for group in budget_change_groups_from_opatreni(opatreni):
        texts = []
        title = str(group.get("title") or "")
        if title:
            texts.append(title)
        note = group.get("note")
        if isinstance(note, dict) and note.get("text"):
            texts.append(str(note.get("text") or ""))
        categories = categories_from_texts(texts)
        if categories:
            categorized.append(categories)
    return categorized


def aggregate_top_categories(opatreni: Dict, limit: int = 4) -> List[str]:
    counts: Counter[str] = Counter()
    for categories in budget_change_categories(opatreni):
        for category in set(categories):
            counts[category] += 1

    rule_order = {label: index for index, (label, _) in enumerate(CATEGORY_RULES)}
    ranked = sorted(counts.items(), key=lambda item: (-item[1], rule_order.get(item[0], 999), item[0]))
    return [label for label, _ in ranked[:limit]]


def summarize_opatreni_plain(opatreni: Dict) -> str:
    titles = budget_change_titles_from_opatreni(opatreni)
    categories = aggregate_top_categories(opatreni)
    budget_change_count = len(opatreni.get("budget_change_ids") or [])

    if categories:
        limited = categories[:5]
        if budget_change_count:
            return f"{budget_change_count} změn: {', '.join(limited)}"
        return ", ".join(limited)

    if titles:
        limited_titles = titles[:3]
        summary = ", ".join(limited_titles)
        if len(titles) > 3:
            summary += ", …"
        if budget_change_count:
            return f"{budget_change_count} změn: {summary}"
        return summary

    if budget_change_count:
        return f"{budget_change_count} změn v rozpočtu"
    return ""
