"""Phase 0 spike: one handwritten letter -> installable .otf.

Throwaway script. Its job is to expose surprises, not to be the design.
Stages map onto the future modules: scan/slice -> vectorize -> build -> render.

    python spike/spike.py data/spike/a.png
    python spike/spike.py data/spike/a.png --char a --name "HW Spike 2"

Writes into data/spike/ (git-ignored):
    1_ink.png      what the tracer sees (black = ink)
    <name>.otf     the font: install it, then type the letter in Word
    3_preview.png  the font rendered by FreeType, with baseline + x-height lines
"""

import argparse
import time
from pathlib import Path

import cv2
import numpy as np
import potrace
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.areaPen import AreaPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.reverseContourPen import ReverseContourPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from PIL import Image, ImageDraw, ImageFont

UPM = 1000          # font units per em; 1000 is the convention for CFF (.otf)
ASCENT, DESCENT = 800, -200
SIDE_BEARING = 50   # empty space left and right of the glyph, in font units


# --- scan: image -> ink mask + baseline --------------------------------------

def load_ink(path: Path) -> np.ndarray:
    """Return a bool mask, True where there is ink."""
    gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise SystemExit(f"cannot read image: {path}")
    # Otsu picks the cut-off between the dark (ink) and light (paper) peaks.
    # Light guide lines (blue ~190, grey ~200) land on the paper side and vanish.
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary == 0


