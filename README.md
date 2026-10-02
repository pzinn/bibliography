# Publications website and CV

This repository contains a publications website and three LaTeX CV documents.
Both use the master bibliography, `pzj.bib`.

## Files to edit

| File or directory | Purpose |
| --- | --- |
| `pzj.bib` | Publications, themes, abstracts, and links. |
| `images/` | Thumbnails named after bibliography keys, e.g. `artic93.png`. |
| `static/index.html` | Standalone page wrapper and its display options. |
| `static/embed.js` | Shared renderer, interactions, loading, and KaTeX configuration. |
| `static/embed.css` | Shared website styling and mobile layout. |
| `build_publications.py` | Bibliography parsing, cleanup, ordering, and website generation. |
| `build_cv.py` | Compilation of all three CV PDFs. |
| `.github/workflows/publish.yml` | GitHub Pages build and deployment on pushes to `main`. |
| `cv/cv-body.tex` | CV text. |
| `cv/conf.tex` | Conference history, used for conference counts in the CV. |
| `cv/cv-shared.tex` | Shared LaTeX formatting and commands. |
| `cv/publications-body.tex` | Publication list configuration. |
| `cv/unsrt-mod.bst` | Custom bibliography style, sorting newest publications first. |

`cv/pzj.bib` is a symbolic link to `../pzj.bib`, not a separate bibliography.

## Python setup

Create a virtual environment outside the repository:

```sh
python3 -m venv ../bibliography-venv
source ../bibliography-venv/bin/activate
python -m pip install -r requirements.txt
```

Activate that environment again in each new terminal before running the build
commands. If `bibtexparser` cannot be imported, use the setup commands above;
installing through `python -m pip` selects the same Python as the build.

## Website

```sh
python build_publications.py
python -m http.server 8000 --directory site
```

Open `http://localhost:8000/` to preview the standalone page.
The build generates `site/`, which is ignored by Git. Edit the source files,
not files inside `site/`.

`site/publications-data.js` is the primary data source. `site/publications.json`
contains the same data and is a fallback for the embedded renderer. The static
frontend files and matching images are copied into `site/` during the build.

Pushing to `main` builds and publishes the website at
<https://pzinn.github.io/bibliography/>. This workflow does not compile the CV.

### Embed in another website

```html
<div style="width:100%;background:#000;">
  <div id="pzj-publications"></div>
</div>
<script src="https://pzinn.github.io/bibliography/embed.js?targetId=pzj-publications&amp;showTitle=0&amp;showBibtex=1&amp;showAbstract=1&amp;tocPosition=right"></script>
```

Available options are `targetId`, `showTitle`, `showBibtex`, `showAbstract`,
`tocPosition` (`top` or `right`), and `debug=1` for detailed loading errors.
Boolean options accept `0`/`1` or `false`/`true`. The right-hand themes menu and
image enlargement are disabled on screens at most 720 pixels wide.

Standalone display options are set with `data-pzjpub-*` attributes in
`static/index.html`. Embedded pages can use the same attributes on their target
div; URL options override the attributes. Both versions use the same CSS and
renderer, so design changes only need to be made once.

## CV documents

Install a TeX distribution providing `pdflatex`, `bibtex`, and the packages
listed in `cv/cv-shared.tex`, then run from the repository root:

```sh
python3 build_cv.py
```

The command runs the LaTeX/BibTeX passes needed to rebuild:

| Source | Output |
| --- | --- |
| `cv/cv-only.tex` | `cv/cv-only.pdf`: CV without the publication list. |
| `cv/publications-only.tex` | `cv/publications-only.pdf`: publication list only. |
| `cv/cv-full.tex` | `cv/cv-full.pdf`: CV plus publications. |

The publication list uses `\nocite{*}`, so every entry in `pzj.bib` is included
automatically. The bibliography style sorts by arXiv number, falling back to
publication year, with the most recent papers first. Both modern and historical
arXiv numbers are supported. Moscow lecture notes have been removed from the
master bibliography.

The PDFs are tracked in Git. Rebuild and review them after changing the CV,
conference history, or bibliography, then commit the updated PDFs with the
source changes. They are not published by the website workflow.

To compile a single document manually, run from inside `cv/`. For example:

```sh
pdflatex -interaction=nonstopmode -halt-on-error publications-only.tex
bibtex publications-only
pdflatex -interaction=nonstopmode -halt-on-error publications-only.tex
pdflatex -interaction=nonstopmode -halt-on-error publications-only.tex
```

## Local clutter

`site/`, `__pycache__/`, editor backups ending in `~`, and LaTeX intermediates
(`.aux`, `.bbl`, `.blg`, `.log`, `.out`) are ignored by Git. The corresponding
source files and the three CV PDFs are the files to maintain.
