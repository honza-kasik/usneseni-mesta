import unittest

from election_terms import term_for_date
from phase2_resolution_analysis import extract_refs
from phase3_resolve_references import process_resolutions


def resolution(resolution_id, datum, refs=None, organ="Rada města Litovel"):
    return {
        "id": resolution_id,
        "datum": datum,
        "organ": organ,
        "actions": ["schvaluje"],
        "references_out": refs or [],
    }


class Phase3ResolveReferencesTest(unittest.TestCase):
    def test_implicit_reference_ignores_future_reset_candidate(self):
        records = [
            resolution("RM/1/1/2022", "2022-10-27"),
            resolution(
                "RM/10/1/2022",
                "2022-10-27",
                [{"raw": "1/1", "type": "implicit", "resolved": None}],
            ),
            resolution("RM/1/1/2026", "2026-10-29"),
        ]

        processed, _refs_index, stats = process_resolutions(records, terms=[])
        by_id = {item["id"]: item for item in processed}

        self.assertEqual(stats["refs_resolved"], 1)
        self.assertEqual(
            by_id["RM/10/1/2022"]["references_out"][0]["resolved"],
            "RM/1/1/2022",
        )
        self.assertEqual(
            by_id["RM/1/1/2022"]["references_in"],
            [{"from": "RM/10/1/2022", "action": "schvaluje"}],
        )
        self.assertEqual(by_id["RM/1/1/2026"]["references_in"], [])

    def test_implicit_reference_stays_with_same_body(self):
        records = [
            resolution(
                "RM/2/1/2026",
                "2026-11-05",
                [{"raw": "1/1", "type": "implicit", "resolved": None}],
            ),
            resolution(
                "ZM/1/1/2026",
                "2026-10-29",
                organ="Zastupitelstvo města Litovel",
            ),
        ]

        processed, _refs_index, stats = process_resolutions(records, terms=[])
        by_id = {item["id"]: item for item in processed}

        self.assertEqual(stats["refs_resolved"], 0)
        self.assertEqual(stats["refs_unresolved"], 1)
        self.assertIsNone(by_id["RM/2/1/2026"]["references_out"][0]["resolved"])

    def test_term_for_date_uses_configured_boundaries(self):
        terms = [
            {"id": "old", "label": "Old term", "start": "2022-09-24", "end": "2026-10-10"},
            {"id": "new", "label": "New term", "start": "2026-10-10", "end": None},
        ]

        self.assertEqual(term_for_date("2026-10-09", terms)["id"], "old")
        self.assertEqual(term_for_date("2026-10-10", terms)["id"], "new")

    def test_extract_refs_detects_explicit_zm_references(self):
        refs = extract_refs("navazuje na ZM/6/23/2025 a RM/2139/69/2026")

        self.assertEqual(
            refs,
            [
                {"raw": "ZM/6/23/2025", "type": "explicit", "resolved": "ZM/6/23/2025"},
                {"raw": "RM/2139/69/2026", "type": "explicit", "resolved": "RM/2139/69/2026"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
