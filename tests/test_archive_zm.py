import unittest

from tools.archive_crawl_zm import crawl_inventory
from tools.archive_zm_common import parse_title_metadata
from tools.archive_extract_text import text_quality_flag
from tools.archive_report import build_report
from tools.archive_build_search_index import build_index, build_payload, skip_reason
from tools.archive_split_resolutions import split_document, split_records


ARCHIVE_HTML = """
<html>
  <body>
    <article class="clanek_body">
      <h4>VOLEBNÍ OBDOBÍ 2018 - 2022</h4>
      <h3>2022</h3>
      <ul>
        <li>
          <a class="link_soubor" href="https://www.litovel.eu/filemanager/files/2344691.pdf" title="*.pdf, 124 KB"><img></a>
          <a href="https://www.litovel.eu/filemanager/pdf-viewer/html5/flipbook_new.inc.php?app=2065&amp;fileID=2344691">
            Usnesení z 34. zasedání zastupitelstva města z 15. 9. 2022;
          </a>
          <a href="https://www.litovel.eu/filemanager/pdf-viewer/html5/flipbook_new.inc.php?app=2065&amp;fileID=999999">
            Hlasování z 34. zasedání zastupitelstva města z 15. 9. 2022
          </a>
        </li>
      </ul>
      <h4>2003</h4>
      <ul>
        <li>
          <a href="https://www.litovel.eu/filemanager/files/38503.doc" class="link_soubor" title="*.doc, 40 KB">
            Usnesení z 11. zasedání zastupitelstva města ze dne 11. prosince 2003
          </a>
        </li>
      </ul>
    </article>
  </body>
</html>
"""


