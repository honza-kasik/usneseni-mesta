#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Phase 3 - resolvování referencí.

Usnesení mohou odkazovat jedno na druhé. V této fázi se resolvují reference
  - imlicitní: Uváděné v textu rozhodnutí pouze jako ID_ROZHODNUTI/CISLO_SCHUZE, například 1853/60 je resolvováno na RM/1853/60/2025
  - explicitní: Už hotová reference ve tvaru RM/1853/60/2025

Resolvované reference se vloží do nového klíče references_in a odkaz je tak oboustranný.

Na závěr jsou do konzole vytištěné statistiky.

Vstup:
  - adresář s JSON soubory ve struktuře z phase 2

Výstup:
  - jeden JSON soubor = jedno usnesení

Použití:
  python phase3_resolve_references.py --input phase2_dir/ --output phase3_dir/
"""

import json
import argparse
from pathlib import Path
from collections import defaultdict, Counter
import re


ID_RE = re.compile(r"^(RM|ZM)/(\d+)/(\d+)/(\d+)$")

def parse_id(id_str):
    """
    RM/1962/65/2025 -> (1962, 65, 2025)
    """
    m = ID_RE.match(id_str)
    if not m:
        return None

    _, num, schuze, rok = m.groups()
    return int(num), int(schuze), int(rok)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", "--input", type=Path, required=True)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)

    # ======================================================
    # 1️⃣ Načtení všech usnesení
    # ======================================================

    usneseni = []
    by_key = defaultdict(list)  # (num, schuze) -> [ (rok, id) ]

    for p in sorted(args.input.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        parsed = parse_id(data["id"])
        if not parsed:
            continue

        num, schuze, rok = parsed
        usneseni.append(data)
        by_key[(num, schuze)].append((rok, data["id"]))

    # seřaď kandidáty podle roku (vzestupně)
    for k in by_key:
        by_key[k].sort()

    if args.verbose:
        print(f"Načteno usnesení: {len(usneseni)}")

    # ======================================================
    # 2️⃣ Rozřešení references_out
    # ======================================================

    refs_index = {}
    unresolved = []
    resolved_count = 0

    for u in usneseni:
        uid = u["id"]
        u["references_in"] = []

        parsed_self = parse_id(uid)
        if not parsed_self:
            continue
        _, _, self_year = parsed_self

        for r in u.get("references_out", []):
            raw = r["raw"]

            # explicitní reference už je hotová
            if r["type"] == "explicit":
                r["resolved"] = raw
                refs_index[(uid, raw)] = raw
                resolved_count += 1
                continue

            # implicitní reference
            try:
                num, schuze = map(int, raw.split("/"))
            except ValueError:
                unresolved.append((uid, raw))
                continue

            candidates = by_key.get((num, schuze), [])
            # vezmi nejbližší předchozí (rok <= aktuální)
            chosen = None
            for rok, cid in reversed(candidates):
                if rok <= self_year:
                    chosen = cid
                    break

            if chosen:
                r["resolved"] = chosen
                refs_index[(uid, raw)] = chosen
                resolved_count += 1
            else:
                unresolved.append((uid, raw))

    # ======================================================
    # 3️⃣ Vytvoření references_in
    # ======================================================

    by_id = {u["id"]: u for u in usneseni}

    for u in usneseni:
        src = u["id"]
        for r in u.get("references_out", []):
            tgt = r.get("resolved")
            if not tgt:
                continue
            if tgt not in by_id:
                continue

            by_id[tgt]["references_in"].append({
                "from": src,
                "action": next(iter(u["actions"]), None)
            })

    # ======================================================
    # 4️⃣ Statistiky
    # ======================================================

    stats = {
        "total_usneseni": len(usneseni),
        "refs_total": sum(len(u.get("references_out", [])) for u in usneseni),
        "refs_resolved": resolved_count,
        "refs_unresolved": len(unresolved),
        "unresolved_refs": unresolved
    }

    # ======================================================
    # 5️⃣ Výstupy
    # ======================================================

    (args.output / "usneseni.json").write_text(
        json.dumps(usneseni, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    (args.output / "refs_index.json").write_text(
        json.dumps(
            {f"{k[0]} -> {k[1]}": v for k, v in refs_index.items()},
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    (args.output / "stats_refs.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print("FÁZE 3 hotová ✔")
    print(f"Usnesení       : {stats['total_usneseni']}")
    print(f"Reference celkem: {stats['refs_total']}")
    print(f"Rozřešeno       : {stats['refs_resolved']}")
    print(f"Nerozřešeno     : {stats['refs_unresolved']}")


if __name__ == "__main__":
    main()
