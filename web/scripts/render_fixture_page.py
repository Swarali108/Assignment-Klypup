"""Render one real cached SEDEMAC RHP page to PNG (plain + quote highlighted) for the gallery.
Read-only use of cache/fetch. Run: .venv/bin/python web/scripts/render_fixture_page.py"""
import hashlib, pathlib
import pdfplumber
from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parents[2]
URL = "https://www.icicisecurities.com/Upload/ArticleAttachments/SEDEMAC%20MECHATRONICS%20LIMITED%20-%20RHP.pdf"
PDF_INDEX, QUOTE = 20, "Up to 45,000 Equity Shares of face"
OUT = ROOT / "web/public/fixtures"
pdf_path = ROOT / "cache/fetch" / (hashlib.sha256(URL.encode()).hexdigest() + ".bin")
with pdfplumber.open(pdf_path) as pdf:
    page = pdf.pages[PDF_INDEX - 1]
    res = 150
    img = page.to_image(resolution=res).original.convert("RGB")
    img.save(OUT / "evidence-plain.png", optimize=True)
    hits = page.search(QUOTE)
    print("hits", len(hits))
    scale = res / 72
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    for h in hits[:1]:
        box = [h["x0"] * scale - 4, h["top"] * scale - 3, h["x1"] * scale + 4, h["bottom"] * scale + 3]
        d.rectangle(box, fill=(255, 214, 90, 110), outline=(196, 140, 20, 255), width=2)
    Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB").save(OUT / "evidence-highlight.png", optimize=True)
