import tempfile
import unittest
from pathlib import Path

import fitz

from paper_figures import catalog_pdf, crop_candidate


class PaperFigureTests(unittest.TestCase):
    def test_catalogs_and_crops_a_paper_native_figure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf = root / "paper.pdf"
            output = root / "crop.png"
            document = fitz.open()
            page = document.new_page(width=300, height=400)
            page.draw_rect(fitz.Rect(40, 50, 260, 180), color=(0, 0, 0), fill=(0.9, 0.9, 0.9))
            page.insert_textbox(
                fitz.Rect(40, 190, 260, 230),
                "Figure 1. Accuracy improves from 70% to 91%.",
                fontsize=10,
            )
            document.save(pdf)
            document.close()

            catalog = catalog_pdf(pdf)

            self.assertEqual(len(catalog["candidates"]), 1)
            candidate = catalog["candidates"][0]
            self.assertEqual(candidate["label"], "Figure 1")
            self.assertLess(candidate["bbox_frac"][1], 0.14)
            self.assertGreater(candidate["bbox_frac"][3], 0.5)

            crop_candidate(pdf, candidate["id"], output)
            self.assertTrue(output.exists())
            with fitz.open(output) as image:
                self.assertGreater(image[0].rect.width, 0)

    def test_rejects_an_unknown_candidate(self):
        with tempfile.TemporaryDirectory() as temporary:
            pdf = Path(temporary) / "paper.pdf"
            document = fitz.open()
            document.new_page()
            document.save(pdf)
            document.close()

            with self.assertRaisesRegex(ValueError, "unknown candidate"):
                crop_candidate(pdf, "c99", Path(temporary) / "crop.png")


if __name__ == "__main__":
    unittest.main()
