import cv2
import numpy as np
import pytest

pytest.importorskip("pypdfium2")

from fake_photo import RENDER_PX_PER_MM, INK_BGR, photograph, render_page, write_in  # noqa: E402
from hwfont import layout as L  # noqa: E402
from hwfont.scan import scan  # noqa: E402
from hwfont.slice import EMPTY, OK, OVERFLOW, file_stem, remove_specks, report, slice_page  # noqa: E402
from hwfont.template import write_template  # noqa: E402


@pytest.fixture(scope="module")
def sliced(tmp_path_factory):
    pdf = tmp_path_factory.mktemp("slice") / "template.pdf"
    pages = write_template(pdf)
    img = render_page(pdf, 0)
    boxes = pages[0].boxes
    write_in(img, boxes[::3])  # sample 0 of every character on the page
    # One stroke deliberately crossing the right edge of the last 'b' box, into the gap after it.
    b = next(b for b in boxes if b.text == "b" and b.sample == 2)
    s = RENDER_PX_PER_MM
    cv2.line(img, (int((b.x + b.w - 4) * s), int(b.baseline * s)),
             (int((b.x + b.w + 2) * s), int(b.baseline * s)), INK_BGR, int(0.6 * s))
    cuts = slice_page(scan(photograph(img, seed=7), pages), pages)
    return {(c.box.text, c.box.sample): c for c in cuts}


def test_written_boxes_are_ok_and_skipped_ones_empty(sliced):
    for (char, sample), cut in sliced.items():
        if (char, sample) == ("b", 2):
            continue
        assert cut.status == (OK if sample == 0 else EMPTY), (char, sample, cut.status)


def test_writing_over_the_edge_is_flagged(sliced):
    assert sliced[("b", 2)].status == OVERFLOW
    assert any("'b' sample 3" in p for p in report(list(sliced.values())))


def test_descender_lands_below_the_baseline_row(sliced):
    cut = sliced[("g", 0)]
    bottom = np.nonzero(cut.ink.any(axis=1))[0][-1]
    assert bottom > cut.baseline_px + 1.5 * 12  # tail at least 1.5 mm below the line


def test_report_names_characters_with_no_usable_sample():
    from hwfont.slice import Cut
    box = L.Box(0, 0, 0, 10, 10, "q", 0)
    cuts = [Cut(box, np.zeros((5, 5), bool), EMPTY)]
    assert report(cuts) == ["'q': all boxes are empty"]


def test_specks_are_removed_but_dots_kept():
    ink = np.zeros((100, 100), bool)
    ink[10, 10] = True            # one-pixel speck
    ink[50:58, 50:58] = True      # 64 px dot, like a full stop
    clean = remove_specks(ink)
    assert not clean[10, 10] and clean[50:58, 50:58].all()


def test_a_quick_full_stop_is_not_mistaken_for_an_empty_box():
    from hwfont.scan import ScannedPage
    from hwfont.slice import cut_box
    page = L.build_layout()[1]
    dot_box = next(b for b in page.boxes if b.text == ".")
    a_box = page.boxes[0]
    ink = np.zeros((round(L.PAGE_H * 12), round(L.PAGE_W * 12)), bool)
    for box in (dot_box, a_box):
        y, x = round((box.y + box.h / 2) * 12), round((box.x + box.w / 2) * 12)
        ink[y:y + 5, x:x + 6] = True  # 30 px: as small as the real full stops measured
    scanned = ScannedPage(1, None, ink, 4, 0.0, 128)
    assert cut_box(scanned, dot_box).status == OK
    assert cut_box(scanned, a_box).status == EMPTY  # too little for a letter: still empty


def test_file_names_are_unique_even_on_case_insensitive_disks():
    from hwfont.slice import Cut
    stems = [file_stem(Cut(b, np.zeros((1, 1), bool), OK)) for p in L.build_layout() for b in p.boxes]
    assert len({s.lower() for s in stems}) == len(stems)
    assert all(ch not in s for s in stems for ch in '<>:"/\\|?*')
