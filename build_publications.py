#!/usr/bin/env python3

from __future__ import annotations

import json
import re
import shutil
from collections import defaultdict
from pathlib import Path

import bibtexparser


ROOT = Path(__file__).resolve().parent
BIB_FILE = ROOT / "pzj.bib"
IMAGES_DIR = ROOT / "images"
STATIC_DIR = ROOT / "static"
SITE_DIR = ROOT / "site"
SITE_IMAGES_DIR = SITE_DIR / "images"

IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".webp", ".gif"]

KATEX_CSS_URL = "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css"
KATEX_JS_URL = "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"
KATEX_RENDER_JS_URL = "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"


def first_of(entry: dict, *keys: str) -> str:
    for key in keys:
        value = entry.get(key)
        if value:
            return str(value).strip()
    return ""


def clean_latex_basic(s: str) -> str:
    if not s:
        return ""

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

    s = re.sub(r"\\[a-zA-Z]+\s*", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def clean_latex_preserving_math(s: str) -> str:
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

    return re.sub(r"\s+", " ", "".join(joined_parts)).strip()


def split_authors(author_field: str) -> list[str]:
    if not author_field:
        return []

    def normalize_author_name(name: str) -> str:
        cleaned = clean_latex_basic(name.strip())
        if "," not in cleaned:
            return cleaned
        parts = [p.strip() for p in cleaned.split(",") if p.strip()]
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
    return int(m.group(0)) if m else 0


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

    pdf = first_of(entry, "pdf")
    slides = first_of(entry, "slides")
    code = first_of(entry, "code")
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
        if field in {"ID", "ENTRYTYPE"} or field.lower() == "theme":
            continue
        v = str(value).strip()
        if v:
            lines.append(f"  {field} = {{{v}}},")
    lines.append("}")
    return "\n".join(lines)


def venue_string(entry: dict) -> str:
    parts = []
    venue = (
        first_of(entry, "journal")
        or first_of(entry, "booktitle")
        or first_of(entry, "howpublished")
        or first_of(entry, "publisher")
    )
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
    yy = yymm // 100
    mm = yymm % 100
    if mm < 1 or mm > 12:
        return yymm
    year = 1900 + yy if yy >= 90 else 2000 + yy
    return year * 100 + mm


def arxiv_sort_key(entry: dict) -> tuple[int, int] | None:
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
    m = re.match(r"^(\d{4})\.(\d{4,5})(?:v\d+)?$", arxiv)
    if m:
        return (yymm_to_yyyymm(int(m.group(1))), int(m.group(2)))

    m = re.match(r"^[a-z\-]+(?:\.[A-Z]{2})?/(\d{7})(?:v\d+)?$", arxiv, re.IGNORECASE)
    if m:
        digits = m.group(1)
        return (yymm_to_yyyymm(int(digits[:4])), int(digits[4:]))

    return None


def entry_chronology_key(entry: dict) -> tuple[int, int]:
    arxiv_key = arxiv_sort_key(entry)
    if arxiv_key is not None:
        return arxiv_key
    return (parse_year(entry) * 100, 0)


def load_entries() -> list[dict]:
    with BIB_FILE.open("r", encoding="utf-8") as f:
        db = bibtexparser.load(f)

    processed: list[dict] = []
    for raw in db.entries:
        key = raw.get("ID", "").strip()
        if not key:
            continue

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
                "title": clean_latex_preserving_math(first_of(raw, "title")),
                "authors_text": ", ".join(split_authors(first_of(raw, "author"))),
                "theme": clean_latex_basic(first_of(raw, "theme")) or "Other",
                "abstract": clean_latex_basic(first_of(raw, "abstract")),
                "venue": venue_string(raw),
                "year": parse_year(raw),
                "links": entry_links(raw),
                "image": site_image,
                "type": raw.get("ENTRYTYPE", ""),
                "chronology_key": entry_chronology_key(raw),
                "bibtex": bibtex_entry_without_theme(raw),
            }
        )

    processed.sort(key=lambda e: (-e["year"], e["title"].lower()))
    return processed


def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "other"


def group_themes(entries: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for entry in entries:
        grouped[entry["theme"]].append(entry)

    themes = []
    for theme_name, theme_entries in grouped.items():
        theme_entries.sort(
            key=lambda e: (-e["chronology_key"][0], -e["chronology_key"][1], e["title"].lower())
        )
        themes.append(
            {
                "name": theme_name,
                "slug": slugify(theme_name),
                "count": len(theme_entries),
                "entries": theme_entries,
                "most_recent_key": max((e["chronology_key"] for e in theme_entries), default=(0, 0)),
            }
        )

    themes.sort(key=lambda t: (-t["most_recent_key"][0], -t["most_recent_key"][1], t["name"].lower()))
    return themes


def data_script(payload: dict) -> str:
    return "window.__PZJ_PUBLICATIONS_DATA__ = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n"


def copy_static_assets() -> None:
    for name in ("index.html", "embed.css", "embed.js"):
        shutil.copy2(STATIC_DIR / name, SITE_DIR / name)


def build_payload(themes: list[dict]) -> dict:
    return {
        "title": "Publications",
        "themes": [
            {
                "name": theme["name"],
                "slug": theme["slug"],
                "count": theme["count"],
                "entries": [
                    {
                        "key": entry["key"],
                        "title": entry["title"],
                        "authors_text": entry["authors_text"],
                        "venue": entry["venue"],
                        "links": entry["links"],
                        "image": entry["image"],
                        "bibtex": entry["bibtex"],
                        "abstract": entry["abstract"],
                    }
                    for entry in theme["entries"]
                ],
            }
            for theme in themes
        ],
    }


def build() -> None:
    entries = load_entries()
    themes = group_themes(entries)
    payload = build_payload(themes)

    SITE_DIR.mkdir(parents=True, exist_ok=True)
    (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")
    copy_static_assets()
    (SITE_DIR / "publications.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (SITE_DIR / "publications-data.js").write_text(data_script(payload), encoding="utf-8")
    print(f"Wrote {SITE_DIR / 'index.html'}")


if __name__ == "__main__":
    build()
