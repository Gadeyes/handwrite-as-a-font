"""Rotating variants: every clean sample in the font, cycled by the calt feature."""

import numpy as np
import pytest
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont

pytest.importorskip("uharfbuzz")

from hwfont.build import build_font, samples_by_char  # noqa: E402
from hwfont.render import glyph_names, render  # noqa: E402
from hwfont.vectorize import Glyph, even_out_sizes  # noqa: E402


def box(width, height, bottom=0):
    """A filled rectangle outline, counter-clockwise like a real outer contour."""
    rec = RecordingPen()
    rec.moveTo((0, bottom))
    rec.lineTo((width, bottom))
    rec.lineTo((width, bottom + height))
    rec.lineTo((0, bottom + height))
    rec.closePath()
    return rec


def glyph(char, sample, width=300, height=480, clean=True, bottom=0):
    return Glyph(char, sample, clean, box(width, height, bottom))


@pytest.fixture(scope="module")
def font(tmp_path_factory):
    glyphs = [glyph("a", i, width=250 + 40 * i) for i in range(3)]      # 3 samples
    glyphs += [glyph("b", i, width=300 + 40 * i, height=700) for i in range(2)]  # 2 samples
    glyphs += [glyph("c", 0)]                                           # 1 sample
    glyphs += [glyph("d", 0, clean=False), glyph("d", 1), glyph("d", 2, clean=False)]
    return build_font(glyphs, "HW Variants Test", tmp_path_factory.mktemp("variants") / "v.otf")


def test_every_clean_sample_is_in_the_font(font):
    order = set(TTFont(font).getGlyphOrder())
    assert {"a", "a.alt1", "a.alt2", "b", "b.alt1", "c", "d"} <= order
    assert not {"c.alt1", "d.alt1", "d.alt2"} & order  # no 2nd sample of c; d's edge-touching ones left out


def test_typing_gives_the_normal_glyph(font):
    assert TTFont(font).getBestCmap()[ord("a")] == "a"


def test_repeated_letters_cycle_through_the_samples(font):
    assert glyph_names(font, "aaaa") == ["a", "a.alt1", "a.alt2", "a"]


def test_the_cycle_runs_across_different_letters(font):
    assert glyph_names(font, "abab") == ["a", "b.alt1", "a.alt2", "b"]


def test_a_letter_with_two_samples_skips_the_missing_third(font):
    assert glyph_names(font, "bbb") == ["b", "b.alt1", "b"]


def test_every_word_starts_fresh(font):
    assert glyph_names(font, "aa aa") == ["a", "a.alt1", "space", "a", "a.alt1"]


def test_rotation_can_be_switched_off(font):
    assert glyph_names(font, "aaa", variants=False) == ["a", "a", "a"]


def test_preview_shows_the_variants(font):
    on = np.array(render(font, "aaa").convert("L"))
    off = np.array(render(font, "aaa", variants=False).convert("L"))
    assert on.shape[1] > off.shape[1]  # the alternates are wider in this test font


def test_samples_far_from_the_usual_size_are_pulled_in():
    a = [glyph("a", 0, height=460), glyph("a", 1, height=500), glyph("a", 2, height=700)]
    heights = []
    for g in even_out_sizes(a):
        bp = BoundsPen(None)
        g.outline.replay(bp)
        heights.append(bp.bounds[3] - bp.bounds[1])
        assert abs(bp.bounds[1]) < 1e-6  # still sitting on the baseline
    assert heights[0] == pytest.approx(460) and heights[1] == pytest.approx(500)  # within ±10%: untouched
    assert heights[2] == pytest.approx(550)  # 700 pulled to median 500 + 10%


def test_tailed_letters_keep_their_top_when_resized():
    g = [glyph("g", i, height=h, bottom=480 - h) for i, h in enumerate((600, 650, 900))]
    tops = []
    for out in even_out_sizes(g):
        bp = BoundsPen(None)
        out.outline.replay(bp)
        tops.append(bp.bounds[3])
    assert tops == pytest.approx([480, 480, 480])


def test_samples_are_kept_in_order_and_clean_first():
    gs = [glyph("x", 2), glyph("x", 0, clean=False), glyph("x", 1)]
    assert [g.sample for g in samples_by_char(gs)["x"]] == [1, 2]
