import cv2
import numpy as np
import pytest
from fontTools.ttLib import TTFont

pytest.importorskip("pypdfium2")

from fake_photo import photograph, render_page, write_in  # noqa: E402
from hwfont import layout as L  # noqa: E402
from hwfont.cli import main  # noqa: E402


@pytest.fixture(scope="module")
def photos(tmp_path_factory):
    """Fake photos of pages 1 and 2 only (page 3 deliberately missing), plus a blank one."""
    tmp = tmp_path_factory.mktemp("cli")
    pdf = tmp / "template.pdf"
    assert main(["template", "-o", str(pdf)]) == 0
    pages = L.build_layout()
    paths = []
    for i in (1, 0):  # out of order on purpose
        img = render_page(pdf, i)
        write_in(img, [b for b in pages[i].boxes if b.sample == 0])
        path = tmp / f"IMG_{i}.jpg"
        cv2.imwrite(str(path), photograph(img, seed=20 + i))
        paths.append(path)
    blank = tmp / "blank.jpg"
    cv2.imwrite(str(blank), np.full((600, 400, 3), 235, np.uint8))
    return tmp, paths, blank


def test_build_makes_a_font_and_reports_what_is_missing(photos, capsys):
    tmp, paths, blank = photos
    out = tmp / "fonts"
    code = main(["build", *map(str, paths), str(blank), "--name", "HW CLI Test", "-o", str(out),
                 "--cuts", str(tmp / "cuts")])
    printed = capsys.readouterr().out
    assert code == 0
    assert "pages found: 1, 2" in printed
    assert "no photo of page 3" in printed
    assert "blank.jpg: no corner squares" in printed

    font = TTFont(out / "HW-CLI-Test.otf")
    assert font["name"].getDebugName(1) == "HW CLI Test"
    assert chr(ord("a")) in {chr(c) for c in font.getBestCmap()}
    assert (out / "HW-CLI-Test-preview.png").exists()
    assert (tmp / "cuts" / "u0061_a_0.png").exists()


def test_a_multi_page_pdf_scan_works(photos, capsys):
    """Like a phone scanner app: both pages saved into one PDF."""
    from PIL import Image
    tmp, paths, _ = photos
    first, *rest = [Image.open(p).convert("RGB") for p in paths]
    pdf = tmp / "scanned.pdf"
    first.save(pdf, save_all=True, append_images=rest, resolution=150)
    assert main(["build", str(pdf), "-o", str(tmp / "from-pdf")]) == 0
    assert "pages found: 1, 2" in capsys.readouterr().out


def test_folders_and_wildcards_expand_without_a_shell(photos, tmp_path):
    from hwfont.cli import expand_photos
    tmp, paths, blank = photos
    (tmp / "notes.txt").write_text("not a photo")
    found = set(expand_photos([tmp]))
    assert {*paths, blank} <= found and tmp / "notes.txt" not in found
    assert set(expand_photos([tmp / "IMG_*.jpg"])) == set(paths)


def test_missing_and_unreadable_files_are_reported_not_crashed(photos, capsys):
    tmp, paths, _ = photos
    (tmp / "photo.heic").write_bytes(b"not really")
    code = main(["build", str(tmp / "nope.jpg"), str(tmp / "photo.heic"), str(paths[0]),
                 "-o", str(tmp / "mixed")])
    printed = capsys.readouterr().out
    assert code == 0
    assert "nope.jpg: file not found" in printed
    assert "photo.heic: iPhone HEIC" in printed


def test_build_with_nothing_usable_fails_cleanly(photos, capsys):
    tmp, _, blank = photos
    assert main(["build", str(blank), "-o", str(tmp / "none")]) == 1
    assert "no font built" in capsys.readouterr().out
