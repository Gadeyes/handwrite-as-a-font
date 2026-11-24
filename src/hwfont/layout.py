"""Where everything sits on the template pages.

This is the one description both halves of the pipeline share: template.py
draws the pages from it, and the scan/slice side uses it to find each box
again in a photo. Change it and every printed sheet already filled in stops
matching, so treat it as a contract.

All lengths are millimetres, measured from the page's top-left corner with
y pointing DOWN, the way image pixels are addressed. A straightened scan
then maps onto these numbers with a single scale factor.
"""

import string
from dataclasses import dataclass, field

# --- what gets written -------------------------------------------------------

PUNCTUATION = ".,;:!?'\"-()/&@#%+="
CHARACTERS = string.ascii_lowercase + string.ascii_uppercase + string.digits + PUNCTUATION
SAMPLES_PER_CHAR = 3  # real variants to rotate between, before any model exists

# Free writing for the style-reference models in Phase 1. Each entry is one
# line on the page, short enough to fit at the cell's writing size.
SENTENCE_LINES = (
    "The quick brown fox",
    "jumps over the lazy dog.",
    "Pack my box with five",
    "dozen liquor jugs!",
)

# Printed next to labels that are easy to misread or too small to see.
HINTS = {
    "l": "small L", "I": "capital i", "1": "one",
    "o": "small o", "O": "capital o", "0": "zero",
    ".": "full stop", ",": "comma", ";": "semicolon", ":": "colon",
    "!": "exclamation", "?": "question", "'": "apostrophe", '"': "quotes",
    "-": "hyphen", "(": "open", ")": "close", "/": "slash",
    "&": "and", "@": "at", "#": "hash", "%": "percent", "+": "plus", "=": "equals",
}

# --- page --------------------------------------------------------------------

PAGE_W, PAGE_H = 210.0, 297.0  # A4. US Letter is 7 mm shorter and needs its own numbers.
MARGIN = 10.0                  # blank edge, wider than most printers' unprintable strip
MARKER_SIZE = 12.0             # ArUco marker side, black border included
MARKER_GAP = 3.0               # white space kept clear around each marker
ARUCO_DICT = "DICT_4X4_50"     # name of the cv2.aruco constant; 50 ids = 12 pages
MARKERS_PER_PAGE = 4           # page p uses ids 4p .. 4p+3: TL, TR, BR, BL

# --- one writing box ---------------------------------------------------------

CELL_W = 15.0
CELL_H = 22.0
# Guide lines, measured down from the top of a box. Proportions follow real
# handwriting (tall letters about twice the x-height, long tails), not the
# font's metrics: the build step rescales using baseline and x-height.
ASCENDER_Y = 3.0   # capitals and tall letters (b, d, h, k, l) reach up to here
XHEIGHT_Y = 9.0    # small letters (a, c, e, ...) reach up to here
BASELINE_Y = 15.0  # every letter sits on this; g, p, y hang below it

# --- grid --------------------------------------------------------------------

GROUPS_PER_ROW = 4   # characters per row; each group is SAMPLES_PER_CHAR boxes
LABEL_H = 5.0        # strip above the boxes for the printed label, kept out of the boxes
ROW_GAP = 2.0
ROW_H = LABEL_H + CELL_H + ROW_GAP

CONTENT_LEFT = MARGIN
CONTENT_RIGHT = PAGE_W - MARGIN
CONTENT_W = CONTENT_RIGHT - CONTENT_LEFT
GROUP_W = SAMPLES_PER_CHAR * CELL_W
GROUP_GAP = (CONTENT_W - GROUPS_PER_ROW * GROUP_W) / (GROUPS_PER_ROW - 1)

GRID_TOP = MARGIN + MARKER_SIZE + MARKER_GAP                 # below the top markers
GRID_BOTTOM = PAGE_H - MARGIN - MARKER_SIZE - MARKER_GAP     # above the bottom markers


@dataclass(frozen=True)
class Box:
    """One place to write: a single character sample, or a sentence line."""
    page: int
    x: float
    y: float
    w: float
    h: float
    text: str            # what to write here
    sample: int | None   # 0..SAMPLES_PER_CHAR-1 for a character box, None for a sentence line

    @property
    def ascender(self) -> float:
        return self.y + ASCENDER_Y

    @property
    def x_height(self) -> float:
        return self.y + XHEIGHT_Y

    @property
    def baseline(self) -> float:
        return self.y + BASELINE_Y


@dataclass(frozen=True)
class Label:
    """Printed text telling the writer what goes in the boxes below it."""
    x: float
    y: float     # top of the label strip
    text: str
    hint: str = ""


@dataclass(frozen=True)
class Marker:
    id: int
    x: float     # top-left corner
    y: float
    size: float = MARKER_SIZE

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.size / 2, self.y + self.size / 2)


@dataclass
class Page:
    index: int
    markers: list[Marker]
    boxes: list[Box] = field(default_factory=list)
    labels: list[Label] = field(default_factory=list)


def page_markers(index: int) -> list[Marker]:
    """The four corner markers of a page, clockwise from top-left."""
    left, right = MARGIN, PAGE_W - MARGIN - MARKER_SIZE
    top, bottom = MARGIN, PAGE_H - MARGIN - MARKER_SIZE
    corners = [(left, top), (right, top), (right, bottom), (left, bottom)]
    first = index * MARKERS_PER_PAGE
    return [Marker(first + i, x, y) for i, (x, y) in enumerate(corners)]


def _place_char_row(page: Page, chars: str, y: float) -> None:
    for g, char in enumerate(chars):
        gx = CONTENT_LEFT + g * (GROUP_W + GROUP_GAP)
        page.labels.append(Label(gx, y, char, HINTS.get(char, "")))
        for s in range(SAMPLES_PER_CHAR):
            page.boxes.append(Box(page.index, gx + s * CELL_W, y + LABEL_H, CELL_W, CELL_H, char, s))


def _place_line(page: Page, text: str, y: float) -> None:
    page.labels.append(Label(CONTENT_LEFT, y, text, "write this sentence"))
    page.boxes.append(Box(page.index, CONTENT_LEFT, y + LABEL_H, CONTENT_W, CELL_H, text, None))


def build_layout(chars: str = CHARACTERS, lines: tuple[str, ...] = SENTENCE_LINES) -> list[Page]:
    """Flow the character rows, then the sentence lines, down as many pages as needed."""
    rows = [chars[i:i + GROUPS_PER_ROW] for i in range(0, len(chars), GROUPS_PER_ROW)]
    items = [(_place_char_row, r) for r in rows] + [(_place_line, s) for s in lines]

    pages: list[Page] = []
    y = GRID_BOTTOM  # forces a new page for the first item
    for place, content in items:
        if y + ROW_H - ROW_GAP > GRID_BOTTOM:
            pages.append(Page(len(pages), page_markers(len(pages))))
            y = GRID_TOP
        place(pages[-1], content, y)
        y += ROW_H
    return pages
