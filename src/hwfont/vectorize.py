"""Ink images -> smooth outlines in font units.

One scale is used for every glyph, measured from the writer's own capitals,
so letters keep their real proportions to each other. Each outline comes out
with the ink's left edge at x = 0 and the baseline at y = 0; build.py adds the
spacing around it.
"""

from dataclasses import dataclass, field, replace
from statistics import median

import numpy as np
import potrace
from fontTools.pens.areaPen import AreaPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.reverseContourPen import ReverseContourPen
from fontTools.pens.transformPen import TransformPen

from hwfont import layout as L
from hwfont.scan import PX_PER_MM
from hwfont.slice import MIN_SPECK_PX, OK, Cut

CAP_HEIGHT = 700  # font units; the usual cap height in a 1000-unit em
X_HEIGHT = 480    # used for the scale only when there are no capitals to measure

# Capitals whose ink height is exactly the cap height (no round overshoot, no tail).
FLAT_CAPS = set("BDEFHIKLMNPRTXZ")
# Small letters whose ink height is exactly the x-height.
FLAT_SMALL = set("mnruvwxz")
# Characters whose ink rests on the baseline. Their bottom edge *is* the
# baseline, wherever in the box the writer put them.
SITS_ON_BASELINE = set(L.CHARACTERS) - set("gjpqyQJ") - set(L.PUNCTUATION) | set(".!?:")
# Characters with a tail can't use their bottom edge. Their top edge sits at a
# height the writer shows elsewhere, so they hang from there instead:
# a 'g' is placed so its top is at the writer's x-height, measured on m, n, x...
HANGS_FROM_TOP = {
    **dict.fromkeys("gpqy", FLAT_SMALL),
    "j": {"i"},             # the dot to the baseline, like an 'i'
    **dict.fromkeys("QJ", FLAT_CAPS),
}
SIZE_SPREAD = 0.10  # samples of one character may differ in height by ±10% before being resized


@dataclass
class Glyph:
    char: str
    sample: int
    clean: bool           # False if the writing touched the box edge
    outline: RecordingPen  # font units: ink starts at x = 0, baseline at y = 0


def _ink_rows(cut: Cut) -> tuple[int, int]:
    """First ink row and the row just below the last one."""
    rows = np.nonzero(cut.ink.any(axis=1))[0]
    return int(rows[0]), int(rows[-1] + 1)


def _ink_height(cut: Cut) -> int:
    top, bottom = _ink_rows(cut)
    return bottom - top


@dataclass
class Habits:
    """Where this writer really puts things, measured from all their boxes.

    Many people don't rest letters on the printed line; they float them a
    couple of millimetres above it, or centre them in the box.
    """
    lift_px: float = 0.0                                 # letters rest this far above the printed line
    heights_px: dict[str, float] = field(default_factory=dict)  # median ink height per character


def measure_habits(cuts: list[Cut]) -> Habits:
    usable = [c for c in cuts if c.status == OK and c.box.sample is not None]
    lifts = [c.baseline_px - _ink_rows(c)[1] for c in usable
             if c.box.text in SITS_ON_BASELINE and c.box.text not in L.PUNCTUATION]
    heights: dict[str, list[int]] = {}
    for c in usable:
        heights.setdefault(c.box.text, []).append(_ink_height(c))
    return Habits(median(lifts) if lifts else 0.0, {ch: median(h) for ch, h in heights.items()})


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


def baseline_for(cut: Cut, habits: Habits | None = None) -> float:
    """Row inside the crop that becomes the font's baseline (y = 0)."""
    habits = habits or Habits()
    ch = cut.box.text
    top, bottom = _ink_rows(cut)
    if ch in SITS_ON_BASELINE:
        return float(bottom)
    refs = [habits.heights_px[r] for r in HANGS_FROM_TOP.get(ch, ()) if r in habits.heights_px]
    if refs:
        return top + median(refs)
    # Punctuation and anything without a reference: keep its height relative
    # to the writer's letters, i.e. move it by the same lift.
    return cut.baseline_px - habits.lift_px


def _outline_bounds(rec: RecordingPen) -> tuple[float, float, float, float]:
    bp = BoundsPen(None)
    rec.replay(bp)
    return bp.bounds or (0.0, 0.0, 0.0, 0.0)


def _anchor_y(char: str, y_min: float, y_max: float) -> float:
    """The height that must stay put when a sample is resized."""
    if char in SITS_ON_BASELINE:
        return 0.0                # still on the baseline
    if char in HANGS_FROM_TOP:
        return y_max              # still level with the x-height; the tail changes length
    return (y_min + y_max) / 2    # punctuation: stays at the same height


def even_out_sizes(glyphs: list[Glyph], spread: float = SIZE_SPREAD) -> list[Glyph]:
    """Pull samples of the same character to within ±spread of their median height.

    Real samples vary a lot (one writer's three a's: 6.3, 4.6 and 5.4 mm);
    in running text that reads as letters jumping in size. Shapes are kept,
    only the size of outliers changes.
    """
    heights: dict[str, list[float]] = {}
    for g in glyphs:
        y_min, y_max = _outline_bounds(g.outline)[1::2]
        heights.setdefault(g.char, []).append(y_max - y_min)
    typical = {ch: median(hs) for ch, hs in heights.items()}

    out = []
    for g in glyphs:
        _, y_min, _, y_max = _outline_bounds(g.outline)
        h, mid = y_max - y_min, typical[g.char]
        target = min(max(h, mid * (1 - spread)), mid * (1 + spread))
        if h <= 0 or target == h:
            out.append(g)
            continue
        s, ay = target / h, _anchor_y(g.char, y_min, y_max)
        scaled = RecordingPen()
        g.outline.replay(TransformPen(scaled, (s, 0, 0, s, 0, ay * (1 - s))))  # scale around (0, ay)
        out.append(replace(g, outline=scaled))
    return out


def vectorize(cuts: list[Cut]) -> list[Glyph]:
    """Trace every usable character sample, all at one shared scale."""
    units_per_px = measure_scale(cuts)
    habits = measure_habits(cuts)
    return even_out_sizes([
        Glyph(c.box.text, c.box.sample, c.status == OK, trace(c.ink, baseline_for(c, habits), units_per_px))
        for c in cuts
        if c.usable and c.box.sample is not None
    ])
