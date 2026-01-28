#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Parsování PDF s usneseními Rady města Litovel.

Vstup:
  - jeden PDF soubor
  - NEBO složka s PDF soubory

Výstup:
  - jeden JSON soubor = jedno usnesení

Použití:
  python parse_rm_pdf.py input.pdf output_dir/
  python parse_rm_pdf.py pdf_dir/ output_dir/
"""

import pdfplumber
import re
import json
import sys
from pathlib import Path


# ---------- REGEXY ----------

USNESENI_SPLIT_RE = re.compile(
    r"\n(?=Číslo:\s+RM/\d+/\d+/\d+)"
)

ID_RE = re.compile(
    r"Číslo:\s+(RM/\d+/\d+/\d+)"
)

DATE_PATTERNS = [
    r"konané dne\s+(\d{1,2}\.\s*[^\d]+\s+\d{4})",
    r"ze dne\s+(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})",
]


# ---------- MAPA MĚSÍCŮ ----------

MONTHS = {
    "ledna": "01",
    "února": "02",
    "března": "03",
    "dubna": "04",
    "května": "05",
    "června": "06",
    "července": "07",
    "srpna": "08",
    "září": "09",
    "října": "10",
    "listopadu": "11",
    "prosince": "12",
}


# ---------- PDF → TEXT ----------

def pdf_to_text(path: Path) -> str:
    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n".join(pages)


# ---------- NORMALIZACE ----------

def normalize_text(text: str) -> str:
    text = re.sub(r"Stránka\s+\d+\s+z\s+\d+", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


# ---------- DATUM ----------

def parse_cz_date(text: str):
    for pattern in DATE_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            continue

        raw = m.group(1).lower().replace(" ", "")
        
        # formát: 31.8.2023
        if re.match(r"\d{1,2}\.\d{1,2}\.\d{4}", raw):
            d, mth, y = raw.split(".")
            return f"{y}-{mth.zfill(2)}-{d.zfill(2)}"

        # formát: 27.října 2022
        parts = raw.replace(".", "").split()
        if len(parts) == 3 and parts[1] in MONTHS:
            day = parts[0].zfill(2)
            month = MONTHS[parts[1]]
            year = parts[2]
            return f"{year}-{month}-{day}"

    return None


# ---------- SPLIT USNESENÍ ----------

def split_usneseni(text: str):
    chunks = USNESENI_SPLIT_RE.split(text)
    return [c.strip() for c in chunks if c.strip()]


# ---------- PARSE JEDNOHO USNESENÍ ----------

def parse_usneseni(block: str, datum: str):
    m = ID_RE.search(block)
    if not m:
        return None

    uid = m.group(1)
    body = block[m.end():].strip()

    return {
        "id": uid,
        "datum": datum,
        "organ": "Rada města Litovel",
        "text_raw": body
    }


# ---------- ULOŽENÍ ----------

def save_usneseni(usn: dict, out_dir: Path):
    filename = usn["id"].replace("/", "-") + ".json"
    path = out_dir / filename

    with path.open("w", encoding="utf-8") as f:
        json.dump(usn, f, ensure_ascii=False, indent=2)


# ---------- ZPRACOVÁNÍ JEDNOHO PDF ----------

def process_pdf(pdf_path: Path, out_dir: Path, failures: list):
    print(f"📄 {pdf_path}")

    raw_text = pdf_to_text(pdf_path)
    clean_text = normalize_text(raw_text)

    datum = parse_cz_date(clean_text)
    if not datum:
        print("   ❌ nenalezeno datum")
        failures.append((pdf_path, "chybí datum"))
        return 0

    blocks = split_usneseni(clean_text)
    if not blocks:
        print("   ❌ žádná usnesení")
        failures.append((pdf_path, "žádná usnesení"))
        return 0

    count = 0
    for block in blocks:
        usn = parse_usneseni(block, datum)
        if not usn:
            continue
        save_usneseni(usn, out_dir)
        count += 1

    print(f"   → {count} usnesení ({datum})")
    return count

# ---------- MAIN ----------

def main():
    if len(sys.argv) != 3:
        print("Použití:")
        print("  python parse_rm_pdf.py input.pdf output_dir/")
        print("  python parse_rm_pdf.py pdf_dir/ output_dir/")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    failures = []

    total = 0

    if input_path.is_file() and input_path.suffix.lower() == ".pdf":
        total += process_pdf(input_path, out_dir, failures)

    elif input_path.is_dir():
        pdfs = sorted(input_path.glob("*.pdf"))
        if not pdfs:
            print("⚠️  Ve složce nejsou žádné PDF soubory")
            sys.exit(1)

        for pdf in pdfs:
            total += process_pdf(pdf, out_dir, failures)

    else:
        print("❌ Vstup musí být PDF soubor nebo složka s PDF")
        sys.exit(1)

    print(f"\n✅ Hotovo: celkem {total} usnesení")

    if failures:
        print("\n⚠️  SOUBORY, KTERÉ SE NEPODAŘILO ZPRACOVAT:")
        for path, reason in failures:
            print(f" - {path} ({reason})")
    else:
        print("\n🎉 Všechny PDF soubory zpracovány úspěšně")

if __name__ == "__main__":
    main()
