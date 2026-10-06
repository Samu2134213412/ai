"""Aufgeräumte Seite: das selbstgebaute PDF muss in einem echten PDF-Leser aufgehen."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node nicht installiert")
class PdfExport(unittest.TestCase):
    def test_real_reader_opens_it(self):
        try:
            import pypdf
            from PIL import Image
        except ImportError:
            self.skipTest("pypdf/Pillow fehlen")
        tmp = Path(tempfile.mkdtemp())
        for i, color in enumerate(("white", "#ffd9a8")):
            Image.new("RGB", (1240, 1754), color).save(tmp / f"p{i}.jpg", "JPEG")
        out = tmp / "seite.pdf"
        subprocess.run(["node", str(ROOT / "tests" / "pdf_make.js"), str(out), str(tmp / "p0.jpg"), str(tmp / "p1.jpg")], check=True)
        reader = pypdf.PdfReader(str(out))
        self.assertEqual(len(reader.pages), 2)
        box = reader.pages[0].mediabox
        self.assertEqual((round(float(box.width)), round(float(box.height))), (595, 842))          # A4
        images = [im for p in reader.pages for im in p.images]
        self.assertEqual(len(images), 2)
        self.assertEqual(images[0].image.size, (1240, 1754))
        self.assertEqual(images[1].image.getpixel((10, 10))[0], 255)


if __name__ == "__main__":
    unittest.main()
