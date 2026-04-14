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
    }
    for k, v in replacements.items():
        s = s.replace(k, v)

    # Very rough removal of remaining TeX commands like \emph, \textbf, etc.
    s = re.sub(r"\\[a-zA-Z]+\s*", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def split_authors(author_field: str) -> list[str]:
    if not author_field:
        return []
    authors = [clean_latex_basic(a.strip()) for a in author_field.split(" and ")]
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

def arxiv_sort_key(entry: dict) -> tuple[int, int] | None:
    """
    Return a sortable chronological key from an arXiv identifier.

    For modern arXiv ids like:
      2403.12345
      2403.12345v2
    return (2403, 12345)

    For old-style ids like:
      math/0612345
      hep-th/9901001
    return a rough sortable key based on the trailing 7 digits:
      yymmnnn  -> (yymm, nnn)

    Return None if no usable arXiv id is found.
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
        return (int(m.group(1)), int(m.group(2)))

    # Old format: math/0612345, hep-th/9901001, etc.
    m = re.match(r"^[a-z\-]+(?:\.[A-Z]{2})?/(\d{7})(?:v\d+)?$", arxiv, re.IGNORECASE)
    if m:
        digits = m.group(1)
        return (int(digits[:4]), int(digits[4:]))

    return None

def entry_chronology_key(entry: dict) -> tuple[int, int]:
    """
    Prefer arXiv chronology; otherwise fall back to year.
    Larger means more recent.
    """
    ak = arxiv_sort_key(entry)
    if ak is not None:
        return ak

    year = parse_year(entry)
    return (year, 0)

def load_entries() -> list[dict]:
    with BIB_FILE.open("r", encoding="utf-8") as f:
        db = bibtexparser.load(f)

    processed: list[dict] = []

    for raw in db.entries:
        key = raw.get("ID", "").strip()
        if not key:
            continue

        title = clean_latex_basic(first_of(raw, "title"))
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
  <style>
    :root {
      --fg: #e8e8e8;
      --muted: #aaaaaa;
      --border: #444;
      --bg-soft: #111;
      --bg: #000;
      --link: #7db7ff;
      --maxw: 1000px;
    }
    html { box-sizing: border-box; }
    *, *:before, *:after { box-sizing: inherit; }
    body {
      margin: 0;
      padding: 2rem 1rem 4rem;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--fg);
      line-height: 1.45;
      background: var(--bg);
    }
    .wrap {
      max-width: var(--maxw);
      margin: 0 auto;
    }
    h1 {
      margin-top: 0;
      margin-bottom: 0.3rem;
      font-size: 2rem;
    }
    .intro {
      color: var(--muted);
      margin-bottom: 2rem;
    }
    .toc {
      background: var(--bg-soft);
      border: 1px solid var(--border);
      padding: 1rem;
      margin: 1.5rem 0 2rem;
    }
    .toc ul {
      margin: 0.5rem 0 0;
      padding-left: 1.2rem;
      columns: 2;
    }
    .theme-section {
      margin-top: 2.5rem;
    }
    .theme-section h2 {
      border-bottom: 1px solid var(--border);
      padding-bottom: 0.35rem;
      margin-bottom: 1rem;
    }
    .pub {
      display: grid;
      grid-template-columns: 140px 1fr;
      gap: 1rem;
      padding: 1rem 0;
      border-bottom: 1px solid var(--border);
    }
    .pub.noimg {
      grid-template-columns: 1fr;
    }
    .thumb {
      width: 140px;
    }
    .thumb img {
      width: 100%;
      height: auto;
      display: block;
      border: 1px solid var(--border);
      background: #000;
    }
    .title {
      font-size: 1.1rem;
      font-weight: bold;
      margin-bottom: 0.2rem;
    }
    .authors {
      margin-bottom: 0.2rem;
    }
    .venue {
      color: var(--muted);
      margin-bottom: 0.35rem;
      font-style: italic;
    }
    .links a {
      margin-right: 0.8rem;
      white-space: nowrap;
    }
    details {
      margin-top: 0.5rem;
    }
    summary {
      cursor: pointer;
      color: var(--link);
    }
    a { color: var(--link); }
    a:visited { color: #b08cff; }
    code {
      background: #111;
      padding: 0.1rem 0.3rem;
      border-radius: 3px;
    }
    @media (max-width: 720px) {
      .toc ul { columns: 1; }
      .pub, .pub.noimg {
        grid-template-columns: 1fr;
      }
      .thumb {
        width: min(260px, 100%);
      }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Publications</h1>
    <div class="intro">
      Generated automatically from <code>pzj.bib</code>.
    </div>

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
          <article class="pub{% if not pub.image %} noimg{% endif %}">
            {% if pub.image %}
              <div class="thumb">
                <img src="{{ pub.image }}" alt="Thumbnail for {{ pub.title }}">
              </div>
            {% endif %}

            <div>
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
                </div>
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