def find_baseline(path: Path) -> float | None:
    """Row of the blue guide line, or None if there is none."""
    hsv = cv2.cvtColor(cv2.imread(str(path), cv2.IMREAD_COLOR), cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    # OpenCV hue runs 0-180; blue is ~100-130. The value check drops near-black
    # ink pixels, whose hue is noise.
    blue = (h > 90) & (h < 130) & (s > 40) & (v > 100)
    counts = blue.sum(axis=1)
    if counts.max() < 0.1 * blue.shape[1]:  # not a line across the cell
        return None
    rows = np.nonzero(counts >= 0.5 * counts.max())[0]
    return float(rows.mean())  # centre of the (several px thick) line


# --- vectorize: ink mask -> Bezier outlines in font units --------------------

def trace(ink: np.ndarray, baseline_px: float, x_height: int) -> RecordingPen:
    ys, xs = np.nonzero(ink)
    left, top = xs.min(), ys.min()
    # The letter's top-to-baseline distance becomes the x-height.
    scale = x_height / (baseline_px - top)

    def to_font(p):
        # Image y points down from the top; font y points up from the baseline.
        return ((p.x - left) * scale + SIDE_BEARING, (baseline_px - p.y) * scale)

    # potracer traces the False pixels as the shape, so hand it "not ink".
    path = potrace.Bitmap(~ink).trace(turdsize=10)

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
    print(f"traced {len(path.curves)} contour(s); scale {scale:.2f} units/px")
    return rec


def draw_upright(rec: RecordingPen, pen) -> None:
    """Replay outlines so outer contours run counter-clockwise (CFF convention).

    The y-flip in trace() mirrors every contour, which reverses its direction.
    Positive signed area means counter-clockwise, so reverse if it is negative.
    """
    area = AreaPen()
    rec.replay(area)
    rec.replay(ReverseContourPen(pen) if area.value < 0 else pen)


# --- build: outlines + metrics -> .otf ---------------------------------------

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


def build_font(rec: RecordingPen, char: str, family: str, x_height: int, out: Path) -> None:
    # Plain ASCII letters/digits can be their own glyph name; anything else uses uniXXXX.
    glyph = char if char.isascii() and char.isalnum() else f"uni{ord(char):04X}"

    bp = BoundsPen(None)
    rec.replay(bp)
    advance = round(bp.bounds[2] + SIDE_BEARING)  # right edge of the ink + margin

    pen = T2CharStringPen(advance, None)
    draw_upright(rec, pen)

    charstrings = {
        ".notdef": notdef(500),
        "space": T2CharStringPen(250, None).getCharString(),
        glyph: pen.getCharString(),
    }
    advances = {".notdef": 500, "space": 250, glyph: advance}

    fb = FontBuilder(UPM, isTTF=False)
    fb.setupGlyphOrder(list(charstrings))
    fb.setupCharacterMap({0x20: "space", ord(char): glyph})
    ps_name = family.replace(" ", "") + "-Regular"
    fb.setupCFF(ps_name, {"FullName": f"{family} Regular"}, charstrings, {})
    # In CFF fonts the left side bearing in hmtx must equal the glyph's xMin.
    lsb = {name: (cs.calcBounds(None) or (0,))[0] for name, cs in charstrings.items()}
    fb.setupHorizontalMetrics({name: (advances[name], lsb[name]) for name in charstrings})
    fb.setupHorizontalHeader(ascent=ASCENT, descent=DESCENT)
    fb.setupNameTable({
        "familyName": family,
        "styleName": "Regular",
        "uniqueFontIdentifier": f"{ps_name};{time.strftime('%Y%m%d%H%M%S')}",
        "fullName": f"{family} Regular",
        "psName": ps_name,
        "version": "Version 0.001",
    })
    fb.setupOS2(
        sTypoAscender=ASCENT, sTypoDescender=DESCENT, sTypoLineGap=0,
        usWinAscent=ASCENT, usWinDescent=-DESCENT,
        sxHeight=x_height, sCapHeight=700,
        fsType=0,  # installable embedding, so Word can embed it in documents
        # Bit 0 = "supports Latin 1 (Western European)". Without it Word lists the
        # font but silently draws Courier New instead. FreeType/Pillow ignore this
        # field, so the preview image cannot catch the problem.
        ulCodePageRange1=1,
    )
    fb.setupPost()
    fb.save(str(out))


# --- render: font -> preview image -------------------------------------------

def preview(font_path: Path, char: str, x_height: int, out: Path) -> None:
    size = 200  # px per em
    font = ImageFont.truetype(str(font_path), size)
    img = Image.new("RGB", (900, 320), "white")
    d = ImageDraw.Draw(img)
    baseline = 230
    xh = baseline - x_height * size / UPM
    d.line([(0, baseline), (900, baseline)], fill=(120, 160, 230), width=2)
    d.line([(0, xh), (900, xh)], fill=(220, 220, 220), width=2)
    # "ls" anchor = left edge, on the baseline: tails should dip below the blue line.
    d.text((40, baseline), f"{char}{char}{char} {char}", font=font, fill="black", anchor="ls")
    img.save(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", type=Path)
    ap.add_argument("--char", default="a", help="character this drawing is (default: a)")
    ap.add_argument("--name", default=f"HW Spike {time.strftime('%H%M')}",
                    help="font family name; change it on every rebuild so Word "
                         "cannot show you a cached old version")
    ap.add_argument("--x-height", type=int, default=500, help="in font units (default: 500)")
    ap.add_argument("--out", type=Path, default=Path("data/spike"))
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    ink = load_ink(args.image)
    cv2.imwrite(str(args.out / "1_ink.png"), np.where(ink, 0, 255).astype(np.uint8))

    baseline = find_baseline(args.image)
    if baseline is None:
        baseline = float(np.nonzero(ink)[0].max())
        print("no blue guide line found: using the bottom of the ink as the baseline")
    else:
        print(f"baseline from guide line at row {baseline:.1f}")

    rec = trace(ink, baseline, args.x_height)
    font_path = args.out / f"{args.name.replace(' ', '-')}.otf"
    build_font(rec, args.char, args.name, args.x_height, font_path)
    preview(font_path, args.char, args.x_height, args.out / "3_preview.png")
    print(f"font:    {font_path}   (family name: {args.name!r})")
    print(f"preview: {args.out / '3_preview.png'}")


if __name__ == "__main__":
    main()
