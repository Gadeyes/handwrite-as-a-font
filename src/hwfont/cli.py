"""Command line: hwfont template | hwfont build.

    hwfont template                           # data/template.pdf: print, fill in, photograph
    hwfont build page1.jpg page2.jpg page3.jpg
    hwfont build *.jpg --name "My Handwriting" --cuts data/cuts

Photos can be in any order and any way up; each page identifies itself.
"""

import argparse
import sys
import time
from pathlib import Path

from hwfont.pipeline import make_font
from hwfont.template import write_template


def cmd_template(args) -> int:
    pages = write_template(args.out)
    print(f"wrote {args.out} ({len(pages)} pages). Print it, fill it in, photograph each page.")
    return 0


def cmd_build(args) -> int:
    # Word keeps showing a cached copy of a font it has seen under the same
    # name, so the default name changes on every build.
    family = args.name or f"My Handwriting {time.strftime('%m%d-%H%M')}"
    result = make_font(args.photos, family, args.out, args.cuts)

    print(f"pages found: {', '.join(map(str, result.pages_found)) or 'none'}")
    for problem in result.problems:
        print(f"  ! {problem}")
    if result.missing_chars:
        print(f"  ! not in the font: {' '.join(result.missing_chars)}")
    if result.font is None:
        print("no font built: nothing usable was found in the photos")
        return 1
    print(f"font:    {result.font}   (family name in Word: {family!r})")
    print(f"preview: {result.preview}")
    if args.cuts:
        print(f"cuts:    {args.cuts}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="hwfont", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    t = sub.add_parser("template", help="write the printable template PDF")
    t.add_argument("-o", "--out", type=Path, default=Path("data/template.pdf"))
    t.set_defaults(run=cmd_template)

    b = sub.add_parser("build", help="photos of filled-in pages -> .otf font")
    b.add_argument("photos", type=Path, nargs="+")
    b.add_argument("--name", help="font name as it appears in Word (default: dated, so Word never shows a stale copy)")
    b.add_argument("-o", "--out", type=Path, default=Path("data/fonts"), help="folder for the font and preview")
    b.add_argument("--cuts", type=Path, help="also save every cut-out box here, to inspect by eye")
    b.set_defaults(run=cmd_build)

    args = ap.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
