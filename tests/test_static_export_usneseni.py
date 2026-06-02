import tempfile
import unittest
from pathlib import Path

from static_export.usneseni import write_meeting_index, write_resolution


class StaticExportUsneseniTest(unittest.TestCase):
    def test_write_resolution_includes_term_frontmatter(self):
        resolution = {
            "id": "RM/1/1/2026",
            "datum": "2026-10-29",
            "organ": "Rada města Litovel",
            "actions": ["schvaluje"],
            "subject": "program schůze",
            "items": [],
            "references_out": [],
            "term_id": "2026-2030",
            "term_label": "Volební období 2026-2030",
        }

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            write_resolution(resolution, output, {}, {})
            page = output / "usneseni" / "2026" / "RM-1-1-2026" / "index.html"
            text = page.read_text(encoding="utf-8")

        self.assertIn('term_id: "2026-2030"', text)
        self.assertIn('term_label: "Volební období 2026-2030"', text)

    def test_write_meeting_index_includes_term_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            write_meeting_index(
                "2026",
                "RM",
                "1",
                [("RM/1/1/2026", "/usneseni/2026/RM-1-1-2026/", "program schůze", ["schvaluje"])],
                {
                    "organ": "Rada města Litovel",
                    "datum": "2026-10-29",
                    "term_id": "2026-2030",
                    "term_label": "Volební období 2026-2030",
                },
                output,
            )
            page = output / "usneseni" / "2026" / "RM-1" / "index.html"
            text = page.read_text(encoding="utf-8")

        self.assertIn('term_id: "2026-2030"', text)
        self.assertIn("2026-10-29 • Volební období 2026-2030 • 1 usnesení", text)


if __name__ == "__main__":
    unittest.main()
