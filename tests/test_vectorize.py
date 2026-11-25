import cv2
import numpy as np
from fontTools.pens.areaPen import AreaPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen

from hwfont import layout as L
from hwfont.scan import PX_PER_MM
from hwfont.slice import INSET_MM, OK, Cut
from hwfont.vectorize import CAP_HEIGHT, baseline_for, measure_scale, trace, vectorize

H = round((L.CELL_H - 2 * INSET_MM) * PX_PER_MM)
W = round((L.CELL_W - 2 * INSET_MM) * PX_PER_MM)
BASE = round((L.BASELINE_Y - INSET_MM) * PX_PER_MM)


def ring_cut(char="o", lift_px=0, height_px=70):
    """A ring (an 'o' with a hole) resting lift_px above the baseline."""
    ink = np.zeros((H, W), np.uint8)
    r = height_px // 2
    cv2.circle(ink, (W // 2, BASE - lift_px - r), r - 4, 1, thickness=8)
    return Cut(L.Box(0, 0, 0, L.CELL_W, L.CELL_H, char, 0), ink.astype(bool), OK)


def contour_areas(rec: RecordingPen) -> list[float]:
    """Signed area of each contour separately."""
    areas, current = [], RecordingPen()
    for op, args in rec.value:
        getattr(current, op)(*args)
        if op == "closePath":
            pen = AreaPen()
            current.replay(pen)
            areas.append(pen.value)
            current = RecordingPen()
    return areas


def bounds(rec: RecordingPen):
    bp = BoundsPen(None)
    rec.replay(bp)
    return bp.bounds


def test_ring_keeps_its_hole_with_cff_directions():
    cut = ring_cut()
    areas = contour_areas(trace(cut.ink, BASE, 10.0))
    assert len(areas) == 2
    assert max(areas) > 0 > min(areas)  # outer counter-clockwise, hole clockwise


def test_outline_starts_at_x0_and_sits_on_the_baseline():
    cut = ring_cut()
    x_min, y_min, _, y_max = bounds(trace(cut.ink, baseline_for(cut), 10.0))
    assert abs(x_min) < 10 and abs(y_min) < 10  # within one pixel at 10 units/px
    assert y_max > 0  # upright, not upside down


def test_drifting_letter_is_snapped_to_the_baseline():
    cut = ring_cut("o", lift_px=12)  # written 1 mm above the line
    assert abs(baseline_for(cut) - (BASE - 12)) <= 1


def test_tailed_letter_is_left_where_it_was_written():
    cut = ring_cut("g", lift_px=12)
    assert baseline_for(cut) == cut.baseline_px


def test_scale_comes_from_the_capitals():
    caps = [ring_cut(c, height_px=100) for c in "EHT"]
    assert abs(measure_scale(caps) * 100 - CAP_HEIGHT) < 0.05 * CAP_HEIGHT


def test_empty_and_sentence_boxes_are_skipped():
    empty = Cut(L.Box(0, 0, 0, L.CELL_W, L.CELL_H, "x", 1), np.zeros((H, W), bool), "empty")
    line = ring_cut()
    line.box = L.Box(0, 0, 0, L.CONTENT_W, L.CELL_H, "The quick brown fox", None)
    glyphs = vectorize([empty, line, ring_cut("o")])
    assert [(g.char, g.sample) for g in glyphs] == [("o", 0)]
