import json
import tempfile
import unittest
from pathlib import Path

from tools.archive_build_search_index import build_payload
from tools.archive_promote_current import promote_roots


MODERN_ARCHIVE_TEXT = """
Výpis usnesení ze zasedání konané dne 15. září 2022
Číslo: ZM/1/34/2022
Zastupitelstvo města Litovel schvaluje ověřovatele zápisu.
Číslo: ZM/2/34/2022
Zastupitelstvo města Litovel bere na vědomí kontrolu usnesení.
"""


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def archive_record(record_id="ZM-archive-2022-34-usneseni") -> dict:
    return {
        "id": record_id,
        "type": "archive_document",
        "kind": "usneseni",
        "org": "ZM",
        "organ": "Zastupitelstvo města Litovel",
        "title": "Usnesení z 34. zasedání zastupitelstva města",
        "date": "2022-09-15",
        "year": 2022,
        "meeting_no": 34,
        "source_url": "https://www.litovel.eu/archive",
        "original_file_url": "https://www.litovel.eu/filemanager/files/2344691.pdf",
        "file_type": "pdf",
        "extraction_method": "pdf_text",
        "text_quality": {"quality_flag": "text_ok"},
        "search_text": MODERN_ARCHIVE_TEXT,
        "display_text": MODERN_ARCHIVE_TEXT,
    }


class ArchivePromoteCurrentTest(unittest.TestCase):
    def test_promotes_modern_archive_text_to_phase1_records_with_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive_root = root / "archive_zm"
            output = root / "phase1"
            text_path = archive_root / "text" / "ZM-archive-2022-34-usneseni.txt"
            text_path.parent.mkdir(parents=True)
            text_path.write_text(MODERN_ARCHIVE_TEXT, encoding="utf-8")
            write_json(archive_root / "archive_documents.json", [archive_record()])
            write_json(
                archive_root / "extraction.json",
                {
                    "ZM-archive-2022-34-usneseni": {
                        "text_path": str(text_path),
                        "quality_flag": "text_ok",
                    }
                },
            )
            write_json(
                archive_root / "inventory.json",
                [
                    {
                        "id": "ZM-archive-2022-34-usneseni",
                        "local_path": "work/archive_zm/files/ZM-archive-2022-34-usneseni.pdf",
                    }
                ],
            )

            report = promote_roots([archive_root], output)

            self.assertEqual(report["promoted_documents"], 1)
            self.assertEqual(report["promoted_resolutions"], 2)
            promoted = json.loads((output / "ZM-1-34-2022.json").read_text(encoding="utf-8"))
            self.assertEqual(promoted["id"], "ZM/1/34/2022")
            self.assertEqual(promoted["datum"], "2022-09-15")
            self.assertEqual(promoted["source"], "archive")
            self.assertEqual(promoted["archive_document_id"], "ZM-archive-2022-34-usneseni")
            self.assertEqual(promoted["source_pdf"], "work/archive_zm/files/ZM-archive-2022-34-usneseni.pdf")

    def test_current_phase1_record_wins_id_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive_root = root / "archive_zm"
            output = root / "phase1"
            output.mkdir(parents=True)
            (output / "ZM-1-34-2022.json").write_text(
                json.dumps({"id": "ZM/1/34/2022"}, ensure_ascii=False),
                encoding="utf-8",
            )
            write_json(archive_root / "archive_documents.json", [archive_record()])
            write_json(archive_root / "extraction.json", {})

            report = promote_roots([archive_root], output)

            self.assertEqual(report["promoted_resolutions"], 1)
            self.assertEqual(json.loads((output / "ZM-1-34-2022.json").read_text(encoding="utf-8")), {"id": "ZM/1/34/2022"})
            self.assertIn("ZM/2/34/2022", report["promoted_resolution_ids"])

    def test_archive_payload_excludes_promoted_document_and_children(self):
        parent = archive_record()
        child = {
            "id": "ZM-archive-2022-34-usneseni-resolution-001-1",
            "type": "archive_resolution",
            "kind": "usneseni",
            "parent_document_id": "ZM-archive-2022-34-usneseni",
            "org": "ZM",
            "organ": "Zastupitelstvo města Litovel",
            "title": "Archivní usnesení",
            "date": "2022-09-15",
            "year": 2022,
            "meeting_no": 34,
            "search_text": "1. Schvaluje opravu chodníku.",
            "display_text": "1. Schvaluje opravu chodníku.",
        }

        by_year, report = build_payload([parent], [child], {"ZM-archive-2022-34-usneseni"})

        self.assertEqual(by_year, {})
        self.assertEqual(report["indexed"], 0)
        self.assertEqual(report["skipped_promoted_documents"], 1)


if __name__ == "__main__":
    unittest.main()
