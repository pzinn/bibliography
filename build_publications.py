#!/usr/bin/env python3

from __future__ import annotations

import html
import re
import shutil
from collections import defaultdict
from pathlib import Path

import bibtexparser
from jinja2 import Environment, select_autoescape


ROOT = Path(__file__).resolve().parent
BIB_FILE = ROOT / "pzj.bib"
IMAGES_DIR = ROOT / "images"
SITE_DIR = ROOT / "site"
SITE_IMAGES_DIR = SITE_DIR / "images"

IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".webp", ".gif"]


def first_of(entry: dict, *keys: str) -> str:
    for key in keys:
        value = entry.get(key)
        if value:
            return str(value).strip()
    return ""


def clean_latex_basic(s: str) -> str:
    """
    Very lightweight BibTeX/LaTeX cleanup.
    This is intentionally conservative and easy to tweak later.
    """
    if not s:
        return ""

    # Remove outer braces used for capitalization protection.
    s = s.replace("{", "").replace("}", "")

    replacements = {
        r"\\&": "&",
        r"\\%": "%",
        r"\\_": "_",
        r"\\#": "#",
        r"\\textendash": "–",
        r"\\textemdash": "—",
        r"\\'e": "é",
        r'\\"o': "ö",
        r'\\"u': "ü",
        r'\\"a': "ä",
        r"\\`e": "è",
        r"\\aa": "å",
        r"\\ss": "ß",
        "--": "—",
    }
    for k, v in replacements.items():
        s = s.replace(k, v)

    # Very rough removal of remaining TeX commands like \emph, \textbf, etc.
    s = re.sub(r"\\[a-zA-Z]+\s*", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def clean_latex_preserving_math(s: str) -> str:
    """
    Clean lightweight LaTeX in text while preserving inline math expressions.

    Math segments delimited by unescaped `$...$` are kept as-is so KaTeX can
    render them client-side.
    """
    if not s:
        return ""

    parts: list[tuple[str, str]] = []
    buf: list[str] = []
    in_math = False
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "$" and (i == 0 or s[i - 1] != "\\"):
            if in_math:
                buf.append(ch)
                parts.append(("math", "".join(buf)))
                buf = []
                in_math = False
            else:
                if buf:
                    parts.append(("text", "".join(buf)))
                    buf = []
                buf.append(ch)
                in_math = True
            i += 1
            continue
        buf.append(ch)
        i += 1

    if buf:
        parts.append(("math" if in_math else "text", "".join(buf)))

    cleaned_parts: list[tuple[str, str]] = []
    for part_type, part in parts:
        if part_type == "math":
            cleaned_parts.append((part_type, part))
        else:
            cleaned = clean_latex_basic(part)
            if part[:1].isspace() and cleaned and not cleaned.startswith(" "):
                cleaned = " " + cleaned
            if part[-1:].isspace() and cleaned and not cleaned.endswith(" "):
                cleaned = cleaned + " "
            cleaned_parts.append((part_type, cleaned))

    joined_parts: list[str] = []
    left_attach = "([{-/–—"
    right_attach = ").,;:!?]}-/–—"
    prev_type: str | None = None
    for part_type, text in cleaned_parts:
        if not text:
            continue
        if joined_parts:
            prev_text = joined_parts[-1]
            if (
                not prev_text.endswith((" ", "\t", "\n"))
                and not text.startswith((" ", "\t", "\n"))
            ):
                prev_char = prev_text[-1]
                next_char = text[0]
                if (
                    (prev_type == "text" and part_type == "math" and prev_char not in left_attach)
                    or (prev_type == "math" and part_type == "text" and next_char not in right_attach)
                    or (prev_type == "math" and part_type == "math")
                ):
                    joined_parts.append(" ")
        joined_parts.append(text)
        prev_type = part_type

    joined = "".join(joined_parts)
    return re.sub(r"\s+", " ", joined).strip()


def split_authors(author_field: str) -> list[str]:
    if not author_field:
        return []
    def normalize_author_name(name: str) -> str:
        cleaned = clean_latex_basic(name.strip())
        if "," not in cleaned:
            return cleaned
        parts = [p.strip() for p in cleaned.split(",") if p.strip()]
        # BibTeX supports:
        #   Last, First
        #   Last, Jr, First
        if len(parts) == 2:
            return f"{parts[1]} {parts[0]}"
        if len(parts) >= 3:
            return f"{parts[2]} {parts[0]} {parts[1]}"
        return cleaned

    authors = [normalize_author_name(a) for a in author_field.split(" and ")]
    return [a for a in authors if a]


def parse_year(entry: dict) -> int:
    year = first_of(entry, "year")
    m = re.search(r"\d{4}", year)
    if m:
        return int(m.group(0))
    return 0


def find_image_for_key(key: str) -> Path | None:
    for ext in IMAGE_EXTENSIONS:
        candidate = IMAGES_DIR / f"{key}{ext}"
        if candidate.exists():
            return candidate
    return None


def entry_links(entry: dict) -> dict[str, str]:
    links: dict[str, str] = {}

    url = first_of(entry, "url")
    doi = first_of(entry, "doi")
    eprint = first_of(entry, "eprint")
    archiveprefix = first_of(entry, "archiveprefix").lower()
    arxiv = first_of(entry, "arxiv")

    if doi:
        links["DOI"] = f"https://doi.org/{doi}"
    if url:
        links["URL"] = url

    if arxiv:
        links["arXiv"] = f"https://arxiv.org/abs/{arxiv}"
    elif eprint and (archiveprefix == "arxiv" or re.match(r"^\d{4}\.\d{4,5}(v\d+)?$", eprint)):
        links["arXiv"] = f"https://arxiv.org/abs/{eprint}"

    # Optional custom fields you might already have or may want later
    slides = first_of(entry, "slides")
    code = first_of(entry, "code")
    pdf = first_of(entry, "pdf")

    if pdf:
        links["PDF"] = pdf
    if slides:
        links["Slides"] = slides
    if code:
        links["Code"] = code

    return links


def bibtex_entry_without_theme(entry: dict) -> str:
    entry_type = first_of(entry, "ENTRYTYPE") or "misc"
    key = first_of(entry, "ID") or "entry"
    lines = [f"@{entry_type}{{{key},"]
    for field, value in entry.items():
        if field in {"ID", "ENTRYTYPE"}:
            continue
        if field.lower() == "theme":
            continue
        v = str(value).strip()
        if not v:
            continue
        lines.append(f"  {field} = {{{v}}},")
    lines.append("}")
    return "\n".join(lines)


def venue_string(entry: dict) -> str:
    parts = []

    journal = first_of(entry, "journal")
    booktitle = first_of(entry, "booktitle")
    publisher = first_of(entry, "publisher")
    howpublished = first_of(entry, "howpublished")

    venue = journal or booktitle or howpublished or publisher
    volume = first_of(entry, "volume")
    number = first_of(entry, "number")
    pages = first_of(entry, "pages")
    year = first_of(entry, "year")

    if venue:
        parts.append(clean_latex_basic(venue))
    if volume:
        vol_part = clean_latex_basic(volume)
        if number:
            vol_part += f"({clean_latex_basic(number)})"
        parts.append(vol_part)
    elif number:
        parts.append(f"no. {clean_latex_basic(number)}")
    if pages:
        parts.append(f"pp. {clean_latex_basic(pages)}")
    if year:
        parts.append(clean_latex_basic(year))

    return ", ".join(parts)


def yymm_to_yyyymm(yymm: int) -> int:
    """
    Convert arXiv YYMM to YYYYMM on a single timeline.

    Old-style arXiv ids use YYMM with years 91-07. Modern ids also start with
    YYMM (e.g. 2403.12345). Mapping both onto YYYYMM makes them comparable.
    """
    yy = yymm // 100
    mm = yymm % 100
    if mm < 1 or mm > 12:
        return yymm
    year = 1900 + yy if yy >= 90 else 2000 + yy
    return year * 100 + mm


def arxiv_sort_key(entry: dict) -> tuple[int, int] | None:
    """
    Return a sortable chronological key from an arXiv identifier.

    Both modern and old-style arXiv ids are mapped to (YYYYMM, serial).
    """
    arxiv = first_of(entry, "arxiv")
    if not arxiv:
        eprint = first_of(entry, "eprint")
        archiveprefix = first_of(entry, "archiveprefix").lower()
        if eprint and (archiveprefix == "arxiv" or "arxiv" in first_of(entry, "url").lower()):
            arxiv = eprint

    if not arxiv:
        url = first_of(entry, "url")
        m = re.search(r"arxiv\.org/(?:abs|pdf)/([^\s/]+)", url, re.IGNORECASE)
        if m:
            arxiv = m.group(1)

    if not arxiv:
        return None

    arxiv = arxiv.strip()

    # Modern format: 2403.12345 or 2403.12345v2
    m = re.match(r"^(\d{4})\.(\d{4,5})(?:v\d+)?$", arxiv)
    if m:
        yyyymm = yymm_to_yyyymm(int(m.group(1)))
        return (yyyymm, int(m.group(2)))

    # Old format: math/0612345, hep-th/9901001, cond-mat/0207063, etc.
    m = re.match(r"^[a-z\-]+(?:\.[A-Z]{2})?/(\d{7})(?:v\d+)?$", arxiv, re.IGNORECASE)
    if m:
        digits = m.group(1)
        yyyymm = yymm_to_yyyymm(int(digits[:4]))
        return (yyyymm, int(digits[4:]))

    return None


def entry_chronology_key(entry: dict) -> tuple[int, int]:
    """
    Prefer arXiv chronology; otherwise fall back to publication year.
    Larger means more recent.
    """
    ak = arxiv_sort_key(entry)
    if ak is not None:
        return ak
    year = parse_year(entry)
    return (year * 100, 0)


def load_entries() -> list[dict]:
    with BIB_FILE.open("r", encoding="utf-8") as f:
        db = bibtexparser.load(f)

    processed: list[dict] = []

    for raw in db.entries:
        key = raw.get("ID", "").strip()
        if not key:
            continue

        title = clean_latex_preserving_math(first_of(raw, "title"))
        authors = split_authors(first_of(raw, "author"))
        theme = clean_latex_basic(first_of(raw, "theme")) or "Other"
        abstract = clean_latex_basic(first_of(raw, "abstract"))
        venue = venue_string(raw)
        year = parse_year(raw)
        links = entry_links(raw)

        image_path = find_image_for_key(key)
        site_image = None
        if image_path is not None:
            SITE_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
            target = SITE_IMAGES_DIR / image_path.name
            shutil.copy2(image_path, target)
            site_image = f"images/{target.name}"

        processed.append(
            {
                "key": key,
                "title": title,
                "authors": authors,
                "authors_text": ", ".join(authors),
                "theme": theme,
                "abstract": abstract,
                "venue": venue,
                "year": year,
                "links": links,
                "image": site_image,
                "type": raw.get("ENTRYTYPE", ""),
                "chronology_key": entry_chronology_key(raw),
                "bibtex": bibtex_entry_without_theme(raw),
            }
        )

    processed.sort(key=lambda e: (-e["year"], e["title"].lower()))
    return processed


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Publications — Paul Zinn-Justin</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="generator" content="build_publications.py from pzj.bib">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
  <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
  <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"></script>
  <style>
    :root {
      --fg: #ece4d8;
      --muted: #b9ac9a;
      --border: #4d4338;
      --bg-soft: #14110e;
      --bg: #000;
      --link: #e1a36f;
      --maxw: 1080px;
    }
    html { box-sizing: border-box; }
    *, *:before, *:after { box-sizing: inherit; }
    body {
      margin: 0;
      padding: 2.25rem 1.2rem 4.5rem;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--fg);
      line-height: 1.5;
      background: var(--bg);
      font-size: 1.08rem;
    }
    .wrap {
      max-width: var(--maxw);
      margin: 0 auto;
    }
    h1 {
      margin-top: 0;
      margin-bottom: 0.45rem;
      font-size: 2.35rem;
      letter-spacing: 0.01em;
    }
    .toc {
      background: var(--bg-soft);
      border: 1px solid var(--border);
      padding: 1rem 1.1rem;
      margin: 1.2rem 0 2.4rem;
    }
    .toc ul {
      margin: 0.5rem 0 0;
      padding-left: 1.2rem;
      columns: 2;
    }
    .theme-section {
      margin-top: 2.8rem;
    }
    .theme-section h2 {
      border-bottom: 1px solid var(--border);
      padding-bottom: 0.4rem;
      margin-bottom: 1.1rem;
      font-size: 1.55rem;
    }
    .pub {
      display: grid;
      grid-template-columns: 180px 1fr;
      gap: 1.2rem;
      padding: 1.1rem 0;
      border-bottom: 1px solid var(--border);
      align-items: start;
      transition: background-color 120ms linear, box-shadow 120ms linear;
    }
    .pub:hover {
      background: #2b2117;
      box-shadow: inset 0 1px 0 #5a4330, inset 0 -1px 0 #5a4330;
    }
    .pub:focus-within {
      outline: 1px solid #6a4f38;
      outline-offset: -1px;
    }
    .thumb {
      width: 180px;
      height: 140px;
      min-height: 0;
      display: flex;
      align-items: flex-start;
      justify-content: flex-start;
      border: 0;
      background: transparent;
      box-shadow: none;
      outline: none;
      padding: 0;
      margin: 0;
    }
    .thumb img {
      width: 100%;
      height: 100%;
      object-fit: contain;
      object-position: left top;
      display: block;
      cursor: zoom-in;
      border: none;
      outline: none;
      box-shadow: none;
      background: transparent;
    }
    .meta {
      display: grid;
      row-gap: 0.25rem;
      align-content: start;
      min-height: 100%;
    }
    .title {
      font-size: 1.25rem;
      font-weight: bold;
      line-height: 1.35;
      margin-bottom: 0;
    }
    .authors {
      margin-bottom: 0;
      font-size: 1.06rem;
      font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    }
    .venue {
      color: var(--muted);
      margin-bottom: 0.1rem;
      font-style: italic;
      font-size: 1.02rem;
    }
    .links a {
      margin-right: 0.9rem;
      white-space: nowrap;
    }
    .bibtex-block {
      margin: 0.5rem 0 0;
      padding: 0.6rem 0.7rem;
      border: 1px solid var(--border);
      background: #0d0a07;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-size: 0.94rem;
      line-height: 1.35;
    }
    .lightbox {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.92);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 1000;
      padding: 2rem;
    }
    .lightbox.open {
      display: flex;
    }
    .lightbox img {
      max-width: 94vw;
      max-height: 90vh;
      width: auto;
      height: auto;
      object-fit: contain;
      border: none;
      outline: none;
      box-shadow: none;
      background: transparent;
    }
    .lightbox-close {
      position: absolute;
      top: 0.8rem;
      right: 1rem;
      background: transparent;
      border: 0;
      color: #e9dccb;
      font-size: 2rem;
      line-height: 1;
      cursor: pointer;
      padding: 0.2rem 0.4rem;
    }
    details {
      margin-top: 0.5rem;
    }
    summary {
      cursor: pointer;
      color: var(--link);
    }
    a { color: var(--link); }
    a:visited { color: #c58758; }
    .katex {
      font-size: 1em;
    }
    code {
      background: #1a1510;
      padding: 0.1rem 0.34rem;
      border-radius: 3px;
    }
    @media (max-width: 720px) {
      .toc ul { columns: 1; }
      .pub {
        grid-template-columns: 1fr;
      }
      .thumb {
        width: min(260px, 100%);
        min-height: 0;
        height: auto;
      }
      .thumb img {
        width: 100%;
        height: auto;
        object-fit: contain;
      }
    }
  </style>
</head>
<body>
  <!-- Generated automatically from pzj.bib by build_publications.py -->
  <div class="wrap">
    <h1>Publications</h1>

    <div class="toc">
      <strong>Themes</strong>
      <ul>
      {% for theme in themes %}
        <li><a href="#theme-{{ theme.slug }}">{{ theme.name }}</a> ({{ theme.count }})</li>
      {% endfor %}
      </ul>
    </div>

    {% for theme in themes %}
      <section class="theme-section" id="theme-{{ theme.slug }}">
        <h2>{{ theme.name }}</h2>

        {% for pub in theme.entries %}
          <article class="pub">
              <div class="thumb"{% if not pub.image %} aria-hidden="true"{% endif %}>
            {% if pub.image %}
                <img src="{{ pub.image }}" alt="Thumbnail for {{ pub.title }}">
            {% endif %}
              </div>

            <div class="meta">
              <div class="title">{{ pub.title }}</div>
              {% if pub.authors_text %}
                <div class="authors">{{ pub.authors_text }}</div>
              {% endif %}
              {% if pub.venue %}
                <div class="venue">{{ pub.venue }}</div>
              {% endif %}
              {% if pub.links %}
                <div class="links">
                  {% for label, href in pub.links.items() %}
                    <a href="{{ href }}">{{ label }}</a>
                  {% endfor %}
                  {% if pub.bibtex %}
                    <a href="#" class="bibtex-toggle" data-target="bib-{{ pub.key }}">BibTeX</a>
                  {% endif %}
                </div>
              {% endif %}
              {% if pub.bibtex %}
                <pre id="bib-{{ pub.key }}" class="bibtex-block" hidden>{{ pub.bibtex }}</pre>
              {% endif %}
              {% if pub.abstract %}
                <details>
                  <summary>Abstract</summary>
                  <div>{{ pub.abstract }}</div>
                </details>
              {% endif %}
            </div>
          </article>
        {% endfor %}
      </section>
    {% endfor %}
  </div>
  <div id="lightbox" class="lightbox" hidden>
    <button type="button" class="lightbox-close" aria-label="Close image viewer">&times;</button>
    <img id="lightbox-image" alt="">
  </div>
  <script>
    document.addEventListener("DOMContentLoaded", function () {
      if (window.renderMathInElement) {
        window.renderMathInElement(document.body, {
          delimiters: [
            {left: "$$", right: "$$", display: true},
            {left: "$", right: "$", display: false},
            {left: "\\\\(", right: "\\\\)", display: false},
            {left: "\\\\[", right: "\\\\]", display: true}
          ],
          throwOnError: false
        });
      }

      document.addEventListener("click", function (ev) {
        const link = ev.target.closest(".bibtex-toggle");
        if (!link) return;
        ev.preventDefault();
        const id = link.getAttribute("data-target");
        if (!id) return;
        const block = document.getElementById(id);
        if (!block) return;
        const nowHidden = !block.hasAttribute("hidden");
        if (nowHidden) {
          block.setAttribute("hidden", "");
          link.textContent = "BibTeX";
        } else {
          block.removeAttribute("hidden");
          link.textContent = "Hide BibTeX";
        }
      });

      const lightbox = document.getElementById("lightbox");
      const lightboxImage = document.getElementById("lightbox-image");
      const lightboxClose = lightbox ? lightbox.querySelector(".lightbox-close") : null;

      function openLightbox(src, alt) {
        if (!lightbox || !lightboxImage) return;
        lightboxImage.src = src;
        lightboxImage.alt = alt || "";
        lightbox.hidden = false;
        lightbox.classList.add("open");
      }

      function closeLightbox() {
        if (!lightbox || !lightboxImage) return;
        lightbox.classList.remove("open");
        lightbox.hidden = true;
        lightboxImage.src = "";
        lightboxImage.alt = "";
      }

      document.addEventListener("click", function (ev) {
        const img = ev.target.closest(".thumb img");
        if (!img) return;
        openLightbox(img.currentSrc || img.src, img.alt);
      });

      if (lightbox) {
        lightbox.addEventListener("click", function (ev) {
          if (ev.target === lightbox) {
            closeLightbox();
          }
        });
      }

      if (lightboxClose) {
        lightboxClose.addEventListener("click", function () {
          closeLightbox();
        });
      }

      document.addEventListener("keydown", function (ev) {
        if (ev.key === "Escape" && lightbox && !lightbox.hidden) {
          closeLightbox();
        }
      });
    });
  </script>
</body>
</html>
"""


def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "other"


def build() -> None:
    entries = load_entries()

    grouped: dict[str, list[dict]] = defaultdict(list)
    for entry in entries:
        grouped[entry["theme"]].append(entry)

    themes = []
    for theme_name, theme_entries in grouped.items():
        theme_entries.sort(
            key=lambda e: (-e["chronology_key"][0], -e["chronology_key"][1], e["title"].lower())
        )
        most_recent_key = max((e["chronology_key"] for e in theme_entries), default=(0, 0))
        themes.append(
            {
                "name": theme_name,
                "slug": slugify(theme_name),
                "count": len(theme_entries),
                "entries": theme_entries,
                "most_recent_key": most_recent_key,
            }
        )

    themes.sort(
        key=lambda t: (-t["most_recent_key"][0], -t["most_recent_key"][1], t["name"].lower())
    )

    SITE_DIR.mkdir(parents=True, exist_ok=True)
    (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")

    env = Environment(autoescape=select_autoescape(["html", "xml"]))
    template = env.from_string(TEMPLATE)
    html_out = template.render(themes=themes)

    (SITE_DIR / "index.html").write_text(html_out, encoding="utf-8")
    print(f"Wrote {SITE_DIR / 'index.html'}")

if __name__ == "__main__":
    build()
