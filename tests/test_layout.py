from collections import Counter
from itertools import combinations

from hwfont import layout as L


def test_every_character_has_all_its_samples():
    pages = L.build_layout()
    counts = Counter(b.text for p in pages for b in p.boxes if b.sample is not None)
    assert set(counts) == set(L.CHARACTERS)
    assert set(counts.values()) == {L.SAMPLES_PER_CHAR}


def test_every_sentence_line_is_placed_once():
    pages = L.build_layout()
    lines = [b.text for p in pages for b in p.boxes if b.sample is None]
    assert lines == list(L.SENTENCE_LINES)


def test_boxes_stay_between_the_markers():
    for page in L.build_layout():
        for b in page.boxes:
            assert L.CONTENT_LEFT <= b.x and b.x + b.w <= L.CONTENT_RIGHT + 1e-9
            assert L.GRID_TOP <= b.y and b.y + b.h <= L.GRID_BOTTOM + 1e-9


def test_boxes_do_not_overlap():
    for page in L.build_layout():
        for a, b in combinations(page.boxes, 2):
            apart = (a.x + a.w <= b.x + 1e-9 or b.x + b.w <= a.x + 1e-9 or
                     a.y + a.h <= b.y + 1e-9 or b.y + b.h <= a.y + 1e-9)
            assert apart, (a, b)


def test_guides_run_top_to_bottom_inside_each_box():
    for page in L.build_layout():
        for b in page.boxes:
            assert b.y < b.ascender < b.x_height < b.baseline < b.y + b.h


def test_marker_ids_identify_the_page():
    pages = L.build_layout()
    ids = [m.id for p in pages for m in p.markers]
    assert len(ids) == len(set(ids))
    for p in pages:
        assert {m.id // L.MARKERS_PER_PAGE for m in p.markers} == {p.index}
