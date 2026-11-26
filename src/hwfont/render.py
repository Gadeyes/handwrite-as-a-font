"""Font + text -> image, the way a real app would show it. Used for previews and tests.

    python -m hwfont.render MyFont.otf "The quick brown fox" -o preview.png
    python -m hwfont.render MyFont.otf -o charset.png          # every character, all its variants

Two steps, like a browser or Word: HarfBuzz shapes the text (applies the
font's OpenType rules, so rotating variants show up, and works out where each
glyph goes), then FreeType draws each glyph. Pillow's own text drawing skips
the first step on most Windows installs, so variants would never appear.
"""

import argparse
import io
import math
from pathlib import Path

import freetype
import numpy as np
import uharfbuzz as hb
from PIL import Image, ImageDraw

from hwfont import layout as L

GUIDE = (150, 190, 240)


def shape(hb_font: hb.Font, line: str, variants: bool = True):
    """Glyph ids and positions (in font units) for one line of text."""
    buf = hb.Buffer()
    buf.add_str(line)
    buf.guess_segment_properties()
    hb.shape(hb_font, buf, {"calt": variants})
    return buf.glyph_infos or [], buf.glyph_positions or []  # None, not [], for an empty line


def glyph_names(font_path: Path, text: str, variants: bool = True) -> list[str]:
    """Which glyphs a text turns into, e.g. ['a', 'a.alt1', 'a.alt2']. For tests and debugging."""
    from fontTools.ttLib import TTFont
    order = TTFont(font_path).getGlyphOrder()
    hb_font = hb.Font(hb.Face(hb.Blob(Path(font_path).read_bytes())))
    infos, _ = shape(hb_font, text, variants)
    return [order[i.codepoint] for i in infos]


def _paste_max(canvas: np.ndarray, tile: np.ndarray, left: int, top: int) -> None:
    """Combine a glyph's coverage into the canvas (overlapping letters stay dark), clipped to the edges."""
    h, w = tile.shape
    y0, x0 = max(top, 0), max(left, 0)
    y1, x1 = min(top + h, canvas.shape[0]), min(left + w, canvas.shape[1])
    if y0 < y1 and x0 < x1:
        region = canvas[y0:y1, x0:x1]
        np.maximum(region, tile[y0 - top:y1 - top, x0 - left:x1 - left], out=region)


def render(font_path: Path, text: str, size: int = 96, guides: bool = False, variants: bool = True) -> Image.Image:
    """Draw text (newlines allowed) in black on white, with an optional blue baseline per line.

    size is pixels per em. variants=False turns the rotation off, to compare.
    """
    data = Path(font_path).read_bytes()
    hb_font = hb.Font(hb.Face(hb.Blob(data)))  # positions come out in font units
    scale = size / hb_font.face.upem
    extents = hb_font.get_font_extents("ltr")
    ascent, descent = math.ceil(extents.ascender * scale), math.ceil(-extents.descender * scale)

    ft = freetype.Face(io.BytesIO(data))  # from memory: FreeType can't open non-ASCII Windows paths
    ft.set_pixel_sizes(0, size)

    lines = [shape(hb_font, line, variants) for line in text.split("\n")]
    line_h, pad = ascent + descent, size // 4
    width = max(1, *(round(sum(p.x_advance for p in pos) * scale) for _, pos in lines))
    ink = np.zeros((line_h * len(lines) + 2 * pad, width + 2 * pad), np.uint8)

    baselines = []
    for i, (infos, positions) in enumerate(lines):
        baseline = pad + i * line_h + ascent
        baselines.append(baseline)
        x = float(pad)
        for info, pos in zip(infos, positions):
            ft.load_glyph(info.codepoint, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
            g, bm = ft.glyph, ft.glyph.bitmap
            if bm.rows and bm.width:
                tile = np.array(bm.buffer, np.uint8).reshape(bm.rows, bm.pitch)[:, :bm.width]
                left = round(x + pos.x_offset * scale) + g.bitmap_left
                top = baseline - round(pos.y_offset * scale) - g.bitmap_top
                _paste_max(ink, tile, left, top)
            x += pos.x_advance * scale

    img = Image.new("RGB", (ink.shape[1], ink.shape[0]), "white")
    if guides:
        d = ImageDraw.Draw(img)
        for baseline in baselines:
            d.line([(0, baseline), (img.width, baseline)], fill=GUIDE, width=max(1, size // 48))
    rgb = np.asarray(img, np.float32) * (1 - ink[..., None] / 255.0)  # ink darkens whatever is below
    return Image.fromarray(rgb.round().astype(np.uint8))


def charset_text(per_line: int = 20) -> str:
    chars = L.CHARACTERS
    return "\n".join(chars[i:i + per_line] for i in range(0, len(chars), per_line))


def variants_text(per_line: int = 10) -> str:
    """'aaa bbb ccc ...': each character typed once per sample, so the rotation shows every variant."""
    groups = [ch * L.SAMPLES_PER_CHAR for ch in L.CHARACTERS]
    return "\n".join(" ".join(groups[i:i + per_line]) for i in range(0, len(groups), per_line))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("font", type=Path)
    ap.add_argument("text", nargs="?", help="text to draw (default: every character, all its variants)")
    ap.add_argument("-o", "--out", type=Path, default=Path("data/preview.png"))
    ap.add_argument("--size", type=int, default=96, help="pixels per em (default: 96)")
    ap.add_argument("--no-variants", action="store_true", help="turn the rotation off, to compare")
    args = ap.parse_args()
    img = render(args.font, args.text or variants_text(), args.size, guides=True, variants=not args.no_variants)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    img.save(args.out)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
