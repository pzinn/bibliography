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


EMBED_CSS = """
:root{
  --pzpub-fg:#ece4d8;
  --pzpub-muted:#b9ac9a;
  --pzpub-border:#4d4338;
  --pzpub-bg-soft:#14110e;
  --pzpub-bg:#000;
  --pzpub-link:#e1a36f;
  --pzpub-maxw:1080px;
}
.pzpub-root,.pzpub-root *{box-sizing:border-box}
.pzpub-root{
  margin:0 auto;
  max-width:var(--pzpub-maxw);
  padding:2.25rem 1.2rem 4.5rem;
  font-family:Georgia,"Times New Roman",serif;
  color:var(--pzpub-fg);
  line-height:1.5;
  background:var(--pzpub-bg);
  font-size:1.08rem;
}
.pzpub-root.pzpub-embedded{
  padding:1rem 0 2rem;
}
.pzpub-root.pzpub-toc-right{
  display:grid;
  grid-template-columns:minmax(0,1fr) 280px;
  grid-template-areas:
    "title title"
    "content toc";
  column-gap:1.5rem;
  align-items:start;
}
.pzpub-title{
  margin:0 0 0.45rem;
  font-size:2.35rem;
  letter-spacing:0.01em;
}
.pzpub-root.pzpub-toc-right .pzpub-title{
  grid-area:title;
}
.pzpub-toc{
  background:var(--pzpub-bg-soft);
  border:1px solid var(--pzpub-border);
  padding:1rem 1.1rem;
  margin:1.2rem 0 2.4rem;
}
.pzpub-root.pzpub-toc-right .pzpub-toc{
  grid-area:toc;
  margin:0;
  position:sticky;
  top:1rem;
}
.pzpub-toc ul{
  margin:0.5rem 0 0;
  padding-left:1.2rem;
  columns:2;
}
.pzpub-root.pzpub-toc-right .pzpub-toc ul{
  columns:1;
}
.pzpub-theme{
  margin-top:2.8rem;
}
.pzpub-content{
  min-width:0;
}
.pzpub-root.pzpub-toc-right .pzpub-content{
  grid-area:content;
}
.pzpub-root.pzpub-toc-right .pzpub-theme:first-of-type{
  margin-top:0;
}
.pzpub-theme-title,
.pzpub-root .pzpub-theme-title,
.pzpub-root h1.pzpub-title,
.pzpub-root h2.pzpub-title,
.pzpub-root h2.pzpub-theme-title,
.pzpub-root h3.pzpub-theme-title{
  border-bottom:1px solid var(--pzpub-border);
  padding-bottom:0.4rem;
  margin:0 0 1.1rem;
  font-size:1.55rem;
  color:var(--pzpub-fg) !important;
  text-align:left !important;
}
.pzpub-item{
  display:grid;
  grid-template-columns:180px 1fr;
  gap:1.2rem;
  padding:1.1rem 0;
  border-bottom:1px solid var(--pzpub-border);
  align-items:start;
  text-align:left;
  transition:background-color 120ms linear,box-shadow 120ms linear;
}
.pzpub-item:hover{
  background:#2b2117;
  box-shadow:inset 0 1px 0 #5a4330,inset 0 -1px 0 #5a4330;
}
.pzpub-item:focus-within{
  outline:1px solid #6a4f38;
  outline-offset:-1px;
}
.pzpub-thumb{
  width:180px;
  height:140px;
  min-height:0;
  padding:0;
  margin:0;
  text-align:left;
}
.pzpub-thumb img{
  width:100%;
  height:100%;
  object-fit:contain;
  object-position:left top;
  display:block;
  cursor:zoom-in;
  border:none;
  outline:none;
  box-shadow:none;
  background:transparent;
}
.pzpub-meta{
  min-height:100%;
  text-align:left;
}
.pzpub-paper-title{
  font-size:1.25rem;
  font-weight:bold;
  line-height:1.35;
  margin:0;
  text-align:left;
}
.pzpub-authors{
  margin:0;
  font-size:1.06rem;
  font-family:"Helvetica Neue",Helvetica,Arial,sans-serif;
  text-align:left;
}
.pzpub-venue{
  color:var(--pzpub-muted);
  margin:0 0 0.1rem;
  font-style:italic;
  font-size:1.02rem;
  text-align:left;
}
.pzpub-links a{
  margin-right:0.9rem;
  white-space:nowrap;
}
.pzpub-bibtex{
  margin:0.5rem 0 0;
  padding:0.6rem 0.7rem;
  border:1px solid var(--pzpub-border);
  background:#0d0a07;
  white-space:pre-wrap;
  overflow-wrap:anywhere;
  font-size:0.94rem;
  line-height:1.35;
}
.pzpub-summary{
  cursor:pointer;
  color:var(--pzpub-link);
}
.pzpub-root a{color:var(--pzpub-link)}
.pzpub-root a:visited{color:#c58758}
.pzpub-lightbox{
  position:fixed;
  inset:0;
  background:rgba(0,0,0,0.92);
  display:none;
  align-items:center;
  justify-content:center;
  z-index:1000;
  padding:2rem;
}
.pzpub-lightbox.open{
  display:flex;
}
.pzpub-lightbox img{
  max-width:94vw;
  max-height:90vh;
  width:auto;
  height:auto;
  object-fit:contain;
}
.pzpub-lightbox-close{
  position:absolute;
  top:0.8rem;
  right:1rem;
  background:transparent;
  border:0;
  color:#e9dccb;
  font-size:2rem;
  line-height:1;
  cursor:pointer;
  padding:0.2rem 0.4rem;
}
.pzpub-katex{
  font-size:1em;
}
@media (max-width:720px){
  .pzpub-root.pzpub-toc-right{display:block}
  .pzpub-root.pzpub-toc-right .pzpub-toc{display:none}
  .pzpub-toc ul{columns:1}
  .pzpub-item{grid-template-columns:1fr}
  .pzpub-thumb{width:min(260px,100%);min-height:0;height:auto}
  .pzpub-thumb img{width:100%;height:auto;object-fit:contain}
}
""".strip()