class ArchiveZmTest(unittest.TestCase):
    def archive_record(
        self,
        record_id="ZM-archive-2022-34-usneseni",
        record_type="archive_document",
        kind="usneseni",
        search_text="Oprava chodníku v Litovli",
        quality_flag="text_ok",
        date="2022-09-15",
        year=2022,
    ):
        return {
            "id": record_id,
            "type": record_type,
            "legacy": True,
            "org": "ZM",
            "organ": "Zastupitelstvo města Litovel",
            "title": "Usnesení z 34. zasedání zastupitelstva města",
            "date": date,
            "year": year,
            "period": "2018-2022",
            "meeting_no": 34,
            "kind": kind,
            "source_url": "https://www.litovel.eu/archive",
            "original_file_url": "https://www.litovel.eu/filemanager/files/2344691.pdf",
            "file_type": "pdf",
            "extraction_method": "pdf_text",
            "ocr_used": False,
            "text_quality": {
                "text_chars": len(search_text),
                "has_text": bool(search_text),
                "quality_flag": quality_flag,
            },
            "search_text": search_text,
            "display_text": search_text,
        }

    def archive_resolution(
        self,
        record_id="ZM-archive-2022-34-usneseni-resolution-001-1",
        parent_document_id="ZM-archive-2022-34-usneseni",
        search_text="1. Schvaluje opravu chodníku v Litovli.",
    ):
        return {
            "id": record_id,
            "type": "archive_resolution",
            "legacy": True,
            "parent_document_id": parent_document_id,
            "org": "ZM",
            "organ": "Zastupitelstvo města Litovel",
            "title": "Archivní usnesení",
            "date": "2022-09-15",
            "year": 2022,
            "period": "2018-2022",
            "meeting_no": 34,
            "kind": "usneseni",
            "ordinal": 1,
            "resolution_no": "1",
            "source_url": "https://www.litovel.eu/archive",
            "original_file_url": "https://www.litovel.eu/filemanager/files/2344691.pdf",
            "source_span": {"start_char": 0, "end_char": len(search_text)},
            "split_method": "heading_resolution",
            "split_confidence": 0.85,
            "search_text": search_text,
            "display_text": search_text,
        }

    def test_parse_numeric_date_metadata(self):
        metadata = parse_title_metadata(
            "Usnesení z 34. zasedání zastupitelstva města z 15. 9. 2022"
        )

        self.assertEqual(metadata["kind"], "usneseni")
        self.assertEqual(metadata["meeting_no"], 34)
        self.assertEqual(metadata["meeting_no_source"], "title")
        self.assertEqual(metadata["meeting_date"], "2022-09-15")
        self.assertIsNone(metadata["date_missing_reason"])
        self.assertEqual(metadata["year"], 2022)
        self.assertEqual(metadata["year_source"], "date")

    def test_parse_textual_date_metadata(self):
        metadata = parse_title_metadata(
            "Usnesení z 30. zasedání zastupitelstva města ze dne 17. prosince 2013"
        )

        self.assertEqual(metadata["kind"], "usneseni")
        self.assertEqual(metadata["meeting_no"], 30)
        self.assertEqual(metadata["meeting_date"], "2013-12-17")
        self.assertEqual(metadata["year"], 2013)
        self.assertEqual(metadata["year_source"], "date")

    def test_parse_voting_metadata(self):
        metadata = parse_title_metadata(
            "Hlasování z 34. zasedání zastupitelstva města z 15. 9. 2022"
        )

        self.assertEqual(metadata["kind"], "hlasovani")
        self.assertEqual(metadata["meeting_no"], 34)
        self.assertEqual(metadata["meeting_date"], "2022-09-15")

    def test_parse_acclamation_voting_metadata(self):
        metadata = parse_title_metadata("Hlasování aklamací z 33. ZML", context_year=2022)

        self.assertEqual(metadata["kind"], "hlasovani_aklamaci")
        self.assertEqual(metadata["meeting_no"], 33)
        self.assertIsNone(metadata["meeting_date"])
        self.assertEqual(metadata["date_missing_reason"], "no_date_in_title")
        self.assertEqual(metadata["year"], 2022)
        self.assertEqual(metadata["year_source"], "section")

    def test_parse_meeting_number_after_ze(self):
        metadata = parse_title_metadata("Hlasování ze 17. ZML", context_year=2020)

        self.assertEqual(metadata["kind"], "hlasovani")
        self.assertEqual(metadata["meeting_no"], 17)
        self.assertEqual(metadata["year"], 2020)

    def test_parse_meeting_number_without_dot(self):
        metadata = parse_title_metadata("Hlasování z 3 ZML", context_year=2018)

        self.assertEqual(metadata["kind"], "hlasovani")
        self.assertEqual(metadata["meeting_no"], 3)
        self.assertEqual(metadata["meeting_no_source"], "title")
        self.assertEqual(metadata["date_missing_reason"], "no_date_in_title")

    def test_parse_generic_voting_title_reason(self):
        metadata = parse_title_metadata("Hlasování", context_year=2017)

        self.assertEqual(metadata["kind"], "hlasovani")
        self.assertIsNone(metadata["meeting_no"])
        self.assertEqual(metadata["meeting_no_source"], "none")
        self.assertEqual(metadata["date_missing_reason"], "generic_voting_title")

    def test_parse_meeting_only_historical_title_reason(self):
        metadata = parse_title_metadata("Usnesení z 31. zasedání zastupitelstva města", context_year=2002)

        self.assertEqual(metadata["kind"], "usneseni")
        self.assertEqual(metadata["meeting_no"], 31)
        self.assertIsNone(metadata["meeting_date"])
        self.assertEqual(metadata["date_missing_reason"], "meeting_only_historical_title")

    def test_crawl_inventory_pairs_flipbook_with_direct_file_and_keeps_unresolved(self):
        inventory = crawl_inventory(ARCHIVE_HTML)

        self.assertEqual(len(inventory), 3)
        by_id = {item["id"]: item for item in inventory}
        usneseni = by_id["ZM-archive-2022-34-usneseni"]
        self.assertEqual(usneseni["id"], "ZM-archive-2022-34-usneseni")
        self.assertEqual(usneseni["period"], "2018-2022")
        self.assertEqual(usneseni["url_kind"], "flipbook")
        self.assertEqual(usneseni["filemanager_id"], "2344691")
        self.assertEqual(usneseni["resolved_file_url"], "https://www.litovel.eu/filemanager/files/2344691.pdf")
        self.assertEqual(usneseni["status"], "discovered")
        self.assertEqual(usneseni["year_source"], "date")
        self.assertEqual(usneseni["meeting_no_source"], "title")

        hlasovani = by_id["ZM-archive-2022-34-hlasovani"]
        self.assertEqual(hlasovani["kind"], "hlasovani")
        self.assertEqual(hlasovani["filemanager_id"], "999999")
        self.assertIsNone(hlasovani["resolved_file_url"])
        self.assertEqual(hlasovani["status"], "needs_resolution")

        doc = by_id["ZM-archive-2003-11-usneseni"]
        self.assertEqual(doc["kind"], "usneseni")
        self.assertEqual(doc["file_type"], "doc")
        self.assertEqual(doc["year"], 2003)
        self.assertEqual(doc["meeting_date"], "2003-12-11")

    def test_crawl_inventory_can_be_parameterized_for_rada(self):
        inventory = crawl_inventory(
            ARCHIVE_HTML,
            "https://www.litovel.eu/cs/mesto/rada-mesta/usneseni-rady-archiv.html",
            source="litovel.eu",
            organ="Rada města Litovel",
            org_code="RM",
        )

        self.assertEqual(len(inventory), 3)
        self.assertTrue(all(item["id"].startswith("RM-archive-") for item in inventory))
        self.assertTrue(all(item["org"] == "RM" for item in inventory))
        self.assertTrue(all(item["organ"] == "Rada města Litovel" for item in inventory))

    def test_text_quality_flag(self):
        self.assertEqual(text_quality_flag("", None, 200), "empty_text")
        self.assertEqual(text_quality_flag("short", None, 200), "short_text")
        self.assertEqual(text_quality_flag("x" * 250, None, 200), "text_ok")
        self.assertEqual(text_quality_flag("bad", "failed", 200), "extraction_failed")
        self.assertEqual(text_quality_flag("\ufffd" * 10 + "abc", None, 200), "probably_binary_garbage")

    def test_report_includes_metadata_duplicates_and_period_year(self):
        inventory = [
            {
                "id": "a",
                "title": "Usnesení z 1. zasedání zastupitelstva města",
                "archive_url": "https://example.test/a.doc",
                "resolved_file_url": "https://example.test/a.doc",
                "period": "1998-2002",
                "year": 2002,
                "year_source": "section",
                "meeting_no": 1,
                "meeting_date": None,
                "date_missing_reason": "meeting_only_historical_title",
                "kind": "usneseni",
                "file_type": "doc",
                "status": "downloaded",
            },
            {
                "id": "b",
                "title": "Usnesení z 2. zasedání zastupitelstva města",
                "archive_url": "https://example.test/a.doc",
                "resolved_file_url": "https://example.test/a.doc",
                "period": "1998-2002",
                "year": 2002,
                "year_source": "section",
                "meeting_no": 2,
                "meeting_date": None,
                "date_missing_reason": "meeting_only_historical_title",
                "kind": "usneseni",
                "file_type": "doc",
                "status": "downloaded",
            },
            {
                "id": "c",
                "title": "Hlasování",
                "archive_url": "https://example.test/c.txt",
                "resolved_file_url": "https://example.test/c.txt",
                "period": "2014-2018",
                "year": 2017,
                "year_source": "section",
                "meeting_no": None,
                "meeting_date": None,
                "date_missing_reason": "generic_voting_title",
                "kind": "hlasovani",
                "file_type": "unknown",
                "status": "downloaded",
            },
            {
                "id": "d",
                "title": "Hlasování",
                "archive_url": "https://example.test/d.txt",
                "resolved_file_url": "https://example.test/d.txt",
                "period": "2014-2018",
                "year": 2017,
                "year_source": "section",
                "meeting_no": None,
                "meeting_date": None,
                "date_missing_reason": "generic_voting_title",
                "kind": "hlasovani",
                "file_type": "unknown",
                "status": "downloaded",
            },
        ]
        records = [
            {"id": "a", "text_quality": {"has_text": True, "text_chars": 500}},
            {"id": "b", "text_quality": {"has_text": True, "text_chars": 50}},
            {"id": "c", "text_quality": {"has_text": False, "text_chars": 0}},
            {"id": "d", "text_quality": {"has_text": False, "text_chars": 0}},
        ]
        extraction = {
            "a": {"quality_flag": "text_ok"},
            "b": {"quality_flag": "short_text"},
            "c": {"quality_flag": "extraction_failed", "error": "unsupported"},
            "d": {"quality_flag": "empty_text"},
        }

        report = build_report(inventory, records, extraction, 200)

        self.assertEqual(report["metadata_quality"]["total_items"], 4)
        self.assertEqual(report["metadata_quality"]["items_without_date"], 4)
        self.assertEqual(report["metadata_quality"]["items_with_year_inferred_from_section"], 4)
        self.assertEqual(len(report["duplicates"]["duplicate_archive_url"]), 1)
        self.assertEqual(len(report["duplicates"]["duplicate_resolved_file_url"]), 1)
        self.assertEqual(len(report["duplicates"]["same_title_different_url"]), 1)
        self.assertEqual(report["text_quality"]["text_ok"], 1)
        self.assertEqual(report["text_quality"]["short_text"], 1)
        self.assertEqual(report["text_quality"]["extraction_failed"], 1)
        self.assertIn(
            {
                "period": "1998-2002",
                "year": "2002",
                "usneseni": 2,
                "hlasovani": 0,
                "hlasovani_aklamaci": 0,
                "unknown": 0,
            },
            report["period_year"],
        )

    def test_archive_search_indexes_usneseni_with_text_ok(self):
        by_year, report = build_payload([self.archive_record()])

        self.assertEqual(report["indexed"], 1)
        self.assertEqual(report["skipped"]["not_usneseni"], 0)
        self.assertEqual(list(by_year), ["2022"])
        self.assertEqual(by_year["2022"][0]["type"], "archive_document")
        self.assertTrue(by_year["2022"][0]["legacy"])

        index = build_index(by_year["2022"])
        self.assertIn("chodnik", index)
        self.assertEqual(index["chodnik"], ["ZM-archive-2022-34-usneseni"])

    def test_archive_search_does_not_index_hlasovani(self):
        record = self.archive_record(
            record_id="ZM-archive-2022-34-hlasovani",
            kind="hlasovani",
        )

        by_year, report = build_payload([record])

        self.assertEqual(by_year, {})
        self.assertEqual(report["indexed"], 0)
        self.assertEqual(report["skipped"]["not_usneseni"], 1)
        self.assertEqual(skip_reason(record), "not_usneseni")

    def test_archive_search_does_not_index_empty_text(self):
        record = self.archive_record(search_text="", quality_flag="empty_text")

        by_year, report = build_payload([record])

        self.assertEqual(by_year, {})
        self.assertEqual(report["indexed"], 0)
        self.assertEqual(report["skipped"]["no_search_text"], 1)
        self.assertEqual(skip_reason(record), "no_search_text")

    def test_archive_search_does_not_index_extraction_failed(self):
        record = self.archive_record(search_text="Neuplny text", quality_flag="extraction_failed")

        by_year, report = build_payload([record])

        self.assertEqual(by_year, {})
        self.assertEqual(report["indexed"], 0)
        self.assertEqual(report["skipped"]["bad_quality_flag"], 1)
        self.assertEqual(skip_reason(record), "bad_quality_flag")

    def test_archive_search_indexes_short_text_and_missing_date(self):
        record = self.archive_record(
            record_id="ZM-archive-2002-31-usneseni",
            search_text="Krátký text",
            quality_flag="short_text",
            date=None,
            year=2002,
        )

        by_year, report = build_payload([record])

        self.assertEqual(report["indexed"], 1)
        self.assertEqual(list(by_year), ["2002"])
        self.assertIsNone(by_year["2002"][0]["date"])

    def test_split_explicit_usneseni_blocks(self):
        block = "Schvaluje opravu chodníku v Litovli a ukládá odboru investic připravit navazující kroky. " * 3
        text = "\n".join(
            [
                "Město Litovel",
                "Usnesení č. 1/2022",
                block,
                "Usnesení č. 2/2022",
                block,
                "Usnesení č. 3/2022",
                block,
            ]
        )
        record = self.archive_record(search_text=text)

        children, outcome = split_document(record)

        self.assertEqual(outcome["status"], "split")
        self.assertEqual(len(children), 3)
        self.assertEqual([child["resolution_no"] for child in children], ["1/2022", "2/2022", "3/2022"])
        self.assertTrue(all(child["type"] == "archive_resolution" for child in children))
        self.assertTrue(all(child["split_method"] == "numbered_resolution" for child in children))

    def test_split_ordinal_verb_blocks(self):
        block = "Bere na vědomí zprávu a schvaluje navržený postup pro další období města Litovel. " * 3
        text = "\n".join(["1. Bere na vědomí " + block, "2. Schvaluje " + block, "3. Ukládá " + block])
        record = self.archive_record(search_text=text)

        children, outcome = split_document(record)

        self.assertEqual(outcome["status"], "split")
        self.assertEqual(len(children), 3)
        self.assertEqual(children[0]["split_method"], "heading_resolution")

    def test_split_rm_slash_meeting_headings(self):
        block = "Rada města schvaluje předložený návrh a ukládá odboru zajistit další postup. " * 3
        text = "\n".join(
            [
                "M ě s t o L i t o v e l",
                "U s n e s e n í",
                "69/5 Stanovení částky za použití vozidel Města Litovel",
                block,
                "70/5 Ad usnesení Rady města Litovel č. 35/2",
                block,
                "71/5 Sjednocení cen tepla pro odběrná místa Města Litovel",
                block,
            ]
        )
        record = self.archive_record(record_id="RM-archive-2006-5-usneseni", search_text=text)
        record["org"] = "RM"
        record["organ"] = "Rada města Litovel"
        record["meeting_no"] = 5

        children, outcome = split_document(record)

        self.assertEqual(outcome["status"], "split")
        self.assertEqual(len(children), 3)
        self.assertEqual([child["resolution_no"] for child in children], ["69/5", "70/5", "71/5"])
        self.assertTrue(all(child["split_method"] == "numbered_resolution" for child in children))

    def test_split_rm_compact_lowercase_slash_headings(self):
        block = "v předloženém znění a za podmínek uvedených v důvodové zprávě. " * 4
        text = "\n".join(
            [
                "Výpis usnesení z 28. schůze Rady města Litovel",
                "807/28 zveřejnění záměru pronájmu prostor sloužících podnikání",
                block,
                "808/28 uzavření smlouvy o právu provést stavbu",
                block,
                "829//28 uzavření Smlouvy o dílo na vyhotovení projektové dokumentace",
                block,
            ]
        )
        record = self.archive_record(record_id="RM-archive-2016-28-usneseni", search_text=text)
        record["org"] = "RM"
        record["organ"] = "Rada města Litovel"
        record["meeting_no"] = 28

        children, outcome = split_document(record)

        self.assertEqual(outcome["status"], "split")
        self.assertEqual([child["resolution_no"] for child in children], ["807/28", "808/28", "829/28"])

    def test_split_rm_slash_heading_must_match_parent_meeting(self):
        block = "Rada města schvaluje předložený návrh a ukládá odboru zajistit další postup. " * 3
        text = "\n".join(
            [
                "56/40 orná půda o výměře pozemku parcely, pokračování odstavce",
                block,
                "57/40 další parcela v textu, nikoliv usnesení této schůze",
                block,
            ]
        )
        record = self.archive_record(record_id="RM-archive-2016-28-usneseni", search_text=text)
        record["org"] = "RM"
        record["organ"] = "Rada města Litovel"
        record["meeting_no"] = 28

        children, outcome = split_document(record)

        self.assertEqual(children, [])
        self.assertEqual(outcome["reason"], "no_boundaries")

    def test_split_recognizes_accept_and_reject_verbs(self):
        block_14 = "Schvaluje odprodej teplovodů, které zásobují teplem sídliště Novosady v Litovli, za cenu 20.000 Kč. " * 2
        block_15 = "Nepřijímá nabídku daru části pozemku v katastru města Litovel, protože je v rozporu se zájmy města. " * 2
        block_16 = "Přijímá nabídku daru jiné části pozemku v katastru města Litovel, která je potřebná pro veřejný zájem. " * 2
        text = "\n".join([
            f"14. {block_14}",
            f"15. {block_15}",
            f"16. {block_16}",
        ])
        record = self.archive_record(search_text=text)

        children, outcome = split_document(record)

        self.assertEqual(outcome["status"], "split")
        self.assertEqual(len(children), 3)
        self.assertEqual([child["resolution_no"] for child in children], ["14", "15", "16"])

    def test_split_ignores_voting_documents(self):
        text = ("Usnesení č. 1/2022\nSchvaluje testovací dlouhý text. " * 20)
        record = self.archive_record(record_id="ZM-archive-2022-34-hlasovani", kind="hlasovani", search_text=text)

        children, outcome = split_document(record)

        self.assertEqual(children, [])
        self.assertEqual(outcome["reason"], "unsupported_kind")

    def test_split_single_boundary_is_unsplit(self):
        text = "Usnesení č. 1/2022\n" + ("Schvaluje dlouhý text usnesení pro ověření splitteru. " * 12)
        record = self.archive_record(search_text=text)

        children, outcome = split_document(record)

        self.assertEqual(children, [])
        self.assertEqual(outcome["reason"], "single_boundary")

    def test_split_suspicious_short_blocks_is_unsplit(self):
        text = (
            ("Úvodní text bez hranic. " * 20)
            + "\nUsnesení č. 1\nA\nUsnesení č. 2\nB\nUsnesení č. 3\nC\n"
        )
        record = self.archive_record(search_text=text)

        children, outcome = split_document(record)

        self.assertEqual(children, [])
        self.assertEqual(outcome["reason"], "suspicious_boundaries")

    def test_split_source_span_matches_parent_text_and_id_is_stable(self):
        block = "Schvaluje přesný text výřezu archivního usnesení a ponechává jej bez přepisu. " * 4
        text = "\n".join(["Hlavička dokumentu", "Usnesení č. 1/2022", block, "Usnesení č. 2/2022", block])
        record = self.archive_record(search_text=text)

        first_children, _first_outcome = split_document(record)
        second_children, _second_outcome = split_document(record)

        self.assertEqual([child["id"] for child in first_children], [child["id"] for child in second_children])
        for child in first_children:
            span = child["source_span"]
            self.assertEqual(text[span["start_char"]:span["end_char"]], child["search_text"])

    def test_split_child_inherits_parent_org_and_organ(self):
        text = "\n".join(
            [
                "1. Schvaluje opravu chodníku v Litovli a pověřuje odbor investic přípravou zadání.",
                "Důvodová zpráva k akci a související technické podklady zůstávají součástí rozhodnutí.",
                "2. Schvaluje rozpočet a ukládá finančnímu odboru zajištění krytí ve schváleném rozpočtu.",
                "Text pokračuje dalším odůvodněním, aby dokument splnil konzervativní prahy pro rozdělení.",
                "3. Bere na vědomí informaci o realizaci a ukládá tajemníkovi zveřejnění usnesení.",
                "Další doplňující odstavec drží délku dokumentu nad minimem.",
            ]
        )
        record = self.archive_record(search_text=text)
        record["org"] = "RM"
        record["organ"] = "Rada města Litovel"

        children, outcome = split_document(record)

        self.assertEqual(outcome["status"], "split")
        self.assertTrue(children)
        self.assertTrue(all(child["org"] == "RM" for child in children))
        self.assertTrue(all(child["organ"] == "Rada města Litovel" for child in children))

    def test_archive_search_indexes_children_and_skips_split_parent(self):
        parent = self.archive_record(search_text="Parent text with chodnik.")
        child = self.archive_resolution(search_text="1. Schvaluje opravu chodníku v Litovli.")

        by_year, report = build_payload([parent], [child])

        self.assertEqual(report["indexed"], 1)
        self.assertEqual(report["indexed_archive_resolutions"], 1)
        self.assertEqual(report["fallback_archive_documents"], 0)
        self.assertEqual(report["skipped_split_parents"], 1)
        self.assertEqual(by_year["2022"][0]["type"], "archive_resolution")

    def test_archive_search_uses_parent_fallback_when_unsplit(self):
        parent = self.archive_record(search_text="Parent fallback text with chodnik.")

        by_year, report = build_payload([parent], [])

        self.assertEqual(report["indexed"], 1)
        self.assertEqual(report["indexed_archive_resolutions"], 0)
        self.assertEqual(report["fallback_archive_documents"], 1)
        self.assertEqual(by_year["2022"][0]["type"], "archive_document")


if __name__ == "__main__":
    unittest.main()
