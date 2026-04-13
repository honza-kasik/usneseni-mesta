#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Pipeline – spustí všechny fáze zpracování usnesení za sebou.

Výchozí adresářová struktura (lze přepsat argumenty):
  pdf_dir/          ← vstupní PDF soubory (povinné)
  work/phase1/      ← výstup fáze 1
  work/phase2/      ← výstup fáze 2
  work/phase3/      ← výstup fáze 3
  work/phase4/      ← výstup fáze 4
  export/           ← výstup fáze 5 (statický export)

Použití:
  # Celý pipeline od začátku
  python pipeline.py --pdf pdf_dir/

  # Přeskočit fáze 1–2 a pokračovat od fáze 3
  python pipeline.py --pdf pdf_dir/ --from-phase 3

  # Spustit pouze fáze 2 a 3
  python pipeline.py --pdf pdf_dir/ --from-phase 2 --to-phase 3

  # Vlastní pracovní adresář
  python pipeline.py --pdf pdf_dir/ --workdir moje_data/ --export vystup/
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path


# ──────────────────────────────────────────────
# Barvy pro terminál (degradují na prázdné stringy pokud není TTY)
# ──────────────────────────────────────────────

def _supports_color():
    import os
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty() and os.name != "nt"

if _supports_color():
    BOLD  = "\033[1m"
    GREEN = "\033[32m"
    RED   = "\033[31m"
    CYAN  = "\033[36m"
    DIM   = "\033[2m"
    RESET = "\033[0m"
else:
    BOLD = GREEN = RED = CYAN = DIM = RESET = ""


# ──────────────────────────────────────────────
# Pomocné funkce
# ──────────────────────────────────────────────

def header(text: str):
    print(f"\n{BOLD}{CYAN}{'─' * 60}{RESET}")
    print(f"{BOLD}{CYAN}{text}{RESET}")
    print(f"{BOLD}{CYAN}{'─' * 60}{RESET}")


def success(text: str):
    print(f"{GREEN}✔  {text}{RESET}")


def failure(text: str):
    print(f"{RED}✖  {text}{RESET}")


def info(text: str):
    print(f"{DIM}   {text}{RESET}")


def run_phase(name: str, cmd: list[str]) -> bool:
    """Spustí příkaz a vrátí True při úspěchu."""
    info(f"Příkaz: {' '.join(str(c) for c in cmd)}")
    t0 = time.monotonic()
    result = subprocess.run(cmd, text=True)
    elapsed = time.monotonic() - t0

    if result.returncode == 0:
        success(f"{name} dokončena za {elapsed:.1f} s")
        return True
    else:
        failure(f"{name} selhala (kód {result.returncode})")
        return False


def collect_pdf_dirs(root: Path) -> list[Path]:
    """
    Rekurzivně projde root a vrátí seznam adresářů, které přímo obsahují
    alespoň jeden *.pdf soubor. Zahrnuje i samotný root.
    """
    dirs = []
    for d in sorted(root.rglob("*")):
        if d.is_dir() and any(d.glob("*.pdf")):
            dirs.append(d)
    # také root sám, pokud obsahuje PDF přímo
    if any(root.glob("*.pdf")) and root not in dirs:
        dirs.insert(0, root)
    return dirs


def run_phase1_recursive(pdf_dir: Path, phase1: Path, dry_run: bool) -> bool:
    """
    Spustí phase1_parse_pdf.py pro každý podadresář (i root), který obsahuje PDF.
    Všechny výstupy jdou do stejného phase1/ adresáře.
    """
    dirs = collect_pdf_dirs(pdf_dir)

    if not dirs:
        failure(f"Žádné PDF soubory nenalezeny v {pdf_dir} ani jejích podadresářích")
        return False

    info(f"Nalezeno {len(dirs)} adresář(ů) s PDF soubory")
    phase1.mkdir(parents=True, exist_ok=True)

    t0 = time.monotonic()
    for d in dirs:
        count = len(list(d.glob("*.pdf")))
        info(f"  {d}  ({count} PDF)")
        cmd = [sys.executable, "phase1_parse_pdf.py", str(d), str(phase1)]
        if dry_run:
            info("DRY RUN: " + " ".join(str(c) for c in cmd))
            continue
        result = subprocess.run(cmd, text=True)
        if result.returncode != 0:
            failure(f"Fáze 1 selhala pro adresář: {d}")
            return False

    elapsed = time.monotonic() - t0
    if not dry_run:
        success(f"Fáze 1 – parsování PDF dokončeno za {elapsed:.1f} s")
    return True


# ──────────────────────────────────────────────
# Definice fází
# ──────────────────────────────────────────────

