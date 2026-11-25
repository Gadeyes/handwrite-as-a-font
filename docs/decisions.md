# Decision log

One line per decision or finding: what was picked, rejected or learned, and why.

## Phase 0 spike (2026-11-21)

- **Trace with `potracer`, and hand it the inverted ink mask.** It treats `False` pixels as the shape, so passing the ink mask directly traces the paper instead of the letter.
- **Fix contour direction after the y-flip.** Image y points down and font y points up, so flipping mirrors every contour and reverses its direction. Outer contours must run counter-clockwise in CFF, so the outline is reversed when its signed area is negative; otherwise holes fill in.
- **Set `ulCodePageRange1 = 1` in the OS/2 table.** Without the Latin 1 bit Word lists the font but silently draws Courier New. FreeType and Pillow ignore the field, so the preview image cannot catch this; only typing in Word can.
- **Give every rebuild a new family name.** Word keeps showing a cached copy of a font it has already seen under the same name.
- **Export CFF outlines (`.otf`) at 1000 units per em.** Potrace produces cubic Béziers, which CFF stores directly; TrueType would need a conversion to quadratics.
- **Binarise with Otsu's threshold.** Light guide lines land on the paper side of the cut and disappear, with no hand-tuned threshold.
- **Take the baseline from the guide line, not from the ink.** The bottom of the ink is wrong for letters with tails (g, p, y), so it is only the fallback when no guide line is found.

## Template (2026-11-24)

- **Fill-in template, not free handwriting photos, for Phase 0.** Each box already says which character it holds, so slicing yields labelled glyphs with no letter detection. The photo route depends on CharLoc, whose README restricts it to non-commercial research, and on a word detector never tested on a real photo.
- **All layout positions in millimetres, top-left origin, y down.** Matches image pixel coordinates, so a straightened scan maps onto the layout with one scale factor. Only `template.py` converts to PDF's bottom-left, y-up points.
- **ArUco `DICT_4X4_50` corner markers, ids 4p..4p+3 on page p.** A photo identifies its own page and orientation, so sheets can be scanned in any order. OpenCV already ships the detector (4.7+). 50 ids allow 12 pages.
- **reportlab for the PDF.** Vector output, so markers and lines stay sharp at any printer resolution; its built-in Helvetica needs no font files. Markers are drawn as vector squares from OpenCV's bit pattern, not pasted as images.
- **A4 only for now.** US Letter is 7 mm shorter and would lose a row per page; it needs its own numbers if anyone asks.
- **Guides proportioned like handwriting, not like the font.** Box 15 × 22 mm: tall-letter line 3 mm, x-height line 9 mm, baseline 15 mm from the top, leaving 7 mm for tails. The build step rescales with baseline and x-height, so the font's own metrics need not match.
- **Guides and borders printed at grey level about 190; labels kept outside the boxes.** Otsu's cut puts them on the paper side, so an empty box binarises to no ink at all (tested on the rendered PDF). Real photos with uneven light still need checking in `scan.py`.
- **80 characters × 3 samples + 4 sentence lines = 3 pages.** 18 punctuation marks rather than 19: one more character would push the sentence lines onto a fourth page. Look-alikes (l, I, 1, o, O, 0) and all punctuation get a printed name beside the label.

## Scan (2026-11-25)

- **Straightened pages at 12 px/mm (about 300 dpi).** A 6 mm x-height letter is ~70 px tall, enough for clean tracing; a 12 MP phone photo of A4 has ~19 px/mm, so nothing is invented by upscaling.
- **Fit the perspective to every marker corner, least squares, at least 3 markers.** 12–16 points instead of 4 centres: one covered marker still works, and the leftover error (reported in mm) flags curled paper. Over 1 mm is rejected.
- **Flatten lighting before thresholding.** A 3 mm max filter plus blur estimates the paper's brightness under shadows; dividing by it makes paper ~255 everywhere. Global Otsu alone fails as soon as a shadow makes paper darker than the guide lines elsewhere.
- **Otsu's threshold clamped to 100–160.** A nearly empty page could otherwise push the cut up into the guide lines (~190).
- **Read photos with `np.fromfile` + `cv2.imdecode`.** `cv2.imread` can't open non-ASCII Windows paths.
- **Photo rotation is ignored on purpose.** Marker ids fix orientation, so EXIF rotation tags and upside-down photos need no handling.
- **OpenCV 5 returns an empty array, not `None`, when no marker is found.** Check both.
- **Tests use fake phone photos** (`tests/fake_photo.py`: tilt, shadow, blur, noise, JPEG). They prove the geometry and lighting logic, not real pens on real paper.

## Slice, vectorize, build, render (2026-11-25)

- **Crop 0.5 mm inside each box; ink touching the crop edge = "overflow".** Overflowing samples are kept but only used when a character has no clean sample. Blobs under 15 px are dropped as noise (a full stop is ~50 px or more).
- **Cut images are named by code point (`u0061_a_0.png`, `u0041_A_0.png`).** Windows forbids `?:/"*` in names and treats `a.png` and `A.png` as the same file.
- **One scale for all glyphs, from the median height of flat capitals (B D E F H I K L M N P R T X Z) mapped to 700 units.** The spike scaled each letter to the x-height on its own, which only works for one letter. Falls back to flat small letters, then to the printed guides.
- **Snap to the baseline only characters that should rest on it**, and only if within 2 mm. Removes handwriting's up-and-down drift; g j p q y Q J and most punctuation stay as written.
- **Glyph names from the Adobe Glyph List** (`period`, `quotedbl` ...), `uniXXXX` otherwise, so text copied out of PDFs stays readable.
- **Ascent and descent come from the real glyph extremes, rounded outwards, never tighter than 800 / -200.** Windows clips anything outside them. Rounding to nearest clipped a 0.2-unit sliver of a `g` tail.
- **Phase 0 uses one sample per character (first clean one).** The other samples become rotating alternates in Phase 1.
- **render.py uses Pillow's basic layout.** This Pillow build has no libraqm, so it ignores OpenType features: Phase 1's rotation will need HarfBuzz (`uharfbuzz`) to show in previews and evaluation.
- **Whole pipeline on 3 fake photos: about 4 s on a laptop**, pure-Python potracer included. Not worth optimising.
