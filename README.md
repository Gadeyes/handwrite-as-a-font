# Handwrite as a Font

Turn a few pages of your handwriting into an installable `.otf` font that works in Word, Figma, and any other app.

What makes it different from template-based font tools: each letter gets 3–5 natural variants that rotate automatically as you type, so repeated letters don't look copy-pasted.

**Status:** Phase 0, just starting. Nothing is built yet.

## Roadmap

Every phase ends with something usable. Estimates assume about 10 hours a week.

| Phase | Weeks | What we build | Result |
|---|---|---|---|
| 0 | 1–2 | Print template → write → scan → slice → vectorise → export | An installable font |
| 1 | 3–6 | Variants per letter (pretrained few-shot model, or simple deformation) + OpenType rotation | A natural-looking font |
| 2 | 7 | OCR character error rate (TrOCR) + blind test, logged to CSV | Numbers we can quote |
| 3 | 8–9 | "Font doctor": an LLM tool-calling loop that fixes low-scoring letters | Self-repairing pipeline |
| 4 | 10–11 | FastAPI + SQLite + one HTML page, Docker, GPU server | Public demo |

Natural stopping points: after Phase 0 (a font for ourselves), after Phase 2 (model + evaluation data), after Phase 4 (full project).

## Getting started

You need Python 3.11 or newer and Git.

**1. Install Python** (skip if `python --version` already works)

- Windows: `winget install Python.Python.3.12`, then open a new terminal
- macOS: `brew install python@3.12`

**2. Clone and create a virtual environment**

```
git clone <repo-url>
cd handwrite-as-a-font
python -m venv .venv
```

**3. Activate it**

- Windows PowerShell: `.venv\Scripts\Activate.ps1`
  (if blocked, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once)
- macOS / Linux: `source .venv/bin/activate`

**4. Install the Phase 0 libraries**

```
pip install opencv-python pillow fonttools numpy pytest potracer
```

If downloads are slow, add `-i https://pypi.tuna.tsinghua.edu.cn/simple`.

Once `pyproject.toml` exists, this step becomes `pip install -e .`.

## Phase 0 tasks

Do the spike first. It is a throwaway script whose job is to expose the surprises (upside-down letters, filled-in holes, font caching) before we design anything.

- [ ] **Spike:** one handwritten "a" → threshold → trace → `.otf` → typed in Word. Both of us should do this once.
- [ ] `layout.py`: page size, cell grid, character list. The template generator and the slicer both read this, so agree on it together.
- [ ] `template.py`: layout → printable PDF with corner markers and grey guide lines
- [ ] `scan.py`: find the markers, straighten the page, binarise
- [ ] `slice.py`: cut the page into one bitmap per cell, flag empty or overflowing cells
- [ ] `vectorize.py`: bitmap → Bézier outlines
- [ ] `build.py`: outlines + metrics → `.otf`
- [ ] `render.py`: font + text → image (used by tests now, by evaluation later)
- [ ] `cli.py`: `hwfont template` and `hwfont build`
- [ ] Tests: synthetic round trip (template → fake scan → font)
- [ ] Tag `phase-0` and record a short demo

A workable split once `layout.py` is agreed: one person takes the paper side (`template`, `scan`, `slice`), the other takes the font side (`vectorize`, `build`, `render`). The hand-off between the two halves is a folder of labelled glyph bitmaps.

**Phase 0 is done when** a real scan produces a font that installs and types legibly in Word, with the tails of g, p and y below the baseline.

## Planned layout

```
pyproject.toml
README.md
docs/decisions.md     decision log
src/hwfont/           the modules listed above
tests/
data/                 scans, crops, built fonts (not committed)
```

## Template design

Four choices that are cheap now and costly to change later:

- **Three samples of every character.** They give us real variants before any model exists, and real samples for the blind test.
- **A few handwritten lines** (a pangram). The pretrained handwriting models expect word-level style references.
- **Corner markers (ArUco)** so a phone photo can be straightened reliably.
- **Light grey baseline and x-height guides** in every cell. They disappear when the scan is binarised, and they tell us where the baseline is.

## How we work

- **By hand first, then automate.** Run each stage manually once before writing the code for it.
- **One tool per job.** Python, OpenCV, Potrace, FontTools, PyTorch, FastAPI, SQLite. No React, Redis, Celery, PostgreSQL, YOLO or agent frameworks until a real bottleneck appears.
- **Decision log.** Each time we pick or reject a tool, add one line with the reason to `docs/decisions.md`.
- **Branches.** Work on a branch per task, merge to `main` through a pull request the other person reads.
- **Tags.** Tag the end of each phase (`phase-0`, `phase-1`, …) and record a short demo.
- **No personal scans in Git.** Handwriting samples stay in `data/`, which is ignored.

## Scope and limits

- Print-style handwriting only. Joined-up cursive can't be split into single letters reliably.
- Latin letters, digits and basic punctuation.
- **No signatures.** The template has no signature cell and the system only produces template characters.
- When the hosted version exists, uploaded images are deleted on a schedule after the job finishes.

## Tech stack

| Need | Tool |
|---|---|
| Image processing | OpenCV, Potrace |
| Font export | FontTools |
| Variant generation | PyTorch + One-DM or DiffusionPen pretrained weights |
| Evaluation | TrOCR, pytest |
| Font doctor | One multimodal LLM API, official SDK |
| Backend | FastAPI, SQLite |
| Frontend | One HTML page |
| Deployment | Docker, hourly GPU server |
