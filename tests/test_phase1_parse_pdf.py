import unittest

from phase1_parse_pdf import parse_text


class Phase1ParsePdfTest(unittest.TestCase):
    def test_parse_text_ignores_rejected_zm_proposals_section(self):
        text = """
Město Litovel
Usnesení
z 26. zasedání Zastupitelstva města Litovel ze dne 4. 6. 2026
Číslo: ZM/25/26/2026
Zastupitelstvo města Litovel deleguje jako zástupce města na valnou hromadu.
Číslo: ZM/26/26/2026
Zastupitelstvo města Litovel stahuje bod navržený A. H. z programu jednání.
NÁVRHY, KTERÉ NEBYLY PŘIJATY:
Zastupitelstvo města Litovel schvaluje předložený záměr prodeje části pozemku.
"""

        records, error = parse_text(text)

        self.assertIsNone(error)
        self.assertEqual([record["id"] for record in records], ["ZM/25/26/2026", "ZM/26/26/2026"])
        self.assertEqual(
            records[-1]["text_raw"],
            "Zastupitelstvo města Litovel stahuje bod navržený A. H. z programu jednání.",
        )


if __name__ == "__main__":
    unittest.main()
