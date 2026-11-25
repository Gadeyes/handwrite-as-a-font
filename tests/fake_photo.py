"""Fake 'phone photos' of filled-in template pages, for tests.

Real photos come later; these exercise the same problems on purpose: a
tilted, off-centre page on a darker table, a shadow across it, blur, sensor
noise and JPEG compression.
"""

from pathlib import Path

import cv2
import numpy as np
import pypdfium2 as pdfium

from hwfont import layout as L

RENDER_DPI = 200
RENDER_PX_PER_MM = RENDER_DPI / 25.4
INK_BGR = (90, 40, 30)  # dark-blue ballpoint


def render_page(pdf_path: Path, index: int) -> np.ndarray:
    """One template page as a BGR image, exactly as printed."""
    pdf = pdfium.PdfDocument(str(pdf_path))
    rgb = np.array(pdf[index].render(scale=RENDER_DPI / 72).to_pil().convert("RGB"))
    pdf.close()
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def write_in(img: np.ndarray, boxes: list[L.Box]) -> None:
    """Write each box's character on its baseline, roughly cap-height tall.

    OpenCV's built-in font stands in for handwriting: it is print, not script,
    but it puts ink where a writer would and that is all the scan tests need.
    """
    s = RENDER_PX_PER_MM
    font = cv2.FONT_HERSHEY_SCRIPT_SIMPLEX
    for b in boxes:
        target_h = (b.baseline - b.ascender) * s * 0.8
        (_, h), _ = cv2.getTextSize("H", font, 1.0, 1)
        scale = target_h / h
        org = (int((b.x + 2.5) * s), int(b.baseline * s))
        cv2.putText(img, b.text, org, font, scale, INK_BGR, thickness=max(2, int(0.6 * s)), lineType=cv2.LINE_AA)


def photograph(page: np.ndarray, seed: int = 0, tilt: float = 0.06, rotate_180: bool = False) -> np.ndarray:
    """Simulate a phone photo of a printed page lying on a table."""
    rng = np.random.default_rng(seed)
    h, w = page.shape[:2]
    if rotate_180:
        page = cv2.rotate(page, cv2.ROTATE_180)

    # The page sits inside a larger frame, seen at an angle (each corner moved a bit).
    out_w, out_h = int(w * 1.35), int(h * 1.25)
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    jitter = rng.uniform(-tilt, tilt, size=(4, 2)) * [w, h]
    dst = np.float32(src + jitter + [(out_w - w) / 2, (out_h - h) / 2])
    M = cv2.getPerspectiveTransform(src, dst)
    table = np.full((out_h, out_w, 3), (70, 95, 120), np.uint8)  # brown-grey table
    photo = cv2.warpPerspective(page, M, (out_w, out_h), dst=table, borderMode=cv2.BORDER_TRANSPARENT)

    # Light falls off across the page, plus a soft shadow blob (a phone or a hand).
    yy, xx = np.mgrid[0:out_h, 0:out_w].astype(np.float32)
    light = 1.0 - 0.35 * (xx / out_w) - 0.10 * (yy / out_h)
    cx, cy = rng.uniform(0.3, 0.7) * out_w, rng.uniform(0.3, 0.7) * out_h
    light -= 0.25 * np.exp(-(((xx - cx) / (0.25 * out_w)) ** 2 + ((yy - cy) / (0.2 * out_h)) ** 2))
    photo = photo.astype(np.float32) * light[..., None]

    photo = cv2.GaussianBlur(photo, (0, 0), 1.2)
    photo += rng.normal(0, 4, photo.shape)
    photo = np.clip(photo, 0, 255).astype(np.uint8)
    ok, jpeg = cv2.imencode(".jpg", photo, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return cv2.imdecode(jpeg, cv2.IMREAD_COLOR)
