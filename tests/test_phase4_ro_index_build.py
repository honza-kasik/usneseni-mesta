import unittest

from phase4_ro_index_build import build_index, opatreni_content_year


class Phase4RozpoctovaOpatreniIndexBuildTest(unittest.TestCase):
    def test_content_year_uses_ro_year_not_approval_year(self):
        self.assertEqual(
            opatreni_content_year({
                "id": "RO/26/2025",
                "year": 2025,
                "approval_date": "2026-02-19",
            }),
            "2025",
        )

    def test_index_contains_ids_resolutions_budget_changes_and_row_text(self):
        index = build_index([
            {
                "id": "RO/26/2025",
                "year": 2025,
                "approval_date": "2026-02-19",
                "approved_by": "Radou města Litovel",
                "organ": "RM",
                "source_resolutions": ["RM/2132/68/2026"],
                "budget_change_ids": ["194/2025/RM"],
                "notes": [
                    {
                        "title": "Rozpočtová změna č. 194/2025/RM",
                        "text": "Vratka části dotace od MMR ČR.",
                    }
                ],
                "sections": [
                    {
                        "type": "prijmy",
                        "label": "Změny v příjmech",
                        "rows": [
                            {
                                "budget_change_id": "194/2025/RM",
                                "raw_codes": ["4216", "149517519", "3 003 557"],
                                "amount": "60 000,00",
                                "description": "Nasobůrky - smíšená stezka pro chodce a cyklisty (RZ 194/2025/RM)",
                            }
                        ],
                    }
                ],
            }
        ])

        for token in ("2025", "2132", "194", "nasoburky", "4216", "149517519", "vratka"):
            self.assertIn("RO/26/2025", index[token])


if __name__ == "__main__":
    unittest.main()
