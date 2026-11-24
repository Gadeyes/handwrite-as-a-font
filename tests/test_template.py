"""Render the PDF back to pixels and check what the scanning side will need."""

import cv2
import numpy as np
import pytest

from hwfont import layout as L
from hwfont.template import write_template

pdfium = pytest.importorskip("pypdfium2")

DPI = 200
PX_PER_MM = DPI / 25.4


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    out = tmp_path_factory.mktemp("template") / "template.pdf"
    pages = write_template(out)
    pdf = pdfium.PdfDocument(str(out))
    images = [np.array(pdf[i].render(scale=DPI / 72).to_pil().convert("RGB")) for i in range(len(pdf))]
    pdf.close()
    return pages, images


def test_one_pdf_page_per_layout_page(rendered):
    pages, images = rendered
    assert len(images) == len(pages)


def test_markers_are_found_where_the_layout_says(rendered):
    pages, images = rendered
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, L.ARUCO_DICT))
    detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())
    for page, img in zip(pages, images):
        corners, ids, _ = detector.detectMarkers(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY))
        assert ids is not None
        found = {int(i): c.reshape(4, 2).mean(axis=0) for i, c in zip(ids.flatten(), corners)}
        assert set(found) == {m.id for m in page.markers}
        for m in page.markers:
            expected = np.array(m.center) * PX_PER_MM
            assert np.linalg.norm(found[m.id] - expected) < 3  # pixels


def test_guides_and_borders_vanish_when_binarised(rendered):
    """An empty template must come out with no ink inside any box."""
    pages, images = rendered
    for page, img in zip(pages, images):
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        ink = binary == 0
        for b in page.boxes:
            x0, y0 = int(b.x * PX_PER_MM), int(b.y * PX_PER_MM)
            x1, y1 = int((b.x + b.w) * PX_PER_MM), int((b.y + b.h) * PX_PER_MM)
            assert not ink[y0:y1 + 1, x0:x1 + 1].any(), f"ink in empty box {b.text!r} on page {page.index + 1}"
