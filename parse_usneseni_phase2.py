#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import re
import argparse
from pathlib import Path
from collections import Counter


# ============================================================
# REGEXY
# ============================================================

ID_RE = re.compile(r"^RM/\d+/\d+/\d+$")
ITEM_RE = re.compile(r"(?:^|\n)([a-z])\)\s+")

ACTION_PHRASES = [
    "uděluje předběžný souhlas",
    "uděluje výjimku",
    "byla seznámena",
    "bere na vědomí",
    "neschvaluje",
    "schvaluje",
    "nesouhlasí",
    "souhlasí",
    "ukládá",
    "revokuje",
    "vydává",
    "stanovuje",
    "doporučuje",
    "nedoporučuje",
    "odkládá",
    "jmenuje",
    "pověřuje",
    "svěřuje",
    "určuje",
    "zajistí",
    "vyhovuje",
    "nevyhovuje",
    "rozhoduje",
    "rozhodla",
    "projednala",
    "konstatuje",
    "potvrzuje",
    "navrhuje",
    "nominuje",
]

ACTION_RE = re.compile(
    r"\b(" + "|".join(map(re.escape, ACTION_PHRASES)) + r")\b",
    re.IGNORECASE
)

ACTION_NORMALIZATION = {
    "rozhodla": "rozhoduje",
    "byla seznámena": "bere na vědomí",
    "projednala": "projednává",
}

REF_RE = re.compile(r"RM/\d+/\d+/\d+")
AMOUNT_RE = re.compile(r"\d[\d\s]*\s*Kč")

TAIL_LINE_RE = re.compile(r"\n(?=[a-záčďéěíňóřšťúůýž])")


# ============================================================
# HELPERY
# ============================================================

def normalize_action(a):
    if not a:
        return None
    return ACTION_NORMALIZATION.get(a.lower(), a.lower())


def normalize_amount_text(text):
    """
    Spojí rozdělené částky typu:
    '2.\n000 Kč' → '2.000 Kč'
    """
    # spojení čísla + tečky + zalomení + čísla
    text = re.sub(r"(\d)\.\s*\n\s*(\d{3})\s*Kč", r"\1.\2 Kč", text)

    # případ bez tečky: '2\n000 Kč'
    text = re.sub(r"(\d)\s*\n\s*(\d{3})\s*Kč", r"\1\2 Kč", text)

    return text


def split_header(text):
    text = text.lstrip()
    header = "Rada města Litovel"
    if text.startswith(header):
        return header, text[len(header):].lstrip(" ,\n")
    return None, text


def split_head_items(text):
    m = ITEM_RE.search(text)
    if not m:
        return text.strip(), []

    head = text[:m.start()].strip()
    rest = text[m.start():]

    items = []
    matches = list(ITEM_RE.finditer(rest))
    for i, im in enumerate(matches):
        start = im.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(rest)
        items.append({
            "label": im.group(1),
            "text": rest[start:end].strip()
        })

    return head, items


def extract_action(text):
    if not text:
        return None
    m = ACTION_RE.search(text.lower())
    return normalize_action(m.group(1)) if m else None


def extract_action_and_subject(head):
    h = head.strip()
    if h.lower().startswith("rada města litovel"):
        h = h[len("rada města litovel"):].lstrip(" ,")

    m = ACTION_RE.search(h.lower())
    if not m:
        return None, h.rstrip(":") or None

    action = normalize_action(m.group(1))
    subject = h[m.end():].strip().rstrip(":") or None
    return action, subject


def extract_refs(text):
    return sorted(set(REF_RE.findall(text)))


def extract_amounts(text):
    return sorted(set(AMOUNT_RE.findall(text)))


def split_tail_from_last_item(items):
    if not items:
        return items, None

    last = items[-1]
    txt = last["text"]

    m = TAIL_LINE_RE.search(txt)
    if not m:
        return items, None

    head = txt[:m.start()].strip()
    tail = txt[m.start():].strip()

    # bezpečnostní brzda
    if len(head.split()) < 3:
        return items, None

    last["text"] = head
    return items, tail


# ============================================================
# CORE
# ============================================================

def process_usneseni(raw):
    organ, body = split_header(raw["text_raw"])
    head, items = split_head_items(body)

    # zjisti, zda položky nesou vlastní rozhodnutí
    item_actions = [extract_action(it["text"]) for it in items]
    has_local_actions = any(item_actions)

    refs = set()
    amounts = set()
    actions = set()

    # ========================================================
    # TYP B: sekvence rozhodnutí (a) revokuje, b) schvaluje…
    # ========================================================
    if has_local_actions:
        for it, act in zip(items, item_actions):
            if act:
                actions.add(act)

            refs.update(extract_refs(it["text"]))
            amounts.update(extract_amounts(it["text"]))

        return {
            "id": raw["id"],
            "organ": organ,
            "actions": sorted(actions),
            "subject": None,
            "items": items,
            "tail": None,
            "references_out": sorted(refs),
            "amounts": sorted(amounts)
        }

    # ========================================================
    # TYP A: globální akce + výčet předmětu
    # ========================================================
    action, subject = extract_action_and_subject(head)
    if action:
        actions.add(action)

    items, tail = split_tail_from_last_item(items)

    for it in items:
        refs.update(extract_refs(it["text"]))
        amounts.update(extract_amounts(it["text"]))

    if tail:
        refs.update(extract_refs(tail))
        amounts.update(extract_amounts(tail))

    return {
        "id": raw["id"],
        "organ": organ,
        "actions": sorted(actions),
        "subject": subject,
        "items": items,
        "tail": tail,
        "references_out": sorted(refs),
        "amounts": sorted(amounts)
    }


# ============================================================
# MAIN
# ============================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", "--input", type=Path, required=True)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)

    stats = Counter()
    action_counter = Counter()

    for p in sorted(args.input.glob("*.json")):
        raw = json.loads(p.read_text(encoding="utf-8"))

        if not ID_RE.match(raw.get("id", "")):
            if args.verbose:
                print(f"⚠️  Neplatné ID: {p.name}")
            continue

        parsed = process_usneseni(raw)
        stats["total"] += 1

        for a in parsed["actions"]:
            action_counter[a] += 1

        if not parsed["actions"]:
            stats["missing_action"] += 1

        (args.output / p.name).write_text(
            json.dumps(parsed, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    print("\n=== STATISTIKY ===")
    for k, v in stats.items():
        print(f"{k:20}: {v}")

    print("\n=== AKCE ===")
    for a, c in action_counter.most_common():
        print(f"{a:20}: {c}")

    print("\nHotovo ✔")


if __name__ == "__main__":
    main()
