import tempfile
import unittest
from pathlib import Path

from phase5_static_export import (
    group_opatreni_by_approval_year,
    render_budget_links_section,
    ro_slug_from_id,
    rz_anchor,
    write_year_index,
    write_ro_page,
)
from parse_rozpoctova_opatreni import normalize_financing_sections


class StaticExportRozpoctovaOpatreniTest(unittest.TestCase):
    def test_ro_slug_and_rz_anchor(self):
        self.assertEqual(ro_slug_from_id("RO/6/2026"), "RO-6-2026")
        self.assertEqual(rz_anchor("53/2026/RM"), "rz-53-2026-rm")

    def test_resolution_budget_links_point_to_ro_and_rz_anchor(self):
        html = render_budget_links_section({
            "budget_opatreni_approved": [
                {"opatreni_id": "RO/6/2026", "source": "ro_header"},
            ],
            "budget_change_links": [
                {
                    "budget_change_id": "53/2026/RM",
                    "opatreni_id": "RO/6/2026",
                    "source": "text",
                    "match": "range",
                },
            ],
        })

        self.assertIn('/rozpoctova-opatreni/RO-6-2026/', html)
        self.assertIn('/rozpoctova-opatreni/RO-6-2026/#rz-53-2026-rm', html)
        self.assertIn('Odkazováno z rozpočtového opatření', html)

    def test_write_ro_page_contains_rz_anchor_and_resolution_link(self):
        opatreni = {
            "id": "RO/6/2026",
            "approval_date": "2026-03-12",
            "approved_by": "Radou města Litovel",
            "meeting": {"number": 69, "type": "schůzi", "date": "2026-03-12"},
            "budget_change_ids": ["53/2026/RM"],
            "resolution_links": [
                {
                    "resolution_id": "RM/2161/69/2026",
                    "relation": "approves_opatreni",
                    "source": "ro_header",
                },
                {
                    "resolution_id": "RM/2161/69/2026",
                    "relation": "mentions_budget_change",
                    "budget_change_ids": ["53/2026/RM"],
                },
            ],
            "sections": [
                {
                    "type": "prijmy",
                    "rows": [
                        {
                            "budget_change_id": "53/2026/RM",
                            "raw_codes": ["6320", "2322"],
                            "amount": "3 645,00",
                            "amount_value": 3645.0,
                            "description": "přijaté pojistné plnění (RZ 53/2026/RM)",
                        },
                        {
                            "budget_change_id": "53/2026/RM",
                            "raw_codes": ["6320", "5362"],
                            "amount": "-3 645,00",
                            "amount_value": -3645.0,
                            "description": "převod mezi položkami (RZ 53/2026/RM)",
                        },
                    ],
                },
            ],
            "notes": [
                {
                    "title": "Rozpočtová změna č. 53/2026/RM",
                    "text": "Důvod rozpočtové změny.",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            permalink = write_ro_page(opatreni, output)
            page = output / "rozpoctova-opatreni" / "RO-6-2026" / "index.html"
            text = page.read_text(encoding="utf-8")

        self.assertEqual(permalink, "/rozpoctova-opatreni/RO-6-2026/")
        self.assertIn('id="rz-53-2026-rm"', text)
        self.assertIn('/usneseni/2026/RM-2161-69-2026/', text)
        self.assertIn('organ: "Rada města Litovel"', text)
        self.assertIn('<dt>Orgán</dt><dd>Rada města Litovel</dd>', text)
        self.assertEqual(text.count('id="rz-53-2026-rm"'), 1)
        self.assertEqual(text.count('Rozpočtová změna 53/2026/RM'), 1)
        self.assertIn('class="usn-rz-note"', text)
        self.assertNotIn('Rozpočtová změna č. 53/2026/RM</strong>', text)
        self.assertIn('přijaté pojistné plnění</p>', text)
        self.assertNotIn('přijaté pojistné plnění (RZ 53/2026/RM)</p>', text)
        self.assertIn('<summary>Kódy: POL 6320, ORG 2322</summary>', text)

    def test_financing_section_is_inferred_from_8xxx_codes(self):
        sections = normalize_financing_sections([
            {
                "type": "vydaje",
                "label": "Změny ve výdajích",
                "rows": [
                    {
                        "budget_change_id": "74/2026/RM",
                        "raw_codes": ["8115"],
                    }
                ],
            }
        ])

        self.assertEqual(sections[0]["type"], "financovani")
        self.assertEqual(sections[0]["label"], "Změny ve financování")

    def test_opatreni_are_grouped_by_approval_year(self):
        grouped = group_opatreni_by_approval_year([
            {"id": "RO/25/2025", "approval_date": "2026-01-29"},
            {"id": "RO/1/2026", "approval_date": "2025-12-11"},
        ])

        self.assertEqual([item["id"] for item in grouped["2026"]], ["RO/25/2025"])
        self.assertEqual([item["id"] for item in grouped["2025"]], ["RO/1/2026"])

    def test_year_index_contains_ro_after_meetings(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            write_year_index(
                "2026",
                [("RM/1/1/2026", "/usneseni/2026/RM-1-1-2026/")],
                [("RM-1", "/usneseni/2026/RM-1/", "2026-01-10")],
                output,
                [
                    {
                        "id": "RO/25/2025",
                        "number": 25,
                        "year": 2025,
                        "approval_date": "2026-01-29",
                        "organ": "RM",
                        "budget_change_ids": ["1/2026/RM", "2/2026/RM"],
                    },
                ],
            )
            text = (output / "usneseni" / "2026" / "index.html").read_text(encoding="utf-8")

        self.assertIn('<a href="/rozpoctova-opatreni/RO-25-2025/">RO-25-2025 <span class="usn-date">(29. 1.)</span></a>', text)
        self.assertIn('<a href="/rozpoctova-opatreni/">Všechna rozpočtová opatření</a>', text)
        self.assertLess(text.index("<h2>Schůze</h2>"), text.index("<h2>Rozpočtová opatření</h2>"))
        self.assertLess(text.index("<h2>Rozpočtová opatření</h2>"), text.index("<h2>Poslední usnesení</h2>"))


if __name__ == "__main__":
    unittest.main()
