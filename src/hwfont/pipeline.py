"""The whole chain in one call: photos of filled-in pages -> font + preview.

No printing and no command-line parsing here, so the CLI and (later) the
website can both call make_font() and present the result their own way.
"""

from dataclasses import dataclass, field
from pathlib import Path

from hwfont import layout as L
from hwfont.build import build_font
from hwfont.render import charset_text, render
from hwfont.scan import ScanError, load_image, scan
from hwfont.slice import Cut, report, save_cuts, slice_page
from hwfont.vectorize import vectorize

PREVIEW_TEXT = "The quick brown fox jumps over the lazy dog.\nPack my box with five dozen liquor jugs!"


@dataclass
class FontResult:
    font: Path | None = None
    preview: Path | None = None
    pages_found: list[int] = field(default_factory=list)   # 1-based page numbers
    problems: list[str] = field(default_factory=list)      # worth showing the writer
    missing_chars: list[str] = field(default_factory=list)


def make_font(photos: list[Path], family: str, out_dir: Path, cuts_dir: Path | None = None) -> FontResult:
    pages = L.build_layout()
    result = FontResult()
    cuts_by_page: dict[int, list[Cut]] = {}

    for photo in photos:
        try:
            scanned = scan(load_image(photo), pages)
        except ScanError as e:
            result.problems.append(f"{photo.name}: {e}")
            continue
        if scanned.index in cuts_by_page:
            result.problems.append(f"{photo.name}: page {scanned.index + 1} again; using this photo instead")
        cuts_by_page[scanned.index] = slice_page(scanned, pages)

    result.pages_found = sorted(i + 1 for i in cuts_by_page)
    missing_pages = [i + 1 for i in range(len(pages)) if i not in cuts_by_page]
    if missing_pages:
        result.problems.append(f"no photo of page {', '.join(map(str, missing_pages))}")

    cuts = [c for i in sorted(cuts_by_page) for c in cuts_by_page[i]]
    result.problems += report(cuts)
    if cuts_dir is not None:
        save_cuts(cuts, cuts_dir)

    glyphs = vectorize(cuts)
    have = {g.char for g in glyphs}
    result.missing_chars = [c for c in L.CHARACTERS if c not in have]
    if not glyphs:
        return result

    stem = "".join(ch if ch.isalnum() else "-" for ch in family)
    result.font = build_font(glyphs, family, out_dir / f"{stem}.otf")
    result.preview = out_dir / f"{stem}-preview.png"
    render(result.font, charset_text() + "\n\n" + PREVIEW_TEXT, size=72, guides=True).save(result.preview)
    return result
