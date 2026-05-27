import os
import tempfile
import unittest
from pathlib import Path

from tools.prepare_manual_pdf import prepare_manual_pdf, safe_relative_path


class PrepareManualPdfTest(unittest.TestCase):
    def test_safe_relative_path_accepts_pdf_under_resources(self):
        self.assertEqual(
            safe_relative_path(Path("resources/rm/rm_74_26.pdf")),
            Path("resources/rm/rm_74_26.pdf"),
        )

    def test_safe_relative_path_rejects_paths_outside_resources(self):
        with self.assertRaises(ValueError):
            safe_relative_path(Path("../secret.pdf"))

        with self.assertRaises(ValueError):
            safe_relative_path(Path("work/phase1/file.pdf"))

        with self.assertRaises(ValueError):
            safe_relative_path(Path("resources/rm/file.txt"))

    def test_prepare_existing_pdf_path_records_manifest_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "resources" / "rm" / "rm_74_26.pdf"
            pdf.parent.mkdir(parents=True)
            pdf.write_bytes(b"%PDF-1.4\n")

            cwd = Path.cwd()
            try:
                os.chdir(root)
                manual = prepare_manual_pdf(
                    document_type="resolution",
                    pdf_path="resources/rm/rm_74_26.pdf",
                    pdf_url="",
                    target_filename="",
                    resolution_target="rm",
                    resources_dir=Path("resources"),
                    ro_dir=Path("resources/rozpoctova-opatreni"),
                    dry_run=False,
                )
            finally:
                os.chdir(cwd)

            self.assertEqual(manual.kind, "resolution")
            self.assertEqual(manual.path, "resources/rm/rm_74_26.pdf")

    def test_prepare_url_dry_run_chooses_budget_target_directory(self):
        manual = prepare_manual_pdf(
            document_type="budget_change",
            pdf_path="",
            pdf_url="https://github.com/user-attachments/files/1234/manual.pdf",
            target_filename="Rozpočtové opatření č. 10 2026.pdf",
            resolution_target="rm",
            resources_dir=Path("resources"),
            ro_dir=Path("resources/rozpoctova-opatreni"),
            dry_run=True,
        )

        self.assertEqual(manual.kind, "budget_change")
        self.assertEqual(
            manual.path,
            "resources/rozpoctova-opatreni/rozpoctove_opatreni_c._10_2026.pdf",
        )

    def test_prepare_requires_exactly_one_source(self):
        with self.assertRaises(ValueError):
            prepare_manual_pdf(
                document_type="resolution",
                pdf_path="resources/rm/rm_74_26.pdf",
                pdf_url="https://example.test/file.pdf",
                target_filename="",
                resolution_target="rm",
                resources_dir=Path("resources"),
                ro_dir=Path("resources/rozpoctova-opatreni"),
                dry_run=True,
            )


if __name__ == "__main__":
    unittest.main()
