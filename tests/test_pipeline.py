"""Synthetic round trip: template -> fake photos -> scan -> slice -> vectorize -> font -> render.

Phase 0 is done when a real scan types legibly in Word with the tails of
g, p and y below the baseline. This checks the same things on fake photos.
"""

import numpy as np
import pytest
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont

pytest.importorskip("pypdfium2")

from fake_photo import photograph, render_page, write_in  # noqa: E402
from hwfont import layout as L  # noqa: E402
from hwfont.build import build_font, glyph_name  # noqa: E402
from hwfont.render import charset_text, render  # noqa: E402
from hwfont.scan import scan  # noqa: E402
from hwfont.slice import report, slice_page  # noqa: E402
from hwfont.template import write_template  # noqa: E402
from hwfont.vectorize import vectorize  # noqa: E402


@pytest.fixture(scope="module")
def font_path(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("pipeline")
    pages = write_template(tmp / "template.pdf")
    cuts = []
    for i in range(len(pages)):
        img = render_page(tmp / "template.pdf", i)
        write_in(img, [b for b in pages[i].boxes if b.sample == 0])  # one sample per character
        cuts += slice_page(scan(photograph(img, seed=10 + i), pages), pages)
    assert report(cuts) == []
    return build_font(vectorize(cuts), "HW Test", tmp / "HW-Test.otf")


def glyph_bounds(font: TTFont, char: str):
    gs = font.getGlyphSet()
    bp = BoundsPen(gs)
    gs[glyph_name(char)].draw(bp)
    return bp.bounds


def test_every_character_is_in_the_font(font_path):
    cmap = TTFont(font_path).getBestCmap()
    assert {chr(cp) for cp in cmap} >= set(L.CHARACTERS) | {" "}


def test_word_will_use_the_font(font_path):
    os2 = TTFont(font_path)["OS/2"]
    assert os2.ulCodePageRange1 & 1  # without it Word swaps in Courier New
    assert os2.fsType == 0


def test_tails_hang_below_the_baseline(font_path):
    font = TTFont(font_path)
    for char in "gpy":
        assert glyph_bounds(font, char)[1] < -100, char
    for char in "xnH":
        assert abs(glyph_bounds(font, char)[1]) < 15, char  # snapped onto the baseline


def test_line_metrics_cover_every_glyph(font_path):
    font = TTFont(font_path)
    hhea = font["hhea"]
    for char in L.CHARACTERS:
        _, y_min, _, y_max = glyph_bounds(font, char)
        assert hhea.descent <= y_min and y_max <= hhea.ascent, char


def test_renders_as_text(font_path):
    img = np.array(render(font_path, charset_text()).convert("L"))
    ink = img < 128
    assert ink.mean() > 0.05  # clearly drawn, not blank or .notdef boxes
