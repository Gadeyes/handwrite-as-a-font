"""Glyph outlines -> installable .otf font.

Every clean sample of a character goes into the font: the first as the
normal glyph (`a`), the others as alternates (`a.alt1`, `a.alt2`). An
OpenType rule (`calt`) rotates through them as you type, so a repeated
letter doesn't look copy-pasted.
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


def samples_by_char(glyphs: list[Glyph]) -> dict[str, list[Glyph]]:
    """The samples to put in the font, per character, in sample order.

    Samples that touched the box edge may be cut off, so they're only used
    when a character has no clean sample at all (and then just one of them).
    """
    grouped: dict[str, list[Glyph]] = {}
    for g in sorted(glyphs, key=lambda g: g.sample):
        grouped.setdefault(g.char, []).append(g)
    return {c: [g for g in gs if g.clean] or gs[:1] for c, gs in grouped.items()}


def variant_name(char: str, index: int) -> str:
    return glyph_name(char) + (f".alt{index}" if index else "")


def rotation_feature(names: list[list[str]]) -> str:
    """OpenType rules (feature-file syntax) that rotate each character through its samples.

    A font can't pick at random, so the choice depends on the glyph before it:
    after a normal glyph comes .alt1, after an .alt1 comes .alt2, after that
    the normal one again. The rules run left to right and see the swaps they
    have already made, which is what moves the cycle along. A space is not in
    the cycle, so every word starts with the normal glyphs.
    Returns "" when no character has a second sample.
    """
    def cls(glyphs):  # a backslash stops a glyph name being read as a keyword
        return "[" + " ".join(f"\\{g}" for g in glyphs) + "]"

    with1 = [ns for ns in names if len(ns) > 1]
    with2 = [ns for ns in names if len(ns) > 2]
    if not with1:
        return ""
    rules = [f"sub {cls(ns[0] for ns in names)} {cls(ns[0] for ns in with1)}' by {cls(ns[1] for ns in with1)};"]
    if with2:
        rules.append(f"sub {cls(ns[1] for ns in with1)} {cls(ns[0] for ns in with2)}' by {cls(ns[2] for ns in with2)};")
    body = "\n    ".join(rules)
    return f"languagesystem DFLT dflt;\nlanguagesystem latn dflt;\n\nfeature calt {{\n    {body}\n}} calt;\n"


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
    samples = samples_by_char(glyphs)
    if not samples:
        raise ValueError("no usable glyphs to build a font from")
    chosen = {char: gs[0] for char, gs in samples.items()}  # the normal glyph of each character

    charstrings = {".notdef": notdef(500), "space": T2CharStringPen(SPACE_WIDTH, None).getCharString()}
    advances = {".notdef": 500, "space": SPACE_WIDTH}
    cmap = {0x20: "space"}
    tops, bottoms = [], []
    names: list[list[str]] = []
    for char, gs in samples.items():
        names.append([])
        for i, g in enumerate(gs):
            x_min, y_min, x_max, y_max = _bounds(g)
            advance = round(SIDE_BEARING + x_max + SIDE_BEARING)
            pen = T2CharStringPen(advance, None)
            g.outline.replay(TransformPen(pen, (1, 0, 0, 1, SIDE_BEARING, 0)))  # shift right by the bearing
            name = variant_name(char, i)
            charstrings[name], advances[name] = pen.getCharString(), advance
            names[-1].append(name)
            tops.append(y_max)
            bottoms.append(y_min)
        cmap[ord(char)] = names[-1][0]  # typing the character gives the normal glyph; calt swaps it

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
    features = rotation_feature(names)
    if features:
        fb.addOpenTypeFeatures(features)
    out.parent.mkdir(parents=True, exist_ok=True)
    fb.save(str(out))
    return out
