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
        self.assertIn('<p class="usn-rz-title">přijaté pojistné plnění</p>', text)
        self.assertIn('<p>Důvod rozpočtové změny.</p>', text)
        self.assertIn('Navýšení příjmů</span> <strong class="usn-amount usn-amount-positive">+3 645,00 Kč</strong>', text)
        self.assertIn('Snížení příjmů</span> <strong class="usn-amount usn-amount-negative">-3 645,00 Kč</strong>', text)
        self.assertIn('Přesun v rámci příjmů bez změny celku', text)
        self.assertIn('přijaté pojistné plnění</p>', text)
        self.assertNotIn('přijaté pojistné plnění (RZ 53/2026/RM)</p>', text)
        self.assertIn('<summary>Kódy: POL 6320, ORG 2322</summary>', text)

    def test_write_ro_page_uses_row_description_when_note_missing(self):
        opatreni = {
            "id": "RO/1/2026",
            "approval_date": "2026-01-29",
            "approved_by": "Radou města Litovel",
            "meeting": {"number": 67, "type": "schůzi", "date": "2026-01-29"},
            "budget_change_ids": ["42/2026/RM"],
            "resolution_links": [],
            "sections": [
                {
                    "type": "vydaje",
                    "rows": [
                        {
                            "budget_change_id": "42/2026/RM",
                            "raw_codes": ["3392", "5137"],
                            "amount": "120 000,00",
                            "amount_value": 120000.0,
                            "description": "Unčovice - židle a stoly pro KD (RZ 42/2026/RM)",
                        },
                    ],
                },
            ],
            "notes": [],
        }

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            write_ro_page(opatreni, output)
            text = (output / "rozpoctova-opatreni" / "RO-1-2026" / "index.html").read_text(encoding="utf-8")

        self.assertIn('<p class="usn-rz-title">Unčovice - židle a stoly pro KD</p>', text)
        self.assertIn('Navýšení výdajů</span> <strong class="usn-amount usn-amount-positive">+120 000,00 Kč</strong>', text)

    def test_write_ro_page_prefers_note_title_for_mixed_row_bundle(self):
        opatreni = {
            "id": "RO/5/2026",
            "approval_date": "2026-03-05",
            "approved_by": "Zastupitelstvem města Litovel",
            "meeting": {"number": 25, "type": "zasedání", "date": "2026-03-05"},
            "budget_change_ids": ["42/2026/ZM"],
            "resolution_links": [],
            "sections": [
                {
                    "type": "prijmy",
                    "rows": [
                        {
                            "budget_change_id": "42/2026/ZM",
                            "raw_codes": ["231", "3111", "2229", "48"],
                            "amount": "101 706,00",
                            "amount_value": 101706.0,
                            "description": "MŠ Gemerská - ostatní přijaté vratky transferů a podobné příjmy (RZ 42/2026/ZM)",
                        },
                        {
                            "budget_change_id": "42/2026/ZM",
                            "raw_codes": ["231", "3113", "2229", "46"],
                            "amount": "45 019,82",
                            "amount_value": 45019.82,
                            "description": "ZŠ Jungmannova - ostatní přijaté vratky transferů a podobné příjmy (RZ 42/2026/ZM)",
                        },
                        {
                            "budget_change_id": "42/2026/ZM",
                            "raw_codes": ["231", "6320", "2322", "0"],
                            "amount": "262 537,00",
                            "amount_value": 262537.0,
                            "description": "přijaté pojistné plnění - povodeň 2024 (RZ 42/2026/ZM)",
                        },
                    ],
                },
            ],
            "notes": [
                {
                    "title": "Rozpočtová změna č. 42/2026/ZM",
                    "text": (
                        "V průběhu ledna a února obdrželo město Litovel na svůj účet od příspěvkových organizací "
                        "vratky nevyčerpaných provozních příspěvků na spotřebu energií za rok 2025, také pojistné "
                        "plnění a neinvestiční přijaté transfery od obcí."
                    ),
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            write_ro_page(opatreni, output)
            text = (output / "rozpoctova-opatreni" / "RO-5-2026" / "index.html").read_text(encoding="utf-8")

        self.assertIn(
            "<p class=\"usn-rz-title\">Od příspěvkových organizací vratky nevyčerpaných provozních příspěvků na spotřebu energií za rok 2025, také pojistné plnění a neinvestiční přijaté transfery od obcí</p>",
            text,
        )
        self.assertNotIn('<p class="usn-rz-title">MŠ Gemerská - ostatní přijaté vratky transferů a podobné příjmy</p>', text)
        self.assertIn('Navýšení příjmů</span> <strong class="usn-amount usn-amount-positive">+409 262,82 Kč</strong>', text)

    def test_write_ro_page_shows_reallocation_as_increase_and_decrease(self):
        opatreni = {
            "id": "RO/2/2026",
            "approval_date": "2026-02-12",
            "approved_by": "Radou města Litovel",
            "meeting": {"number": 68, "type": "schůzi", "date": "2026-02-12"},
            "budget_change_ids": ["12/2026/RM"],
            "resolution_links": [],
            "sections": [
                {
                    "type": "vydaje",
                    "rows": [
                        {
                            "budget_change_id": "12/2026/RM",
                            "raw_codes": ["3392", "5169"],
                            "amount": "300 000,00",
                            "amount_value": 300000.0,
                            "description": "Kulturní dům - služby (RZ 12/2026/RM)",
                        },
                        {
                            "budget_change_id": "12/2026/RM",
                            "raw_codes": ["3392", "5171"],
                            "amount": "-300 000,00",
                            "amount_value": -300000.0,
                            "description": "Kulturní dům - opravy (RZ 12/2026/RM)",
                        },
                    ],
                },
            ],
            "notes": [
                {
                    "title": "Rozpočtová změna č. 12/2026/RM",
                    "text": "Přesun mezi výdajovými položkami kulturního domu.",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            write_ro_page(opatreni, output)
            text = (output / "rozpoctova-opatreni" / "RO-2-2026" / "index.html").read_text(encoding="utf-8")

        self.assertIn('Navýšení výdajů</span> <strong class="usn-amount usn-amount-positive">+300 000,00 Kč</strong>', text)
        self.assertIn('Snížení výdajů</span> <strong class="usn-amount usn-amount-negative">-300 000,00 Kč</strong>', text)
        self.assertIn('Přesun v rámci výdajů bez změny celku', text)

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
