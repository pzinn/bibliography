(function () {
  const DEFAULT_TARGET_ID = "pzj-publications";
  const STYLE_ID = "pzjpub-style";
  const DATA_SCRIPT_ID = "pzjpub-data-script";
  const DATA_GLOBAL = "__PZJ_PUBLICATIONS_DATA__";
  const CSS_URL = "embed.css";
  const DATA_URL = "publications-data.js";
  const JSON_URL = "publications.json";
  const KATEX_CSS = "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css";
  const KATEX_JS = "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js";
  const KATEX_RENDER_JS = "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js";
  const INITIAL_SCRIPT = document.currentScript || null;

  function currentScript() {
    if (INITIAL_SCRIPT && INITIAL_SCRIPT.src) return INITIAL_SCRIPT;
    return Array.from(document.querySelectorAll("script[src]")).find((el) =>
      /pzinn\.github\.io\/bibliography\/embed\.js(?:\?|$)/.test(el.src) ||
      /\/bibliography\/embed\.js(?:\?|$)/.test(el.src)
    ) || null;
  }

  function scriptParams() {
    const s = currentScript();
    if (!s || !s.src) return new URLSearchParams();
    try {
      return new URL(s.src).searchParams;
    } catch (_) {
      return new URLSearchParams();
    }
  }

  function scriptBase() {
    const s = currentScript();
    return s && s.src ? new URL(".", s.src).href : "https://pzinn.github.io/bibliography/";
  }

  function getTarget() {
    const params = scriptParams();
    const targetId = params.get("targetId") || params.get("target") || DEFAULT_TARGET_ID;
    return document.getElementById(targetId) || document.querySelector("[data-pzj-publications]");
  }

  function parseFlag(value, fallback) {
    if (value === null || value === undefined || value === "") return fallback;
    const normalized = String(value).trim().toLowerCase();
    if (["0", "false", "no", "off"].includes(normalized)) return false;
    if (["1", "true", "yes", "on"].includes(normalized)) return true;
    return fallback;
  }

  function attrFlag(target, name, fallback) {
    const value = target.getAttribute(name);
    return parseFlag(value, fallback);
  }

  function optionFlag(target, paramName, attrName, fallback) {
    const params = scriptParams();
    if (params.has(paramName)) {
      return parseFlag(params.get(paramName), fallback);
    }
    return attrFlag(target, attrName, fallback);
  }

  function optionValue(target, paramName, attrName, fallback) {
    const params = scriptParams();
    if (params.has(paramName)) {
      const value = params.get(paramName);
      return value === null || value === "" ? fallback : String(value).trim();
    }
    const value = target.getAttribute(attrName);
    return value === null || value === "" ? fallback : String(value).trim();
  }

  function errorMessage(err) {
    if (!err) return "Unknown error";
    if (typeof err === "string") return err;
    if (err.message) return err.message;
    try {
      return JSON.stringify(err);
    } catch (_) {
      return String(err);
    }
  }

  function debugEnabled(target) {
    const params = scriptParams();
    if (params.has("debug")) return parseFlag(params.get("debug"), false);
    if (target) return attrFlag(target, "data-pzjpub-debug", false);
    return false;
  }

  function reportFailure(target, context, err) {
    const info = {
      context,
      message: errorMessage(err),
      script: currentScript() ? currentScript().src : null,
      base: scriptBase(),
      targetFound: !!target,
      targetId: target ? target.id || null : null
    };
    console.error("pzj publications embed failed", info, err);
    if (!target) return;

    const debug = debugEnabled(target);
    const link = `<a href="${info.base}">Open full list</a>`;
    if (debug) {
      target.innerHTML =
        `<div style="color:#f3d9c4;background:#1a0f09;border:1px solid #6a4f38;padding:1rem;font-family:monospace;white-space:pre-wrap">` +
        `Failed to load publications.\n` +
        `context: ${info.context}\n` +
        `message: ${info.message}\n` +
        `script: ${info.script}\n` +
        `base: ${info.base}\n\n` +
        `${link}</div>`;
    } else {
      target.innerHTML = `<p>Failed to load publications. ${link}</p>`;
    }
  }

  function ensureCss(base) {
    if (document.getElementById(STYLE_ID)) return;
    const link = document.createElement("link");
    link.id = STYLE_ID;
    link.rel = "stylesheet";
    link.href = new URL(CSS_URL, base).href;
    document.head.appendChild(link);
  }

  function ensureKatexAssets() {
    if (!document.querySelector(`link[href="${KATEX_CSS}"]`)) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = KATEX_CSS;
      document.head.appendChild(link);
    }

    function ensureScript(src, readyCheck) {
      return new Promise((resolve, reject) => {
        if (readyCheck()) {
          resolve();
          return;
        }
        const existing = document.querySelector(`script[src="${src}"]`);
        if (existing) {
          existing.addEventListener("load", () => resolve(), { once: true });
          existing.addEventListener("error", () => reject(new Error(`Failed to load ${src}`)), { once: true });
          return;
        }
        const script = document.createElement("script");
        script.defer = true;
        script.src = src;
        script.onload = () => resolve();
        script.onerror = () => reject(new Error(`Failed to load ${src}`));
        document.head.appendChild(script);
      });
    }

    return ensureScript(KATEX_JS, () => !!window.katex)
      .then(() => ensureScript(KATEX_RENDER_JS, () => !!window.renderMathInElement));
  }

  function renderMath(root) {
    if (!window.katex || !window.renderMathInElement) return;
    window.renderMathInElement(root, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "$", right: "$", display: false },
        { left: "\\(", right: "\\)", display: false },
        { left: "\\[", right: "\\]", display: true }
      ],
      throwOnError: false
    });
  }

  function ensureData(base) {
    return new Promise((resolve, reject) => {
      if (window[DATA_GLOBAL]) {
        resolve(window[DATA_GLOBAL]);
        return;
      }
      const existing = document.getElementById(DATA_SCRIPT_ID);
      if (existing) {
        existing.addEventListener("load", () => resolve(window[DATA_GLOBAL]));
        existing.addEventListener("error", reject);
        return;
      }
      const script = document.createElement("script");
      script.id = DATA_SCRIPT_ID;
      script.src = new URL(DATA_URL, base).href;
      script.defer = true;
      script.onload = () => resolve(window[DATA_GLOBAL]);
      script.onerror = reject;
      document.head.appendChild(script);
    });
  }

  function fetchJsonData(base) {
    return fetch(new URL(JSON_URL, base).href, { credentials: "omit" })
      .then((res) => {
        if (!res.ok) throw new Error("Failed to fetch publications.json");
        return res.json();
      });
  }

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function openLink(label, href) {
    const link = document.createElement("a");
    link.textContent = label;
    link.href = href;
    if (/^https?:/i.test(href)) {
      link.target = "_blank";
      link.rel = "noopener noreferrer";
    }
    return link;
  }

  function renderPublication(pub, base, options, imageRegistry) {
    const article = el("article", "pzpub-item");
    const thumb = el("div", "pzpub-thumb");
    if (pub.image) {
      const img = document.createElement("img");
      img.src = new URL(pub.image, base).href;
      img.alt = `Thumbnail for ${pub.title || "publication"}`;
      img.addEventListener("click", () => {
        const expanded = article.classList.contains("pzpub-item-expanded");
        for (const item of imageRegistry) {
          if (item !== article) {
            item.classList.remove("pzpub-item-expanded");
            const otherThumb = item.querySelector(".pzpub-thumb");
            if (otherThumb) otherThumb.classList.remove("pzpub-thumb-expanded");
          }
        }
        article.classList.toggle("pzpub-item-expanded", !expanded);
        thumb.classList.toggle("pzpub-thumb-expanded", !expanded);
      });
      thumb.appendChild(img);
      imageRegistry.push(article);
    } else {
      thumb.setAttribute("aria-hidden", "true");
    }
    article.appendChild(thumb);

    const meta = el("div", "pzpub-meta");
    meta.appendChild(el("div", "pzpub-paper-title", pub.title || ""));

    if (pub.authors_text) meta.appendChild(el("div", "pzpub-authors", pub.authors_text));
    if (pub.venue) meta.appendChild(el("div", "pzpub-venue", pub.venue));

    const links = el("div", "pzpub-links");
    let hasLinks = false;
    for (const [label, href] of Object.entries(pub.links || {})) {
      links.appendChild(openLink(label, href));
      hasLinks = true;
    }

    if (options.showBibtex && pub.bibtex) {
      const bibLink = openLink("BibTeX", "#");
      const bibBlock = el("pre", "pzpub-bibtex", pub.bibtex);
      bibBlock.hidden = true;
      bibLink.addEventListener("click", (ev) => {
        ev.preventDefault();
        bibBlock.hidden = !bibBlock.hidden;
        bibLink.textContent = bibBlock.hidden ? "BibTeX" : "Hide BibTeX";
      });
      links.appendChild(bibLink);
      meta.appendChild(links);
      meta.appendChild(bibBlock);
      hasLinks = true;
    } else if (hasLinks) {
      meta.appendChild(links);
    }

    if (options.showAbstract && pub.abstract) {
      const details = document.createElement("details");
      const summary = el("summary", "pzpub-summary", "Abstract");
      details.appendChild(summary);
      details.appendChild(el("div", "", pub.abstract));
      meta.appendChild(details);
    } else if (hasLinks && !meta.contains(links)) {
      meta.appendChild(links);
    }

    if (!hasLinks && meta.contains(links)) {
      links.remove();
    }

    article.appendChild(meta);
    return article;
  }

  function render(target, payload, base) {
    const options = {
      standalone: optionFlag(target, "standalone", "data-pzjpub-standalone", false),
      showTitle: optionFlag(target, "showTitle", "data-pzjpub-show-title", true),
      showBibtex: optionFlag(target, "showBibtex", "data-pzjpub-show-bibtex", true),
      showAbstract: optionFlag(target, "showAbstract", "data-pzjpub-show-abstract", true),
      tocPosition: optionValue(target, "tocPosition", "data-pzjpub-toc-position", "top").toLowerCase()
    };

    target.innerHTML = "";
    target.classList.add("pzpub-root");
    if (!options.standalone) target.classList.add("pzpub-embedded");
    if (options.tocPosition === "right") target.classList.add("pzpub-toc-right");

    if (options.showTitle) {
      const titleTag = options.standalone ? "h1" : "h2";
      target.appendChild(el(titleTag, "pzpub-title", payload.title || "Publications"));
    }

    const toc = el("div", "pzpub-toc");
    toc.appendChild(el("strong", "", "Themes"));
    const tocList = el("ul");
    toc.appendChild(tocList);
    target.appendChild(toc);

    const content = el("div", "pzpub-content");
    const imageRegistry = [];
    target.appendChild(content);

    for (const theme of payload.themes || []) {
      const li = el("li");
      const tocLink = openLink(`${theme.name} (${theme.count})`, `#pzpub-theme-${theme.slug}`);
      li.appendChild(tocLink);
      tocList.appendChild(li);

      const section = el("section", "pzpub-theme");
      section.id = `pzpub-theme-${theme.slug}`;
      const headingTag = options.standalone ? "h2" : "h3";
      section.appendChild(el(headingTag, "pzpub-theme-title", theme.name));

      for (const pub of theme.entries || []) {
        section.appendChild(renderPublication(pub, base, options, imageRegistry));
      }
      content.appendChild(section);
    }

    renderMath(target);
    setTimeout(() => renderMath(target), 300);
    setTimeout(() => renderMath(target), 900);
  }

  function main() {
    const target = getTarget();
    if (!target) {
      console.error("pzj publications embed: target container not found", {
        script: currentScript() ? currentScript().src : null,
        base: scriptBase()
      });
      return;
    }
    const base = scriptBase();
    ensureCss(base);
    const katexReady = ensureKatexAssets()
      .catch((err) => {
        console.warn("pzj publications embed: KaTeX assets failed to load", {
          message: errorMessage(err),
          base
        });
      });
    const loadPayload = ensureData(base)
      .catch((err) => {
        console.warn("pzj publications embed: script data load failed, trying JSON fallback", {
          message: errorMessage(err),
          base
        });
        return fetchJsonData(base).catch((jsonErr) => {
          jsonErr.context = "json-fallback";
          jsonErr.previousError = err;
          throw jsonErr;
        });
      });

    loadPayload
      .then((payload) => {
        if (!payload) throw new Error("Missing publications data");
        render(target, payload, base);
        return katexReady.then(() => {
          renderMath(target);
          setTimeout(() => renderMath(target), 150);
        });
      })
      .catch((err) => reportFailure(target, err && err.context ? err.context : "main", err));
  }

  main();
})();
