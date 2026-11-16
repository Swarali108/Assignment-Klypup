"""Render a cached PDF page as PNG with the quoted text highlighted.

pdfplumber finds the quote's boxes (Page.search); pypdfium2 renders the page. When the
quote cannot be found the plain page is returned and the caller sets X-Highlight: none.
Rendered images are cached under api/state/pages/.
"""

from __future__ import annotations

import hashlib
import io
import re
import threading
from pathlib import Path

import pdfplumber
import pypdfium2
from PIL import Image, ImageDraw

from api import store

DPI = 150
STATE_DIR = Path(__file__).resolve().parent / "state" / "pages"
HIGHLIGHT_FILL = (255, 214, 0, 110)
HIGHLIGHT_LINE = (214, 158, 0, 255)
# PDFium must never run on two threads at once (pypdfium2 docs); every render and page count holds this.
_PDFIUM = threading.Lock()
# Large pages (newspaper notices) are scaled down so the longest side stays under this.
MAX_PIXELS = 2200
# Shorter windows tried when the whole quote is not found (words).
WINDOW = 8


def _patterns(quote: str) -> list[str]:
    """Regexes to try, longest first: the whole quote, then its first and last WINDOW words."""
    parts = [p.strip() for p in re.split(r"…|\.\.\.", quote) if p.strip()]
    text = max(parts, key=len) if parts else quote
    words = [w for w in re.split(r"\s+", text) if w]
    if not words:
        return []
    joined = lambda ws: r"\s*".join(re.escape(w) for w in ws)  # noqa: E731
    found = [joined(words)]
    if len(words) > WINDOW:
        found += [joined(words[:WINDOW]), joined(words[-WINDOW:])]
    return found


def find_boxes(pdf: Path, pdf_index: int, quote: str | None) -> list[tuple[float, float, float, float]]:
    """(x0, top, x1, bottom) boxes in PDF points for the quote on that page; [] when not found."""
    if not quote:
        return []
    with pdfplumber.open(pdf, pages=[pdf_index]) as doc:
        if not doc.pages:
            return []
        page = doc.pages[0]
        for pattern in _patterns(quote):
            for case in (True, False):
                try:
                    hits = page.search(pattern, regex=True, case=case, return_chars=True)
                except Exception:  # a malformed text layer: no highlight, still show the page
                    hits = []
                if hits:
                    return _line_boxes(hits)
    return []


def _line_boxes(hits: list[dict]) -> list[tuple[float, float, float, float]]:
    """One box per text line of each match (a match across lines is split by its chars)."""
    boxes = []
    for hit in hits[:3]:
        lines: dict[int, list[dict]] = {}
        for char in hit.get("chars") or []:
            lines.setdefault(round(char["top"]), []).append(char)
        if not lines:
            boxes.append((hit["x0"], hit["top"], hit["x1"], hit["bottom"]))
            continue
        for chars in lines.values():
            boxes.append((min(c["x0"] for c in chars), min(c["top"] for c in chars),
                          max(c["x1"] for c in chars), max(c["bottom"] for c in chars)))
    return boxes


def page_count(pdf: Path) -> int:
    """Pages in a PDF."""
    with _PDFIUM:
        doc = pypdfium2.PdfDocument(str(pdf))
        try:
            return len(doc)
        finally:
            doc.close()


def render(doc_sha: str, pdf_index: int, quote: str | None) -> tuple[bytes, str | None]:
    """(PNG bytes, highlight box or None) for one page; raises FileNotFoundError / IndexError.

    The box is "x0,y0,x1,y1" as fractions of the image (0..1) around every highlighted line,
    so the viewer can scroll to it.
    """
    pdf = store.pdf_path(doc_sha)
    if pdf is None:
        raise FileNotFoundError(doc_sha)
    key = hashlib.sha256(f"{doc_sha}|{pdf_index}|{quote or ''}|{DPI}".encode()).hexdigest()[:32]
    cached = STATE_DIR / f"{key}.png"
    flag = STATE_DIR / f"{key}.hl"
    if cached.is_file():
        return cached.read_bytes(), (flag.read_text() if flag.is_file() else None)
    with _PDFIUM:
        if cached.is_file():
            return cached.read_bytes(), (flag.read_text() if flag.is_file() else None)
        return _render_locked(pdf, pdf_index, quote, cached, flag)


def _render_locked(pdf: Path, pdf_index: int, quote: str | None, cached: Path, flag: Path) -> tuple[bytes, str | None]:
    """Render, highlight and cache one page; the caller holds _PDFIUM."""
    doc = pypdfium2.PdfDocument(str(pdf))
    try:
        if not 1 <= pdf_index <= len(doc):
            raise IndexError(pdf_index)
        page = doc[pdf_index - 1]
        width, height = page.get_size()
        scale = min(DPI / 72, MAX_PIXELS / max(width, height))
        image = page.render(scale=scale).to_pil().convert("RGBA")
    finally:
        doc.close()
    boxes = find_boxes(pdf, pdf_index, quote)
    box = None
    if boxes:
        w, h = image.size[0] / scale, image.size[1] / scale
        box = ",".join(f"{v:.4f}" for v in (min(b[0] for b in boxes) / w, min(b[1] for b in boxes) / h,
                                              max(b[2] for b in boxes) / w, max(b[3] for b in boxes) / h))
    if boxes:
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        pad = 2 * scale
        for x0, top, x1, bottom in boxes:
            rect = (x0 * scale - pad, top * scale - pad, x1 * scale + pad, bottom * scale + pad)
            draw.rectangle(rect, fill=HIGHLIGHT_FILL, outline=HIGHLIGHT_LINE, width=2)
        image = Image.alpha_composite(image, overlay)
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    data = buffer.getvalue()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if box:
        flag.write_text(box)
    tmp = cached.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(cached)
    return data, box
