"""Ink images -> smooth outlines in font units.

One scale is used for every glyph, measured from the writer's own capitals,
so letters keep their real proportions to each other. Each outline comes out
with the ink's left edge at x = 0 and the baseline at y = 0; build.py adds the
spacing around it.
"""

from dataclasses import dataclass
from statistics import median

import numpy as np
import potrace
from fontTools.pens.areaPen import AreaPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.reverseContourPen import ReverseContourPen

from hwfont import layout as L
from hwfont.scan import PX_PER_MM
from hwfont.slice import MIN_SPECK_PX, OK, Cut

CAP_HEIGHT = 700  # font units; the usual cap height in a 1000-unit em
X_HEIGHT = 480    # used for the scale only when there are no capitals to measure

# Capitals whose ink height is exactly the cap height (no round overshoot, no tail).
FLAT_CAPS = set("BDEFHIKLMNPRTXZ")
# Small letters whose ink height is exactly the x-height.
FLAT_SMALL = set("mnruvwxz")
# Characters whose ink should rest on the baseline. Snapping them removes the
# up-and-down drift of handwriting; anything with a tail is left as written.
SITS_ON_BASELINE = set(L.CHARACTERS) - set("gjpqyQJ") - set(L.PUNCTUATION) | set(".!?")
SNAP_MAX_MM = 2.0  # a bigger gap than this is probably deliberate, so leave it alone


@dataclass
class Glyph:
    char: str
    sample: int
    clean: bool           # False if the writing touched the box edge
    outline: RecordingPen  # font units: ink starts at x = 0, baseline at y = 0


def _ink_height(cut: Cut) -> int:
    rows = np.nonzero(cut.ink.any(axis=1))[0]
    return int(rows[-1] + 1 - rows[0])


def measure_scale(cuts: list[Cut]) -> float:
    """Font units per pixel, from the median height of the writer's flat capitals."""
    usable = [c for c in cuts if c.status == OK and c.box.sample is not None]
    caps = [_ink_height(c) for c in usable if c.box.text in FLAT_CAPS]
    if caps:
        return CAP_HEIGHT / median(caps)
    small = [_ink_height(c) for c in usable if c.box.text in FLAT_SMALL]
    if small:
        return X_HEIGHT / median(small)
    return CAP_HEIGHT / ((L.BASELINE_Y - L.ASCENDER_Y) * PX_PER_MM)  # the printed guides


def trace(ink: np.ndarray, baseline_px: float, units_per_px: float) -> RecordingPen:
    """Trace an ink mask into outlines: ink's left edge at x = 0, baseline at y = 0.

    Outer contours run counter-clockwise and holes clockwise, as CFF fonts
    require. Flipping y (images count down, fonts count up) mirrors every
    contour and reverses its direction, so the result is checked and reversed
    if needed; otherwise the holes in a, e, o would fill in.
    """
    left = np.nonzero(ink.any(axis=0))[0][0]

    def to_font(p):
        return ((p.x - left) * units_per_px, (baseline_px - p.y) * units_per_px)

    # potracer traces the False pixels as the shape, so hand it "not ink".
    path = potrace.Bitmap(~ink).trace(turdsize=MIN_SPECK_PX)
    rec = RecordingPen()
    for curve in path.curves:
        rec.moveTo(to_font(curve.start_point))
        for seg in curve.segments:
            if seg.is_corner:
                rec.lineTo(to_font(seg.c))
                rec.lineTo(to_font(seg.end_point))
            else:
                rec.curveTo(to_font(seg.c1), to_font(seg.c2), to_font(seg.end_point))
        rec.closePath()

    area = AreaPen()
    rec.replay(area)
    if area.value >= 0:  # positive = counter-clockwise outer contours already
        return rec
    fixed = RecordingPen()
    rec.replay(ReverseContourPen(fixed))
    return fixed


def baseline_for(cut: Cut) -> float:
    """The guide baseline, or the bottom of the ink for characters that should rest on it."""
    if cut.box.text not in SITS_ON_BASELINE:
        return cut.baseline_px
    bottom = np.nonzero(cut.ink.any(axis=1))[0][-1] + 1
    if abs(bottom - cut.baseline_px) <= SNAP_MAX_MM * PX_PER_MM:
        return float(bottom)
    return cut.baseline_px


def vectorize(cuts: list[Cut]) -> list[Glyph]:
    """Trace every usable character sample, all at one shared scale."""
    units_per_px = measure_scale(cuts)
    return [
        Glyph(c.box.text, c.box.sample, c.status == OK, trace(c.ink, baseline_for(c), units_per_px))
        for c in cuts
        if c.usable and c.box.sample is not None
    ]
