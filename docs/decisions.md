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
