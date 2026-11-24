"""Draw the printable template PDF from the layout.

    python -m hwfont.template                  # writes data/template.pdf
    python -m hwfont.template -o my-sheet.pdf

Everything the writer must not trace (box borders, guide lines) is printed
light enough to vanish when the scan is turned into black and white. Labels
and instructions are dark, but they sit outside the boxes, so slicing never
picks them up.
"""

import argparse
from pathlib import Path

import cv2
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

from hwfont import layout as L

# Light colours land on the paper side of the black/white cut (grey level
# about 190 out of 255; ink is under 100, paper over 220).
BORDER = (0.78, 0.78, 0.78)
GUIDE = (0.75, 0.75, 0.75)
BASELINE = (0.63, 0.77, 0.95)   # light blue, so it can be told apart from the grey guides
TEXT = (0, 0, 0)
SOFT_TEXT = (0.35, 0.35, 0.35)

INSTRUCTIONS = (
    "Use a black or dark-blue pen. Write each character once per box. Sit every letter on the "
    "blue line; small letters reach the dashed line, capitals and tall letters the dotted line, "
    "and the tails of g, j, p, q, y hang below."
)
FOOTER = "Photograph the whole page lying flat, in good light, with all four black squares visible."


def _pt(x: float, y: float) -> tuple[float, float]:
    """Layout millimetres (top-left origin, y down) -> PDF points (bottom-left origin, y up)."""
    return x * mm, (L.PAGE_H - y) * mm


def _hline(c: canvas.Canvas, x0: float, x1: float, y: float, color, width: float, dash=None) -> None:
    c.setStrokeColorRGB(*color)
    c.setLineWidth(width * mm)
    c.setDash([d * mm for d in dash] if dash else [])
    c.line(*_pt(x0, y), *_pt(x1, y))


def draw_marker(c: canvas.Canvas, marker: L.Marker) -> None:
    """Draw an ArUco marker as vector squares, so it stays sharp at any print size."""
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, L.ARUCO_DICT))
    # Asking for one pixel per module returns the bit pattern itself: 0 = black.
    bits = cv2.aruco.generateImageMarker(dictionary, marker.id, 6)
    n = bits.shape[0]
    module = marker.size / n
    path = c.beginPath()
    for row in range(n):
        for col in range(n):
            if bits[row, col] == 0:
                # rect() takes the bottom-left corner, so step down one module.
                x, y = _pt(marker.x + col * module, marker.y + (row + 1) * module)
                path.rect(x, y, module * mm, module * mm)
    c.setFillColorRGB(0, 0, 0)
    c.drawPath(path, stroke=0, fill=1)


def draw_box(c: canvas.Canvas, box: L.Box) -> None:
    _hline(c, box.x, box.x + box.w, box.ascender, GUIDE, 0.3, dash=(0.5, 1.0))
    _hline(c, box.x, box.x + box.w, box.x_height, GUIDE, 0.3, dash=(2.0, 1.5))
    _hline(c, box.x, box.x + box.w, box.baseline, BASELINE, 0.4)
    c.setDash([])
    c.setStrokeColorRGB(*BORDER)
    c.setLineWidth(0.25 * mm)
    x, y = _pt(box.x, box.y + box.h)
    c.rect(x, y, box.w * mm, box.h * mm, stroke=1, fill=0)


def draw_label(c: canvas.Canvas, label: L.Label) -> None:
    x, y = _pt(label.x + 0.5, label.y + L.LABEL_H - 1.0)
    sentence = len(label.text) > 1
    font, size = ("Helvetica", 9) if sentence else ("Helvetica-Bold", 11)
    c.setFillColorRGB(*TEXT)
    c.setFont(font, size)
    c.drawString(x, y, label.text)
    if label.hint:
        c.setFillColorRGB(*SOFT_TEXT)
        c.setFont("Helvetica", 6.5)
        c.drawString(x + c.stringWidth(label.text, font, size) + 1.5 * mm, y, f"({label.hint})")


def draw_page_text(c: canvas.Canvas, page: L.Page, n_pages: int) -> None:
    # Between the top markers: title and instructions. Between the bottom ones: footer.
    left = L.MARGIN + L.MARKER_SIZE + L.MARKER_GAP
    right = L.PAGE_W - L.MARGIN - L.MARKER_SIZE - L.MARKER_GAP
    c.setFillColorRGB(*TEXT)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(*_pt(left, L.MARGIN + 4.0), "Handwriting font template")
    c.setFont("Helvetica", 9)
    c.drawRightString(*_pt(right, L.MARGIN + 4.0), f"page {page.index + 1} of {n_pages}")

    c.setFillColorRGB(*SOFT_TEXT)
    c.setFont("Helvetica", 7)
    for i, line in enumerate(simpleSplit(INSTRUCTIONS, "Helvetica", 7, (right - left) * mm)):
        c.drawString(*_pt(left, L.MARGIN + 7.5 + i * 3.0), line)
    c.drawCentredString(*_pt(L.PAGE_W / 2, L.PAGE_H - L.MARGIN - L.MARKER_SIZE / 2 + 1.0), FOOTER)


def write_template(out: Path, pages: list[L.Page] | None = None) -> list[L.Page]:
    pages = pages if pages is not None else L.build_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out), pagesize=(L.PAGE_W * mm, L.PAGE_H * mm))
    c.setTitle("Handwriting font template")
    c.setCreator("hwfont")
    for page in pages:
        for marker in page.markers:
            draw_marker(c, marker)
        for box in page.boxes:
            draw_box(c, box)
        for label in page.labels:
            draw_label(c, label)
        draw_page_text(c, page, len(pages))
        c.showPage()
    c.save()
    return pages


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", type=Path, default=Path("data/template.pdf"))
    args = ap.parse_args()
    pages = write_template(args.out)
    n_boxes = sum(len(p.boxes) for p in pages)
    print(f"wrote {args.out}: {len(pages)} pages, {n_boxes} boxes")


if __name__ == "__main__":
    main()
