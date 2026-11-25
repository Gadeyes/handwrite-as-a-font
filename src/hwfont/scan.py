"""Photo of a filled-in template page -> straight, evenly lit, black-and-white page.

    python -m hwfont.scan photo1.jpg photo2.jpg ...   # writes data/scan/page<N>_*.png

The output page is in layout coordinates: pixel (x, y) is layout point
(x / PX_PER_MM, y / PX_PER_MM) millimetres, whatever the angle, distance or
rotation of the original photo. The slicer can then cut boxes using the
layout's numbers alone.
"""

import argparse
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from hwfont import layout as L

PX_PER_MM = 12.0     # about 300 dpi: a 6 mm x-height letter is ~70 px tall
MIN_MARKERS = 3      # 3 markers = 12 corner points, plenty for the fit
MAX_FIT_ERROR_MM = 1.0
STROKE_MAX_MM = 3.0  # anything thinner than this is ink or a printed line, not lighting


class ScanError(Exception):
    """The photo can't be turned into a template page; the message says why."""


@dataclass
class ScannedPage:
    index: int            # which template page this is (0-based), read from the marker ids
    gray: np.ndarray      # straightened and lighting-flattened, uint8, paper ~255
    ink: np.ndarray       # bool, True where there is ink
    markers_found: int
    fit_error_mm: float   # how far the marker corners sit from a perfect fit; large = curled paper
    threshold: int        # grey level that separated ink from paper


def page_size_px() -> tuple[int, int]:
    return round(L.PAGE_W * PX_PER_MM), round(L.PAGE_H * PX_PER_MM)


def load_image(path: Path) -> np.ndarray:
    """Read a photo as BGR. np.fromfile + imdecode also copes with non-ASCII
    Windows paths, which cv2.imread cannot open."""
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ScanError(f"cannot read image: {path}")
    return image


def _detector() -> cv2.aruco.ArucoDetector:
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, L.ARUCO_DICT))
    params = cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX  # corners to a fraction of a pixel
    return cv2.aruco.ArucoDetector(dictionary, params)


def _marker_corners_mm(marker: L.Marker) -> np.ndarray:
    """The four corners in the order OpenCV reports them: TL, TR, BR, BL of the marker as printed."""
    x, y, s = marker.x, marker.y, marker.size
    return np.array([(x, y), (x + s, y), (x + s, y + s), (x, y + s)], dtype=np.float64)


def find_page(gray: np.ndarray, pages: list[L.Page]) -> tuple[int, np.ndarray, np.ndarray]:
    """Detect the markers; return the page index and matching (photo px, layout mm) corner points."""
    corners, ids, _ = _detector().detectMarkers(gray)
    if ids is None or len(ids) == 0:  # OpenCV 4 returns None, OpenCV 5 an empty array
        raise ScanError("no corner squares found. Is the whole page in the photo, in focus and well lit?")

    known = {m.id: m for p in pages for m in p.markers}
    found = {int(i): c.reshape(4, 2) for i, c in zip(ids.flatten(), corners) if int(i) in known}
    if not found:
        raise ScanError("the corner squares in this photo don't belong to this template")

    page_numbers = {i // L.MARKERS_PER_PAGE for i in found}
    if len(page_numbers) > 1:
        shown = ", ".join(str(p + 1) for p in sorted(page_numbers))
        raise ScanError(f"this photo shows corner squares from pages {shown}: photograph one page at a time")
    index = page_numbers.pop()

    if len(found) < MIN_MARKERS:
        raise ScanError(f"only {len(found)} of the 4 corner squares on page {index + 1} are visible; "
                        f"at least {MIN_MARKERS} are needed")

    src = np.concatenate([found[i] for i in sorted(found)])
    dst = np.concatenate([_marker_corners_mm(known[i]) for i in sorted(found)])
    return index, src, dst


def flatten_lighting(gray: np.ndarray) -> np.ndarray:
    """Divide out uneven lighting so paper is ~255 everywhere.

    A max filter wider than any pen stroke replaces ink and printed lines with
    the surrounding paper; blurring that gives the paper's brightness at every
    pixel, shadows included.
    """
    k = int(STROKE_MAX_MM * PX_PER_MM) | 1  # odd size
    paper = cv2.dilate(gray, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    paper = cv2.GaussianBlur(paper, (0, 0), k / 2)
    return cv2.divide(gray, paper, scale=255)


def binarize(flat: np.ndarray) -> tuple[np.ndarray, int]:
    """Ink mask from a lighting-flattened page.

    Otsu picks the cut between ink and paper. It is kept within a band so a
    page with very little ink cannot push the cut up into the guide lines
    (printed at ~190), or down into faint pen strokes.
    """
    otsu, _ = cv2.threshold(flat, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    t = int(np.clip(otsu, 100, 160))
    return flat < t, t


def scan(image: np.ndarray, pages: list[L.Page] | None = None) -> ScannedPage:
    """Straighten one photographed template page and separate ink from paper."""
    pages = pages if pages is not None else L.build_layout()
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    index, src, dst_mm = find_page(gray, pages)
    dst = dst_mm * PX_PER_MM
    # Least squares over every corner point; with 12-16 points one bad corner can't dominate.
    H, _ = cv2.findHomography(src, dst, 0)
    if H is None:
        raise ScanError("could not work out the page's position from the corner squares")

    fitted = cv2.perspectiveTransform(src.reshape(-1, 1, 2), H).reshape(-1, 2)
    fit_error_mm = float(np.linalg.norm(fitted - dst, axis=1).max() / PX_PER_MM)
    if fit_error_mm > MAX_FIT_ERROR_MM:
        raise ScanError(f"the page doesn't look flat (corner squares are off by {fit_error_mm:.1f} mm); "
                        "press it flat and photograph it again")

    straight = cv2.warpPerspective(gray, H, page_size_px(), flags=cv2.INTER_LINEAR,
                                   borderMode=cv2.BORDER_CONSTANT, borderValue=255)
    flat = flatten_lighting(straight)
    ink, threshold = binarize(flat)
    return ScannedPage(index, flat, ink, len(src) // 4, fit_error_mm, threshold)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("photos", type=Path, nargs="+")
    ap.add_argument("-o", "--out", type=Path, default=Path("data/scan"))
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    failed = 0
    for photo in args.photos:
        try:
            page = scan(load_image(photo))
        except ScanError as e:
            print(f"{photo}: {e}")
            failed += 1
            continue
        stem = args.out / f"page{page.index + 1}"
        cv2.imwrite(f"{stem}_straight.png", page.gray)
        cv2.imwrite(f"{stem}_ink.png", np.where(page.ink, 0, 255).astype(np.uint8))
        print(f"{photo}: page {page.index + 1}, {page.markers_found}/4 markers, "
              f"fit error {page.fit_error_mm:.2f} mm, threshold {page.threshold} -> {stem}_*.png")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
