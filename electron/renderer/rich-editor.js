/** Rich markdown editor (Toast UI) for memos and notes. */
(function () {
  const instances = new WeakMap();

  function currentTheme() {
    return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
  }

  function editorTheme() {
    return currentTheme() === "dark" ? "dark" : "default";
  }

  function ensureMarked() {
    if (window.marked?.parse) return window.marked;
    return null;
  }

  function highlightHashtags(html) {
    return String(html || "").replace(/#([\w\u4e00-\u9fff-]+)/g, '<span class="memo-hashtag">#$1</span>');
  }

  function sanitizeHtml(html) {
    const tpl = document.createElement("template");
    tpl.innerHTML = html;
    tpl.content.querySelectorAll("script, iframe, object, embed, link, style").forEach((el) => el.remove());
    tpl.content.querySelectorAll("*").forEach((el) => {
      [...el.attributes].forEach((attr) => {
        const name = attr.name.toLowerCase();
        if (name.startsWith("on") || name === "srcdoc") el.removeAttribute(attr.name);
      });
    });
    return tpl.innerHTML;
  }

  function renderMarkdown(md) {
    const text = String(md || "");
    const marked = ensureMarked();
    if (!marked) return highlightHashtags(escapeHtml(text).replace(/\n/g, "<br>"));
    try {
      const html = marked.parse(text, { breaks: true, gfm: true });
      return highlightHashtags(sanitizeHtml(html));
    } catch {
      return highlightHashtags(escapeHtml(text).replace(/\n/g, "<br>"));
    }
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function uploadImage(blob, apiBase) {
    const form = new FormData();
    form.append("file", blob, blob.name || "paste.png");
    const res = await fetch(`${apiBase}/api/editor/media`, { method: "POST", body: form });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    const url = data.url || "";
    if (url.startsWith("http")) return url;
    return `${apiBase}${url.startsWith("/") ? url : `/${url}`}`;
  }

  function baseOptions(el, { apiBase, height, minHeight, placeholder, compact, growWithContent }) {
    const Editor = window.toastui?.Editor;
    if (!Editor) throw new Error("Toast UI Editor 未加载");
    const opts = {
      el,
      // Toast UI 原生 auto-height：相对定位流式增高，避免固定高度 + overflow 叠字
      height: growWithContent ? "auto" : height || (compact ? "140px" : "100%"),
      minHeight: minHeight || (compact ? "100px" : "280px"),
      initialEditType: "wysiwyg",
      previewStyle: "tab",
      hideModeSwitch: !!compact,
      usageStatistics: false,
      autofocus: false,
      placeholder: placeholder || "写点什么… 支持标题、列表、图片与 #标签",
      theme: editorTheme(),
      toolbarItems: compact
        ? [["heading", "bold", "italic"], ["ul", "ol"], ["link", "image"]]
        : [
            ["heading", "bold", "italic", "strike"],
            ["hr", "quote"],
            ["ul", "ol", "task"],
            ["table", "link", "image"],
            ["code", "codeblock"],
          ],
      hooks: {
        addImageBlobHook: (blob, callback) => {
          uploadImage(blob, apiBase)
            .then((url) => callback(url, blob.name || "image"))
            .catch((err) => {
              window.YizhiToast?.error(String(err.message || err));
            });
        },
      },
    };
    // 仅当 zh-CN 语言包已注册时启用（须在 toastui 主脚本之后加载 i18n）
    try {
      if (Editor.i18n?.get?.("zh-CN") || (Editor.i18n && typeof Editor.i18n.setLanguage === "function")) {
        opts.language = "zh-CN";
      }
    } catch {
      /* keep default language */
    }
    return opts;
  }

  function createTextareaFallback(el, options = {}) {
    el.innerHTML = "";
    const ta = document.createElement("textarea");
    ta.className = "yizhi-memo-fallback-ta";
    ta.placeholder = options.placeholder || "写闪念…";
    ta.value = options.initialValue || "";
    ta.style.cssText =
      "width:100%;min-height:" +
      (options.minHeight || (options.compact ? "100px" : "280px")) +
      ";box-sizing:border-box;padding:10px;font:14px/1.5 system-ui,sans-serif;border:1px solid rgba(128,128,128,.35);border-radius:8px;resize:vertical;";
    el.appendChild(ta);
    const rec = {
      editor: {
        getMarkdown: () => ta.value,
        setMarkdown: (md) => {
          ta.value = md || "";
        },
        focus: () => ta.focus(),
        destroy: () => ta.remove(),
        height: () => {},
      },
      el,
      options: { ...options, fallback: true },
    };
    instances.set(el, rec);
    return rec;
  }

  function elevatePopups(host) {
    if (!host || host._yizhiPopupMo) return;
    const syncPopup = (popup) => {
      if (!popup || popup.dataset.yizhiPortaled === "1") return;
      const ui = popup.closest(".toastui-editor-defaultUI");
      if (!ui || !host.contains(ui)) return;
      const rect = popup.getBoundingClientRect();
      popup.dataset.yizhiPortaled = "1";
      document.body.appendChild(popup);
      popup.style.position = "fixed";
      popup.style.left = `${Math.max(8, rect.left)}px`;
      popup.style.top = `${Math.max(8, rect.top)}px`;
      popup.style.zIndex = "10000";
    };
    host._yizhiPopupMo = new MutationObserver(() => {
      host.querySelectorAll(".toastui-editor-popup").forEach(syncPopup);
    });
    host._yizhiPopupMo.observe(host, { childList: true, subtree: true });
  }

  function create(el, options = {}) {
    if (!el) return null;
    const existing = instances.get(el);
    if (existing) destroy(existing);
    const Editor = window.toastui?.Editor;
    if (!Editor) {
      console.warn("[YizhiRichEditor] Toast UI 未加载，使用纯文本框");
      return createTextareaFallback(el, options);
    }
    try {
      const editor = new Editor(baseOptions(el, options));
      if (options.initialValue) editor.setMarkdown(options.initialValue);
      const rec = { editor, el, options: { ...options } };
      instances.set(el, rec);
      elevatePopups(el);
      if (options.growWithContent) {
        try {
          editor.setHeight?.("auto");
        } catch {
          /* ignore */
        }
        el.classList.add("auto-height");
      } else {
        scheduleFit(rec);
      }
      return rec;
    } catch (err) {
      console.warn("[YizhiRichEditor] 创建失败，回退纯文本:", err);
      return createTextareaFallback(el, options);
    }
  }

  function htmlToPlain(html) {
    const tpl = document.createElement("template");
    tpl.innerHTML = html || "";
    const t = (tpl.content.textContent || "").replace(/\u00a0/g, " ").trim();
    return t;
  }

  function fromHost(el) {
    if (!el) return null;
    return instances.get(el) || null;
  }

  function getMarkdown(rec) {
    const live = (rec?.el && instances.get(rec.el)) || rec;
    if (!live?.editor) return "";
    try {
      let md = String(live.editor.getMarkdown?.() || "").trim();
      if (md) return md;
      // Toast UI: after theme recreate / wysiwyg sync lag, markdown can be empty while DOM has text
      if (typeof live.editor.getHTML === "function") {
        const plain = htmlToPlain(live.editor.getHTML());
        if (plain) return plain;
      }
      const ww = live.el?.querySelector?.(
        ".toastui-editor-contents .ProseMirror, .ProseMirror, .toastui-editor-ww-container"
      );
      if (ww) {
        const t = String(ww.innerText || ww.textContent || "")
          .replace(/\u00a0/g, " ")
          .trim();
        const ph = String(live.options?.placeholder || "").trim();
        if (t && t !== ph) return t;
      }
      if (live.options?.fallback) {
        const ta = live.el?.querySelector?.("textarea");
        if (ta) return String(ta.value || "").trim();
      }
      return "";
    } catch {
      return "";
    }
  }

  function fitToParent(rec) {
    if (!rec?.editor || !rec?.el || rec.options?.compact || rec.options?.growWithContent) return;
    const host = rec.el;
    const main = host.closest(".split-main.editor");
    if (!main || main.clientHeight < 80) return;
    let reserved = 0;
    main.querySelectorAll(":scope > .row.meta, :scope > #asset-link").forEach((el) => {
      if (el.offsetHeight) reserved += el.offsetHeight + 4;
    });
    const h = Math.max(240, main.clientHeight - reserved);
    if (Math.abs(h - (host._fitHeight || 0)) > 2) {
      host._fitHeight = h;
      rec.editor.height(`${h}px`);
    }
  }

  function scheduleFit(rec) {
    if (!rec || rec.options?.compact || rec.options?.growWithContent) return;
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        fitToParent(rec);
      });
    });
  }

  function setMarkdown(rec, md) {
    if (!rec?.editor) return;
    rec.editor.setMarkdown(md || "");
    if (rec.options?.growWithContent) {
      try {
        rec.editor.setHeight?.("auto");
      } catch {
        /* ignore */
      }
      rec.el?.classList.add("auto-height");
    } else {
      scheduleFit(rec);
    }
  }

  function reset(rec) {
    setMarkdown(rec, "");
  }

  function focus(rec) {
    rec?.editor?.focus?.();
  }

  function destroy(rec) {
    if (!rec) return;
    try {
      rec.el?._yizhiPopupMo?.disconnect();
      if (rec.el) rec.el._yizhiPopupMo = null;
    } catch {
      /* ignore */
    }
    try {
      rec.el?._yizhiGrowRo?.disconnect();
      if (rec.el) rec.el._yizhiGrowRo = null;
    } catch {
      /* ignore */
    }
    try {
      rec.editor?.destroy?.();
    } catch {
      /* ignore */
    }
    if (rec.el) instances.delete(rec.el);
  }

  function applyTheme() {
    document.querySelectorAll(".yizhi-rich-editor-host").forEach((host) => {
      const inst = instances.get(host);
      if (!inst?.editor) return;
      const md = getMarkdown(inst);
      const opts = { ...(inst.options || {}) };
      destroy(inst);
      const next = create(host, opts);
      if (next && md) next.editor.setMarkdown(md);
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".theme-btn").forEach((btn) => {
      btn.addEventListener("click", () => window.setTimeout(applyTheme, 0));
    });
  });

  window.addEventListener("resize", () => {
    document.querySelectorAll(".note-editor-host.yizhi-rich-editor-host").forEach((host) => {
      const inst = instances.get(host);
      if (inst) fitToParent(inst);
    });
  });

  window.YizhiRichEditor = {
    create,
    fromHost,
    getMarkdown,
    setMarkdown,
    reset,
    focus,
    destroy,
    renderMarkdown,
    applyTheme,
    fitToParent,
  };
})();
