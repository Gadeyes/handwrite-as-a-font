# Handwrite as a Font

Turn your handwriting into a real, installable font (`.otf`) that you can type with in Word, Google Docs (desktop), Figma, or any other app.

You print a 3-page template, fill it in with a pen, take a photo of each page, and run one command. Everything runs on your own computer, and your photos are never uploaded anywhere.

> **Status: early.** The full pipeline works and is covered by automated tests, but it has only been tried on a small number of real photos. Expect rough edges, and please open an issue if a photo of yours doesn't work.

## What you need

- A computer with **Python 3.11 or newer** (Windows, macOS or Linux)
- A printer, or a tablet with a stylus that can write on a PDF
- A black or dark-blue pen
- A phone camera or a scanner

## Install

**1. Install Python** (skip this if `python --version` already prints 3.11 or higher)

- Windows: `winget install Python.Python.3.12`, then open a new terminal
- macOS: `brew install python@3.12`
- Linux: use your package manager, e.g. `sudo apt install python3 python3-venv`

**2. Download the project and set it up**

```
git clone https://github.com/Gadeyes/handwrite-as-a-font.git
cd handwrite-as-a-font
python -m venv .venv
```

**3. Activate the virtual environment** (needed in every new terminal)

- Windows PowerShell: `.venv\Scripts\Activate.ps1`
  (if it says scripts are disabled, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then try again)
- macOS / Linux: `source .venv/bin/activate`

Your prompt now starts with `(.venv)`.

**4. Install**

```
pip install -e .
```

Check it worked with `hwfont --help`.

## Make your font

### 1. Print the template

```
hwfont template
```

This writes `data/template.pdf`: 3 A4 pages with boxes for 80 characters (a–z, A–Z, 0–9 and common punctuation), three boxes each, plus a few lines for a sample sentence. Print it at actual size. On US Letter paper, choose "Fit to page".

### 2. Fill it in

- Write one character in each box, the character printed above it. Fill all three boxes of each character; small differences between them are fine.
- Rest letters on the **blue line**. Tails of g, j, p, q and y go below it.
- Stay inside the box. Writing that touches the edge is flagged, and that box is skipped.
- Don't write on or near the **black corner squares**. They are how the program finds and straightens the page.
- The grey guide lines disappear when the page is read, so don't worry about writing over them.

### 3. Photograph or scan each page

Any of these work:

- **A phone photo of each page:** lay the page flat, use even light, hold the phone straight above it, and make sure **all four corner squares are in the picture**. The angle doesn't need to be perfect.
- **A scanner app** (iPhone Notes "Scan Documents", Google Drive scan, and similar) that saves all pages as one PDF.
- **A tablet:** write directly on `template.pdf` with a stylus and export it as a PDF.

Accepted formats: JPG, PNG and PDF (every page in a PDF is read). iPhone HEIC photos must be converted first; set **Settings → Camera → Formats → Most Compatible** to get JPGs.

Copy the files to a `data/photos/` folder inside the project. The `data/` folder is never committed to Git.

### 4. Build the font

```
hwfont build data/photos
```

The pages can be in any order and any way up, because each page identifies itself by its corner squares. The command prints what it found:

```
pages found: 1, 2, 3
  ! 'b' sample 3: writing touches the box edge
font:    data/fonts/My-Handwriting-1125-1430.otf   (family name in Word: 'My Handwriting 1125-1430')
preview: data/fonts/My-Handwriting-1125-1430-preview.png
```

Lines starting with `!` are problems worth a look. A box with a problem is skipped and another sample of that character is used instead. Open the preview image to see every character before installing.

Useful options:

```
hwfont build data/photos --name "My Hand"       # choose the font name
hwfont build data/photos --cuts data/cuts       # also save every cut-out box as an image
hwfont build page1.jpg page2.jpg page3.jpg      # or list the files yourself
hwfont build scan.pdf
```

### 5. Install and use it

- **Windows:** double-click the `.otf` file → **Install**
- **macOS:** double-click the `.otf` file → **Install Font**
- **Linux:** copy it to `~/.local/share/fonts/`

Restart Word (or whichever app you use), then pick the font by the name the command printed.

## Troubleshooting

| Message or symptom | What to do |
|---|---|
| `hwfont` is not recognized / command not found | Activate the virtual environment (install step 3). |
| `no corner squares found` | The photo doesn't show the page clearly. Retake it with all four black squares in view. |
| `only 2 of the 4 corner squares … are visible` | A square is cut off, covered or in shadow. Retake the photo. |
| `the page doesn't look flat` | Flatten the paper (e.g. under a book) and retake the photo. |
| `photograph one page at a time` | Two pages appear in one photo. Take one photo per page. |
| `no photo of page 2` | That page is missing, or it couldn't be read; see the other messages. |
| `iPhone HEIC photos can't be read yet` | Convert to JPG, or change the camera setting above. |
| `not in the font: …` | Every box for those characters was empty or flagged. Rewrite them on a fresh template page, photograph that page again, and rebuild. |
| Word shows an old version of your font | Word caches fonts by name. Every build gets a new dated name by default, so pick the newest one. If you use `--name`, change the name between builds. |
| Letters look broken or have holes filled in | Use a darker pen, better light, or a scanner app. Look at the `--cuts` images to see what the program saw. |

To look at a single stage:

```
python -m hwfont.scan photo.jpg              # the straightened page, saved in data/scan/
python -m hwfont.render font.otf "Hello"     # render text with a font into an image
```

## Limits

- **Print-style handwriting.** Joined-up cursive can't be split into single letters reliably.
- **Latin letters, digits and basic punctuation** only: the 80 characters on the template. No accents yet.
- Each character is currently one fixed shape. Repeated letters look identical.
- No signatures. The template has no signature box, and the font only contains template characters.

## Roadmap

- **Variants:** use the three samples you wrote (plus generated ones) so repeated letters rotate between shapes as you type, like real handwriting.
- **Quality check:** score each letter automatically and flag ones that read badly.
- **Website:** upload photos in a browser instead of using the command line.

## How it works

```
template (PDF) → your photos → find corner squares and straighten → black-and-white
→ cut out each box → trace outlines as curves → build the .otf font → preview image
```

| Module | Job |
|---|---|
| `layout.py` | Where every box is on the page; shared by the template and the reader |
| `template.py` | Draws the printable PDF |
| `scan.py` | Finds the corner squares (ArUco markers) and straightens the photo |
| `slice.py` | Cuts the page into one image per box and flags empty or overflowing boxes |
| `vectorize.py` | Traces each letter into curves and scales everything to one size |
| `build.py` | Builds the font file with FontTools |
| `render.py` | Draws text with the font, for the preview and the tests |
| `pipeline.py` / `cli.py` | Runs the whole chain; the `hwfont` command |

Built with [OpenCV](https://opencv.org/), [Potrace](https://potrace.sourceforge.net/) (via potracer), [FontTools](https://github.com/fonttools/fonttools), [ReportLab](https://www.reportlab.com/) and [pypdfium2](https://github.com/pypdfium2-team/pypdfium2).

## Development

```
pip install -e ".[dev]"
pytest
```

The tests don't need real handwriting: they render the template, draw fake letters into it, warp it like a phone photo, and check that a working font comes out.