def build_phases(pdf_dir: Path, workdir: Path, export_dir: Path) -> list[dict]:
    """
    Vrátí seznam fází. Každá fáze je slovník:
      number  – číslo fáze (int)
      name    – popis
      cmd     – callable(dirs) -> list[str|Path]
      check   – callable(dirs) -> bool  (ověří, zda výstup existuje)
    """

    phase1 = workdir / "phase1"
    phase2 = workdir / "phase2"
    phase3 = workdir / "phase3"
    phase4 = workdir / "phase4"

    return [
        {
            "number": 1,
            "name": "Fáze 1 – parsování PDF (rekurzivní)",
            "recursive_phase1": True,
            "output_check": lambda: phase1.exists() and any(phase1.glob("*.json")),
            "output_hint": str(phase1),
        },
        {
            "number": 2,
            "name": "Fáze 2 – analýza usnesení",
            "cmd": lambda: [
                sys.executable, "phase2_resolution_analysis.py",
                "--input", str(phase1),
                "--output", str(phase2),
            ],
            "output_check": lambda: phase2.exists() and any(phase2.glob("*.json")),
            "output_hint": str(phase2),
        },
        {
            "number": 3,
            "name": "Fáze 3 – resolvování referencí",
            "cmd": lambda: [
                sys.executable, "phase3_resolve_references.py",
                "--input", str(phase2),
                "--output", str(phase3),
            ],
            "output_check": lambda: (phase3 / "usneseni.json").exists(),
            "output_hint": str(phase3 / "usneseni.json"),
        },
        {
            "number": 4,
            "name": "Fáze 4 – sestavení indexu",
            "cmd": lambda: [
                sys.executable, "phase4_index_build.py",
                "--input", str(phase3 / "usneseni.json"),
                "--output", str(phase4),
            ],
            "output_check": lambda: (phase4 / "meta.json").exists(),
            "output_hint": str(phase4),
        },
        {
            "number": 5,
            "name": "Fáze 5 – statický export",
            "cmd": lambda: [
                sys.executable, "phase5_static_export.py",
                "--input", str(phase3 / "usneseni.json"),
                "--output", str(export_dir),
            ],
            "output_check": lambda: export_dir.exists() and any(export_dir.iterdir()),
            "output_hint": str(export_dir),
        },
    ]


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Pipeline pro zpracování usnesení města Litovel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument(
        "--pdf", type=Path, required=True, metavar="DIR",
        help="Adresář se vstupními PDF soubory"
    )
    ap.add_argument(
        "--workdir", type=Path, default=Path("work"), metavar="DIR",
        help="Pracovní adresář pro meziproduktová data (výchozí: work/)"
    )
    ap.add_argument(
        "--export", type=Path, default=Path("export"), metavar="DIR",
        help="Cílový adresář statického exportu (výchozí: export/)"
    )
    ap.add_argument(
        "--from-phase", type=int, default=1, metavar="N",
        help="Začít od fáze N (výchozí: 1)"
    )
    ap.add_argument(
        "--to-phase", type=int, default=5, metavar="N",
        help="Skončit po fázi N (výchozí: 5)"
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="Pouze zobraz příkazy, nespouštěj je"
    )
    args = ap.parse_args()

    # Validace
    if not args.pdf.exists():
        failure(f"Adresář s PDF neexistuje: {args.pdf}")
        sys.exit(1)

    if not (1 <= args.from_phase <= 5 and 1 <= args.to_phase <= 5):
        failure("--from-phase a --to-phase musí být v rozmezí 1–5")
        sys.exit(1)

    if args.from_phase > args.to_phase:
        failure("--from-phase nesmí být větší než --to-phase")
        sys.exit(1)

    phases = build_phases(args.pdf, args.workdir, args.export)
    selected = [p for p in phases if args.from_phase <= p["number"] <= args.to_phase]

    print(f"\n{BOLD}Pipeline usnesení města Litovel{RESET}")
    print(f"  PDF vstup : {args.pdf}")
    print(f"  Pracovní  : {args.workdir}")
    print(f"  Export    : {args.export}")
    print(f"  Fáze      : {args.from_phase} – {args.to_phase}")
    if args.dry_run:
        print(f"  {RED}DRY RUN – příkazy se nespustí{RESET}")

    t_total = time.monotonic()
    failed_phases = []

    for phase in selected:
        header(phase["name"])

        if phase.get("recursive_phase1"):
            ok = run_phase1_recursive(args.pdf, args.workdir / "phase1", args.dry_run)
        else:
            cmd = phase["cmd"]()
            if args.dry_run:
                info("DRY RUN: " + " ".join(str(c) for c in cmd))
                ok = True
            else:
                ok = run_phase(phase["name"], cmd)

        if not ok:
            failed_phases.append(phase["number"])
            failure(f"Pipeline přerušen na fázi {phase['number']}.")
            sys.exit(1)

        if not args.dry_run:
            if phase["output_check"]():
                info(f"Výstup ověřen: {phase['output_hint']}")
            else:
                failure(f"Výstup nebyl nalezen: {phase['output_hint']}")
                failed_phases.append(phase["number"])
                sys.exit(1)

    elapsed_total = time.monotonic() - t_total

    if args.dry_run:
        print(f"\n{BOLD}Dry run dokončen.{RESET}\n")
    else:
        print(f"\n{BOLD}{GREEN}{'═' * 60}{RESET}")
        print(f"{BOLD}{GREEN}  ✔  Všechny fáze dokončeny za {elapsed_total:.1f} s{RESET}")
        print(f"{BOLD}{GREEN}{'═' * 60}{RESET}\n")


if __name__ == "__main__":
    main()