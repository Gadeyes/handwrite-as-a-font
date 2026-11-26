"""Straightened page -> one labelled ink image per box.

This is the hand-off between the paper side and the font side. Each Cut
says which character it is, which sample, whether it is usable, and where
the baseline sits inside the crop.
"""

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from hwfont import layout as L
from hwfont.scan import PX_PER_MM, ScannedPage

INSET_MM = 0.5         # skip the box edge itself: leftover border and small alignment errors
MIN_SPECK_PX = 15      # smaller ink blobs are noise (a quick full stop can be as little as ~30 px)
MIN_INK_PX = 40        # less than this in a whole box counts as empty...
TINY_MARKS = set(".,'")  # ...except for marks that are naturally just a dot or a flick

OK, EMPTY, OVERFLOW = "ok", "empty", "overflow"


@dataclass
class Cut:
    box: L.Box
    ink: np.ndarray       # bool crop of the box (inset), True = ink
    status: str           # OK, EMPTY or OVERFLOW (ink touches the edge: letter probably cut off)

    @property
    def baseline_px(self) -> float:
        """Row of the baseline guide inside the crop."""
        return (L.BASELINE_Y - INSET_MM) * PX_PER_MM

    @property
    def x_height_px(self) -> float:
        return (L.XHEIGHT_Y - INSET_MM) * PX_PER_MM

    @property
    def usable(self) -> bool:
        return self.status != EMPTY


def remove_specks(ink: np.ndarray, min_px: int = MIN_SPECK_PX) -> np.ndarray:
    """Drop connected blobs smaller than min_px (dust, noise, JPEG artefacts)."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), connectivity=8)
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_px  # label 0 is the background
    return keep[labels]


def cut_box(page: ScannedPage, box: L.Box) -> Cut:
    x0 = round((box.x + INSET_MM) * PX_PER_MM)
    y0 = round((box.y + INSET_MM) * PX_PER_MM)
    x1 = round((box.x + box.w - INSET_MM) * PX_PER_MM)
    y1 = round((box.y + box.h - INSET_MM) * PX_PER_MM)
    ink = remove_specks(page.ink[y0:y1, x0:x1])

    min_ink = MIN_SPECK_PX if box.text in TINY_MARKS else MIN_INK_PX
    if ink.sum() < min_ink:
        status = EMPTY
    elif ink[0].any() or ink[-1].any() or ink[:, 0].any() or ink[:, -1].any():
        status = OVERFLOW
    else:
        status = OK
    return Cut(box, ink, status)


def slice_page(page: ScannedPage, pages: list[L.Page] | None = None) -> list[Cut]:
    pages = pages if pages is not None else L.build_layout()
    return [cut_box(page, box) for box in pages[page.index].boxes]


def file_stem(cut: Cut) -> str:
    """A Windows-safe, case-safe name: u0061_a_0 for 'a', u0041_A_0 for 'A', u003F_0 for '?'."""
    box = cut.box
    if box.sample is None:
        return f"line_{L.SENTENCE_LINES.index(box.text) + 1}"
    readable = f"_{box.text}" if box.text.isascii() and box.text.isalnum() else ""
    return f"u{ord(box.text):04X}{readable}_{box.sample}"


def save_cuts(cuts: list[Cut], folder: Path) -> None:
    """Write every cut as a PNG (black ink on white), for looking at by eye."""
    folder.mkdir(parents=True, exist_ok=True)
    for cut in cuts:
        cv2.imwrite(str(folder / f"{file_stem(cut)}.png"), np.where(cut.ink, 0, 255).astype(np.uint8))


def report(cuts: list[Cut]) -> list[str]:
    """Plain-English problems worth showing the writer."""
    problems = [f"'{c.box.text}' sample {c.box.sample + 1}: writing touches the box edge"
                for c in cuts if c.status == OVERFLOW and c.box.sample is not None]
    chars = {c.box.text for c in cuts if c.box.sample is not None}
    for ch in sorted(chars):
        if not any(c.usable for c in cuts if c.box.text == ch and c.box.sample is not None):
            problems.append(f"'{ch}': all boxes are empty")
    return problems