EMBED_JS = f"""(function () {{
  const DEFAULT_TARGET_ID = "pzj-publications";
  const STYLE_ID = "pzjpub-style";
  const DATA_SCRIPT_ID = "pzjpub-data-script";
  const DATA_GLOBAL = "__PZJ_PUBLICATIONS_DATA__";
  const CSS_URL = "embed.css";
  const DATA_URL = "publications-data.js";
  const JSON_URL = "publications.json";
  const KATEX_CSS = "{KATEX_CSS_URL}";
  const KATEX_JS = "{KATEX_JS_URL}";
  const KATEX_RENDER_JS = "{KATEX_RENDER_JS_URL}";
  const INITIAL_SCRIPT = document.currentScript || null;

  function currentScript() {{
    if (INITIAL_SCRIPT && INITIAL_SCRIPT.src) return INITIAL_SCRIPT;
    return Array.from(document.querySelectorAll("script[src]")).find((el) =>
      /pzinn\\.github\\.io\\/bibliography\\/embed\\.js(?:\\?|$)/.test(el.src) ||
      /\\/bibliography\\/embed\\.js(?:\\?|$)/.test(el.src)
    ) || null;
  }}

  function scriptParams() {{
    const s = currentScript();
    if (!s || !s.src) return new URLSearchParams();
    try {{
      return new URL(s.src).searchParams;
    }} catch (_) {{
      return new URLSearchParams();
    }}
  }}

  function scriptBase() {{
    const s = currentScript();
    return s && s.src ? new URL(".", s.src).href : "https://pzinn.github.io/bibliography/";
  }}

  function getTarget() {{
    const params = scriptParams();
    const targetId = params.get("targetId") || params.get("target") || DEFAULT_TARGET_ID;
    return document.getElementById(targetId) || document.querySelector("[data-pzj-publications]");
  }}

  function parseFlag(value, fallback) {{
    if (value === null || value === undefined || value === "") return fallback;
    const normalized = String(value).trim().toLowerCase();
    if (["0", "false", "no", "off"].includes(normalized)) return false;
    if (["1", "true", "yes", "on"].includes(normalized)) return true;
    return fallback;
  }}

  function attrFlag(target, name, fallback) {{
    const value = target.getAttribute(name);
    return parseFlag(value, fallback);
  }}

  function optionFlag(target, paramName, attrName, fallback) {{
    const params = scriptParams();
    if (params.has(paramName)) {{
      return parseFlag(params.get(paramName), fallback);
    }}
    return attrFlag(target, attrName, fallback);
  }}

  function optionValue(target, paramName, attrName, fallback) {{
    const params = scriptParams();
    if (params.has(paramName)) {{
      const value = params.get(paramName);
      return value === null || value === "" ? fallback : String(value).trim();
    }}
    const value = target.getAttribute(attrName);
    return value === null || value === "" ? fallback : String(value).trim();
  }}

  function errorMessage(err) {{
    if (!err) return "Unknown error";
    if (typeof err === "string") return err;
    if (err.message) return err.message;
    try {{
      return JSON.stringify(err);
    }} catch (_) {{
      return String(err);
    }}
  }}

  function debugEnabled(target) {{
    const params = scriptParams();
    if (params.has("debug")) return parseFlag(params.get("debug"), false);
    if (target) return attrFlag(target, "data-pzjpub-debug", false);
    return false;
  }}

  function reportFailure(target, context, err) {{
    const info = {{
      context,
      message: errorMessage(err),
      script: currentScript() ? currentScript().src : null,
      base: scriptBase(),
      targetFound: !!target,
      targetId: target ? target.id || null : null
    }};
    console.error("pzj publications embed failed", info, err);
    if (!target) return;

    const debug = debugEnabled(target);
    const link = `<a href="${{info.base}}">Open full list</a>`;
    if (debug) {{
      target.innerHTML =
        `<div style="color:#f3d9c4;background:#1a0f09;border:1px solid #6a4f38;padding:1rem;font-family:monospace;white-space:pre-wrap">` +
        `Failed to load publications.\\n` +
        `context: ${{info.context}}\\n` +
        `message: ${{info.message}}\\n` +
        `script: ${{info.script}}\\n` +
        `base: ${{info.base}}\\n\\n` +
        `${{link}}</div>`;
    }} else {{
      target.innerHTML = `<p>Failed to load publications. ${{link}}</p>`;
    }}
  }}

  function ensureCss(base) {{
    if (document.getElementById(STYLE_ID)) return;
    const link = document.createElement("link");
    link.id = STYLE_ID;
    link.rel = "stylesheet";
    link.href = new URL(CSS_URL, base).href;
    document.head.appendChild(link);
  }}

  function ensureKatexAssets() {{
    if (!document.querySelector(`link[href="${{KATEX_CSS}}"]`)) {{
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = KATEX_CSS;
      document.head.appendChild(link);
    }}
    function ensureScript(src, readyCheck) {{
      return new Promise((resolve, reject) => {{
        if (readyCheck()) {{
          resolve();
          return;
        }}
        const existing = document.querySelector(`script[src="${{src}}"]`);
        if (existing) {{
          existing.addEventListener("load", () => resolve(), {{ once: true }});
          existing.addEventListener("error", () => reject(new Error(`Failed to load ${{src}}`)), {{ once: true }});
          return;
        }}
        const script = document.createElement("script");
        script.defer = true;
        script.src = src;
        script.onload = () => resolve();
        script.onerror = () => reject(new Error(`Failed to load ${{src}}`));
        document.head.appendChild(script);
      }});
    }}

    return ensureScript(KATEX_JS, () => !!window.katex)
      .then(() => ensureScript(KATEX_RENDER_JS, () => !!window.renderMathInElement));
  }}

  function renderMath(root) {{
    if (!window.katex || !window.renderMathInElement) return;
    window.renderMathInElement(root, {{
      delimiters: [
        {{ left: "$$", right: "$$", display: true }},
        {{ left: "$", right: "$", display: false }},
        {{ left: "\\\\(", right: "\\\\)", display: false }},
        {{ left: "\\\\[", right: "\\\\]", display: true }}
      ],
      throwOnError: false
    }});
  }}

  function ensureData(base) {{
    return new Promise((resolve, reject) => {{
      if (window[DATA_GLOBAL]) {{
        resolve(window[DATA_GLOBAL]);
        return;
      }}
      const existing = document.getElementById(DATA_SCRIPT_ID);
      if (existing) {{
        existing.addEventListener("load", () => resolve(window[DATA_GLOBAL]));
        existing.addEventListener("error", reject);
        return;
      }}
      const script = document.createElement("script");
      script.id = DATA_SCRIPT_ID;
      script.src = new URL(DATA_URL, base).href;
      script.defer = true;
      script.onload = () => resolve(window[DATA_GLOBAL]);
      script.onerror = reject;
      document.head.appendChild(script);
    }});
  }}

  function fetchJsonData(base) {{
    return fetch(new URL(JSON_URL, base).href, {{ credentials: "omit" }})
      .then((res) => {{
        if (!res.ok) throw new Error("Failed to fetch publications.json");
        return res.json();
      }});
  }}

  function el(tag, cls, text) {{
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }}

  function openLink(label, href) {{
    const link = document.createElement("a");
    link.textContent = label;
    link.href = href;
    if (/^https?:/i.test(href)) {{
      link.target = "_blank";
      link.rel = "noopener noreferrer";
    }}
    return link;
  }}

  function buildLightbox(root) {{
    const lightbox = el("div", "pzpub-lightbox");
    const close = el("button", "pzpub-lightbox-close");
    close.type = "button";
    close.setAttribute("aria-label", "Close image viewer");
    close.innerHTML = "&times;";
    const img = document.createElement("img");
    lightbox.appendChild(close);
    lightbox.appendChild(img);
    root.appendChild(lightbox);

    function closeLightbox() {{
      lightbox.classList.remove("open");
      img.src = "";
      img.alt = "";
    }}

    close.addEventListener("click", closeLightbox);
    lightbox.addEventListener("click", (ev) => {{
      if (ev.target === lightbox) closeLightbox();
    }});
    document.addEventListener("keydown", (ev) => {{
      if (ev.key === "Escape" && lightbox.classList.contains("open")) closeLightbox();
    }});

    return {{
      open(src, alt) {{
        img.src = src;
        img.alt = alt || "";
        lightbox.classList.add("open");
      }}
    }};
  }}

  function renderPublication(pub, base, options, lightbox) {{
    const article = el("article", "pzpub-item");
    const thumb = el("div", "pzpub-thumb");
    if (pub.image) {{
      const img = document.createElement("img");
      img.src = new URL(pub.image, base).href;
      img.alt = `Thumbnail for ${{pub.title || "publication"}}`;
      img.addEventListener("click", () => lightbox.open(img.src, img.alt));
      thumb.appendChild(img);
    }} else {{
      thumb.setAttribute("aria-hidden", "true");
    }}
    article.appendChild(thumb);

    const meta = el("div", "pzpub-meta");
    meta.appendChild(el("div", "pzpub-paper-title", pub.title || ""));

    if (pub.authors_text) meta.appendChild(el("div", "pzpub-authors", pub.authors_text));
    if (pub.venue) meta.appendChild(el("div", "pzpub-venue", pub.venue));

    const links = el("div", "pzpub-links");
    let hasLinks = false;
    for (const [label, href] of Object.entries(pub.links || {{}})) {{
      links.appendChild(openLink(label, href));
      hasLinks = true;
    }}

    if (options.showBibtex && pub.bibtex) {{
      const bibLink = openLink("BibTeX", "#");
      const bibBlock = el("pre", "pzpub-bibtex", pub.bibtex);
      bibBlock.hidden = true;
      bibLink.addEventListener("click", (ev) => {{
        ev.preventDefault();
        bibBlock.hidden = !bibBlock.hidden;
        bibLink.textContent = bibBlock.hidden ? "BibTeX" : "Hide BibTeX";
      }});
      links.appendChild(bibLink);
      meta.appendChild(links);
      meta.appendChild(bibBlock);
      hasLinks = true;
    }} else if (hasLinks) {{
      meta.appendChild(links);
    }}

    if (options.showAbstract && pub.abstract) {{
      const details = document.createElement("details");
      const summary = el("summary", "pzpub-summary", "Abstract");
      details.appendChild(summary);
      details.appendChild(el("div", "", pub.abstract));
      meta.appendChild(details);
    }} else if (hasLinks && !meta.contains(links)) {{
      meta.appendChild(links);
    }}

    if (!hasLinks && meta.contains(links)) {{
      links.remove();
    }}

    article.appendChild(meta);
    return article;
  }}

  function render(target, payload, base) {{
    const options = {{
      standalone: optionFlag(target, "standalone", "data-pzjpub-standalone", false),
      showTitle: optionFlag(target, "showTitle", "data-pzjpub-show-title", true),
      showBibtex: optionFlag(target, "showBibtex", "data-pzjpub-show-bibtex", true),
      showAbstract: optionFlag(target, "showAbstract", "data-pzjpub-show-abstract", true),
      tocPosition: optionValue(target, "tocPosition", "data-pzjpub-toc-position", "top").toLowerCase()
    }};

    target.innerHTML = "";
    target.classList.add("pzpub-root");
    if (!options.standalone) target.classList.add("pzpub-embedded");
    if (options.tocPosition === "right") target.classList.add("pzpub-toc-right");

    if (options.showTitle) {{
      const titleTag = options.standalone ? "h1" : "h2";
      target.appendChild(el(titleTag, "pzpub-title", payload.title || "Publications"));
    }}

    const toc = el("div", "pzpub-toc");
    toc.appendChild(el("strong", "", "Themes"));
    const tocList = el("ul");
    toc.appendChild(tocList);
    target.appendChild(toc);

    const lightbox = buildLightbox(target);
    const content = el("div", "pzpub-content");
    target.appendChild(content);

    for (const theme of payload.themes || []) {{
      const li = el("li");
      const tocLink = openLink(`${{theme.name}} (${{theme.count}})`, `#pzpub-theme-${{theme.slug}}`);
      li.appendChild(tocLink);
      tocList.appendChild(li);

      const section = el("section", "pzpub-theme");
      section.id = `pzpub-theme-${{theme.slug}}`;
      const headingTag = options.standalone ? "h2" : "h3";
      section.appendChild(el(headingTag, "pzpub-theme-title", theme.name));

      for (const pub of theme.entries || []) {{
        section.appendChild(renderPublication(pub, base, options, lightbox));
      }}
      content.appendChild(section);
    }}

    renderMath(target);
    setTimeout(() => renderMath(target), 300);
    setTimeout(() => renderMath(target), 900);
  }}

  function main() {{
    const target = getTarget();
    if (!target) {{
      console.error("pzj publications embed: target container not found", {{
        script: currentScript() ? currentScript().src : null,
        base: scriptBase()
      }});
      return;
    }}
    const base = scriptBase();
    ensureCss(base);
    const katexReady = ensureKatexAssets()
      .catch((err) => {{
        console.warn("pzj publications embed: KaTeX assets failed to load", {{
          message: errorMessage(err),
          base
        }});
      }});
    const loadPayload = ensureData(base)
      .catch((err) => {{
        console.warn("pzj publications embed: script data load failed, trying JSON fallback", {{
          message: errorMessage(err),
          base
        }});
        return fetchJsonData(base).catch((jsonErr) => {{
          jsonErr.context = "json-fallback";
          jsonErr.previousError = err;
          throw jsonErr;
        }});
      }});

    loadPayload
      .then((payload) => {{
        if (!payload) throw new Error("Missing publications data");
        render(target, payload, base);
        return katexReady.then(() => {{
          renderMath(target);
          setTimeout(() => renderMath(target), 150);
        }});
      }})
      .catch((err) => reportFailure(target, err && err.context ? err.context : "main", err));
  }}

  main();
}})();"""


INDEX_HTML = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Publications - Paul Zinn-Justin</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="generator" content="build_publications.py from pzj.bib">
</head>
<body style="margin:0;background:#000;">
  <!-- Generated automatically from pzj.bib by build_publications.py -->
  <div
    id="pzj-publications"
    data-pzjpub-standalone="true"
    data-pzjpub-show-title="true"
    data-pzjpub-show-bibtex="true"
    data-pzjpub-show-abstract="true"
    data-pzjpub-toc-position="top"
  ></div>
  <script src="publications-data.js"></script>
  <script src="embed.js"></script>
</body>
</html>
"""


def data_script(payload: dict) -> str:
    return "window.__PZJ_PUBLICATIONS_DATA__ = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n"


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
    (SITE_DIR / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (SITE_DIR / "embed.css").write_text(EMBED_CSS + "\n", encoding="utf-8")
    (SITE_DIR / "embed.js").write_text(EMBED_JS + "\n", encoding="utf-8")
    (SITE_DIR / "publications.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (SITE_DIR / "publications-data.js").write_text(data_script(payload), encoding="utf-8")
    print(f"Wrote {SITE_DIR / 'index.html'}")


if __name__ == "__main__":
    build()
