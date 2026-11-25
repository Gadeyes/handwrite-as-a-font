"""Font + text -> image. Used by the tests now and by evaluation (Phase 2) later.

    python -m hwfont.render MyFont.otf "The quick brown fox" -o preview.png
    python -m hwfont.render MyFont.otf -o charset.png          # every character

Pillow's basic text layout is used: no kerning and no OpenType features.
Phase 1's rotating variants need a shaping engine (HarfBuzz) to show up here.
"""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from hwfont import layout as L

GUIDE = (150, 190, 240)


def render(font_path: Path, text: str, size: int = 96, guides: bool = False) -> Image.Image:
    """Draw text (newlines allowed) in black on white, with an optional blue baseline per line."""
    font = ImageFont.truetype(str(font_path), size)
    ascent, descent = font.getmetrics()
    line_h = ascent + descent
    lines = text.split("\n")
    pad = size // 4
    width = max(1, *(round(font.getlength(line)) for line in lines))
    img = Image.new("RGB", (width + 2 * pad, line_h * len(lines) + 2 * pad), "white")
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        baseline = pad + i * line_h + ascent
        if guides:
            d.line([(0, baseline), (img.width, baseline)], fill=GUIDE, width=max(1, size // 48))
        d.text((pad, baseline), line, font=font, fill="black", anchor="ls")  # left, on the baseline
    return img


def charset_text(per_line: int = 20) -> str:
    chars = L.CHARACTERS
    return "\n".join(chars[i:i + per_line] for i in range(0, len(chars), per_line))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("font", type=Path)
    ap.add_argument("text", nargs="?", help="text to draw (default: every template character)")
    ap.add_argument("-o", "--out", type=Path, default=Path("data/preview.png"))
    ap.add_argument("--size", type=int, default=96, help="pixels per em (default: 96)")
    args = ap.parse_args()
    img = render(args.font, args.text or charset_text(), args.size, guides=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    img.save(args.out)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
