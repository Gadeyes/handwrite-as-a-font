import cv2
import numpy as np
import pytest

pytest.importorskip("pypdfium2")

from fake_photo import photograph, render_page, write_in  # noqa: E402
from hwfont import layout as L  # noqa: E402
from hwfont.scan import PX_PER_MM, ScanError, scan  # noqa: E402
from hwfont.template import write_template  # noqa: E402


@pytest.fixture(scope="module")
def pages_and_pdf(tmp_path_factory):
    pdf = tmp_path_factory.mktemp("scan") / "template.pdf"
    return write_template(pdf), pdf


def filled_page(pages_and_pdf, index=0, every=4):
    """Template page `index` with every `every`-th box written in."""
    pages, pdf = pages_and_pdf
    img = render_page(pdf, index)
    filled = pages[index].boxes[::every]
    write_in(img, filled)
    return img, filled


def ink_in(page, box, inset_mm=0.0):
    x0, y0 = int((box.x + inset_mm) * PX_PER_MM), int((box.y + inset_mm) * PX_PER_MM)
    x1, y1 = int((box.x + box.w - inset_mm) * PX_PER_MM), int((box.y + box.h - inset_mm) * PX_PER_MM)
    return int(page.ink[y0:y1, x0:x1].sum())


def check_boxes(page, pages, filled):
    """Written boxes have ink; empty boxes have none (guides and borders gone)."""
    filled_ids = {id(b) for b in filled}
    for b in pages[page.index].boxes:
        if id(b) in filled_ids:
            assert ink_in(page, b, inset_mm=1.0) > 200, f"lost the ink in box {b.text!r}"
        else:
            # a few speckles from noise are tolerable; a guide line would be thousands of pixels
            assert ink_in(page, b) < 30, f"stray ink in empty box {b.text!r}"


def test_clean_render_lines_up_exactly(pages_and_pdf):
    pages, _ = pages_and_pdf
    img, filled = filled_page(pages_and_pdf)
    page = scan(img, pages)
    assert page.index == 0 and page.markers_found == 4
    assert page.fit_error_mm < 0.2
    check_boxes(page, pages, filled)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_tilted_shaded_photo(pages_and_pdf, seed):
    pages, _ = pages_and_pdf
    img, filled = filled_page(pages_and_pdf, index=1)
    page = scan(photograph(img, seed=seed), pages)
    assert page.index == 1
    assert page.fit_error_mm < 0.5
    check_boxes(page, pages, filled)


def test_upside_down_photo(pages_and_pdf):
    pages, _ = pages_and_pdf
    img, filled = filled_page(pages_and_pdf, index=2)
    page = scan(photograph(img, seed=4, rotate_180=True), pages)
    assert page.index == 2
    check_boxes(page, pages, filled)


def test_one_marker_covered_still_works(pages_and_pdf):
    pages, pdf = pages_and_pdf
    img, filled = filled_page(pages_and_pdf)
    m = pages[0].markers[2]
    s = 200 / 25.4  # fake_photo.RENDER_PX_PER_MM
    cv2.rectangle(img, (int((m.x - 1) * s), int((m.y - 1) * s)),
                  (int((m.x + m.size + 1) * s), int((m.y + m.size + 1) * s)), (180, 170, 160), -1)
    page = scan(photograph(img, seed=5), pages)
    assert page.markers_found == 3
    check_boxes(page, pages, filled)


def test_two_markers_covered_is_an_error(pages_and_pdf):
    pages, pdf = pages_and_pdf
    img = render_page(pdf, 0)
    s = 200 / 25.4
    for m in pages[0].markers[:2]:
        cv2.rectangle(img, (int((m.x - 1) * s), int((m.y - 1) * s)),
                      (int((m.x + m.size + 1) * s), int((m.y + m.size + 1) * s)), (255, 255, 255), -1)
    with pytest.raises(ScanError, match="only 2 of the 4"):
        scan(img, pages)


def test_photo_without_markers_is_an_error(pages_and_pdf):
    pages, _ = pages_and_pdf
    with pytest.raises(ScanError, match="no corner squares"):
        scan(np.full((800, 600, 3), 230, np.uint8), pages)
