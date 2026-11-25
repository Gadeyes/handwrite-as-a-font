"""Glyph outlines -> installable .otf font.

One glyph per character for now: the first clean sample. Phase 1 adds the
other samples as alternates that rotate as you type.
"""

import math
import time
from pathlib import Path
from statistics import median

from fontTools.agl import UV2AGL
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen

from hwfont.vectorize import CAP_HEIGHT, FLAT_CAPS, FLAT_SMALL, Glyph

UPM = 1000           # font units per em; 1000 is the convention for CFF (.otf)
SIDE_BEARING = 50    # empty space left and right of each glyph, in font units
SPACE_WIDTH = 300
MIN_ASCENT, MIN_DESCENT = 800, -200  # never tighter than this, even for a font of small letters


def glyph_name(char: str) -> str:
    """Standard names (a, A, period, quotedbl ...) so PDFs keep copy-paste text."""
    return UV2AGL.get(ord(char), f"uni{ord(char):04X}")


def pick(glyphs: list[Glyph]) -> dict[str, Glyph]:
    """One glyph per character: the first clean sample, else the first of any."""
    chosen: dict[str, Glyph] = {}
    for g in sorted(glyphs, key=lambda g: (not g.clean, g.sample)):
        chosen.setdefault(g.char, g)
    return chosen


def _bounds(glyph: Glyph) -> tuple[float, float, float, float]:
    bp = BoundsPen(None)
    glyph.outline.replay(bp)
    return bp.bounds or (0, 0, 0, 0)


def notdef(width: int):
    """The box shown for characters the font does not have."""
    pen = T2CharStringPen(width, None)
    for (x0, y0, x1, y1), ccw in (((50, 0, 450, 700), True), ((100, 50, 400, 650), False)):
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        pts = pts if ccw else pts[::-1]
        pen.moveTo(pts[0])
        for p in pts[1:]:
            pen.lineTo(p)
        pen.closePath()
    return pen.getCharString()


def build_font(glyphs: list[Glyph], family: str, out: Path) -> Path:
    chosen = pick(glyphs)
    if not chosen:
        raise ValueError("no usable glyphs to build a font from")

    charstrings = {".notdef": notdef(500), "space": T2CharStringPen(SPACE_WIDTH, None).getCharString()}
    advances = {".notdef": 500, "space": SPACE_WIDTH}
    cmap = {0x20: "space"}
    tops, bottoms = [], []
    for char, g in chosen.items():
        x_min, y_min, x_max, y_max = _bounds(g)
        advance = round(SIDE_BEARING + x_max + SIDE_BEARING)
        pen = T2CharStringPen(advance, None)
        g.outline.replay(TransformPen(pen, (1, 0, 0, 1, SIDE_BEARING, 0)))  # shift right by the bearing
        name = glyph_name(char)
        charstrings[name], advances[name], cmap[ord(char)] = pen.getCharString(), advance, name
        tops.append(y_max)
        bottoms.append(y_min)

    # Line metrics must cover the tallest and deepest glyph, or Windows clips them.
    # Round outwards: a curve's extreme can fall between whole units.
    ascent = math.ceil(max(MIN_ASCENT, *tops))
    descent = math.floor(min(MIN_DESCENT, *bottoms))
    x_height = round(median([_bounds(g)[3] for c, g in chosen.items() if c in FLAT_SMALL] or [500]))
    cap_height = round(median([_bounds(g)[3] for c, g in chosen.items() if c in FLAT_CAPS] or [CAP_HEIGHT]))

    fb = FontBuilder(UPM, isTTF=False)
    fb.setupGlyphOrder(list(charstrings))
    fb.setupCharacterMap(cmap)
    ps_name = "".join(ch for ch in family if ch.isalnum()) + "-Regular"
    fb.setupCFF(ps_name, {"FullName": f"{family} Regular"}, charstrings, {})
    # In CFF fonts the left side bearing in hmtx must equal the glyph's xMin.
    lsb = {name: (cs.calcBounds(None) or (0,))[0] for name, cs in charstrings.items()}
    fb.setupHorizontalMetrics({name: (advances[name], lsb[name]) for name in charstrings})
    fb.setupHorizontalHeader(ascent=ascent, descent=descent)
    fb.setupNameTable({
        "familyName": family,
        "styleName": "Regular",
        "uniqueFontIdentifier": f"{ps_name};{time.strftime('%Y%m%d%H%M%S')}",
        "fullName": f"{family} Regular",
        "psName": ps_name,
        "version": "Version 0.001",
    })
    fb.setupOS2(
        sTypoAscender=ascent, sTypoDescender=descent, sTypoLineGap=0,
        usWinAscent=ascent, usWinDescent=-descent,
        sxHeight=x_height, sCapHeight=cap_height,
        fsType=0,  # installable embedding, so Word can embed it in documents
        # Bit 0 = "supports Latin 1". Without it Word lists the font but silently
        # draws Courier New instead; FreeType previews cannot catch this.
        ulCodePageRange1=1,
    )
    fb.setupPost()
    out.parent.mkdir(parents=True, exist_ok=True)
    fb.save(str(out))
    return out
