/** 易知服务闭环：任务条 / 周历 / 场景模板 / 续费资产 */
(function () {
  const TASK_LABELS = {
    key_ok: "配置并测通大模型",
    ingest_or_note: "导入资料或写笔记",
    ask_with_cite: "完成一次带出处提问",
    distill_once: "蒸馏一次产出（可选）",
  };
  const TASK_ACTIONS = {
    key_ok: () => {
      document.getElementById("btn-settings")?.click();
      setTimeout(() => {
        const tab = document.querySelector('.modal-tab[data-tab="llm"]');
        tab?.click();
      }, 80);
    },
    ingest_or_note: () => document.querySelector('.tab[data-tab="manage"]')?.click(),
    ask_with_cite: () => document.querySelector('.tab[data-tab="ask"]')?.click(),
    distill_once: () => document.querySelector('.tab[data-tab="manage"]')?.click(),
  };

  let lastStatus = null;
  let draftRun = null;

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function api(path, opts = {}) {
    const method = (opts.method || "GET").toUpperCase();
    const headers = { ...(opts.headers || {}) };
    let body = opts.body;
    if (body != null && typeof body === "object" && !(body instanceof FormData)) {
      body = JSON.stringify(body);
      if (!headers["Content-Type"] && !headers["content-type"]) {
        headers["Content-Type"] = "application/json";
      }
    } else if (typeof body === "string" && method !== "GET" && method !== "HEAD") {
      if (!headers["Content-Type"] && !headers["content-type"]) {
        headers["Content-Type"] = "application/json";
      }
    }
    const next = { ...opts, method, headers, body };
    if (typeof window.api === "function") return window.api(path, next);
    const base = window.YIZHI_API_BASE || "";
    const r = await fetch(base + path, next);
    if (!r.ok) {
      let msg = r.statusText;
      try {
        const j = await r.json();
        msg = j.detail || j.error || msg;
      } catch {
        /* ignore */
      }
      throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    }
    const ct = r.headers.get("content-type") || "";
    if (ct.includes("application/json")) return r.json();
    return r.text();
  }

  function ensureBar() {
    let bar = document.getElementById("service-loop-bar");
    if (bar) return bar;
    bar = document.createElement("div");
    bar.id = "service-loop-bar";
    bar.className = "service-loop-bar hidden";
    bar.setAttribute("role", "region");
    bar.setAttribute("aria-label", "服务进度");
    const header = document.querySelector("header.header");
    if (header?.nextSibling) {
      header.parentNode.insertBefore(bar, header.nextSibling);
    } else {
      document.body.prepend(bar);
    }
    return bar;
  }

  function ensureTemplateModal() {
    let modal = document.getElementById("service-loop-modal");
    if (modal) return modal;
    modal = document.createElement("div");
    modal.id = "service-loop-modal";
    modal.className = "modal hidden";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    modal.innerHTML =
      `<div class="modal-backdrop" data-close-sl></div>` +
      `<div class="modal-card modal-card-form service-loop-modal-card">` +
      `<h2>场景服务模板</h2>` +
      `<p class="hint">先选场景填输入 → 生成草案 → 确认后写入笔记。不编造未提供事实，效果指标不承诺。</p>` +
      `<div id="sl-template-tabs" class="sl-template-tabs"></div>` +
      `<div id="sl-template-form" class="sl-template-form"></div>` +
      `<div class="row sl-template-actions">` +
      `<button type="button" id="sl-btn-run" class="primary">生成草案</button>` +
      `<button type="button" id="sl-btn-close">关闭</button>` +
      `</div>` +
      `<p id="sl-template-status" class="hint"></p>` +
      `<div id="sl-template-preview-wrap" class="sl-preview-wrap hidden">` +
      `<label>标题 <input id="sl-commit-title" type="text" /></label>` +
      `<textarea id="sl-template-preview" rows="14"></textarea>` +
      `<button type="button" id="sl-btn-commit" class="primary">确认写入笔记</button>` +
      `</div>` +
      `<hr class="sl-hr" />` +
      `<div id="sl-weeks" class="sl-weeks"></div>` +
      `</div>`;
    document.body.appendChild(modal);
    modal.querySelector("[data-close-sl]")?.addEventListener("click", closeModal);
    modal.querySelector("#sl-btn-close")?.addEventListener("click", closeModal);
    modal.querySelector("#sl-btn-run")?.addEventListener("click", () => runTemplate().catch(showErr));
    modal.querySelector("#sl-btn-commit")?.addEventListener("click", () => commitTemplate().catch(showErr));
    return modal;
  }

  function showErr(e) {
    const el = document.getElementById("sl-template-status");
    if (el) el.textContent = String(e?.message || e);
  }

  function closeModal() {
    document.getElementById("service-loop-modal")?.classList.add("hidden");
  }

  function openModal() {
    ensureTemplateModal().classList.remove("hidden");
    renderTemplateUi(lastStatus).catch(showErr);
  }

  function renderAssetsHtml(assets) {
    if (!assets) return "";
    return (
      `<div class="license-assets" id="license-assets-inner">` +
      `<h3 class="license-assets-title">你的知识资产（本机）</h3>` +
      `<p class="hint">停订不会删除知识库文件，但会失去继续使用这套已跑顺工作流的软件权限。以下数字仅反映本地使用，不代表业务效果。</p>` +
      `<ul class="license-assets-list">` +
      `<li>笔记等文稿：<strong>${assets.notes_count ?? 0}</strong></li>` +
      `<li>导入文件：<strong>${assets.assets_count ?? 0}</strong></li>` +
      `<li>提问次数：<strong>${assets.ask_count ?? 0}</strong>（带出处 ${assets.ask_with_cite ?? 0}）</li>` +
      `<li>蒸馏 Skills：<strong>${assets.distill_skills ?? 0}</strong></li>` +
      `<li>资料夹：<strong>${assets.folders_count ?? 0}</strong></li>` +
      `</ul></div>`
    );
  }

  window.YizhiServiceLoop = {
    refresh,
    openModal,
    probeAndMark,
    renderLicenseAssets,
    getStatus: () => lastStatus,
  };

  async function probeAndMark() {
    const r = await api("/api/llm/probe", { method: "POST", body: {} });
    if (r.ok) {
      await api("/api/service-loop", {
        method: "PATCH",
        body: { tasks: { key_ok: true } },
      });
      await refresh();
    }
    return r;
  }

  async function renderLicenseAssets(host, lic) {
    if (!host) return;
    const show =
      lic &&
      (lic.reason === "trial_expired" ||
        lic.reason === "expired" ||
        (lic.reason === "trial" && (lic.trial_days_left ?? 99) <= 7));
    if (!show) {
      host.innerHTML = "";
      host.classList.add("hidden");
      return;
    }
    try {
      const assets = await api("/api/service-loop/assets");
      host.innerHTML = renderAssetsHtml(assets);
      host.classList.remove("hidden");
    } catch {
      host.innerHTML = "";
      host.classList.add("hidden");
    }
  }

  function ensureShowToggle() {
    let btn = document.getElementById("btn-service-loop-show");
    if (btn) return btn;
    const actions = document.querySelector(".header-actions");
    if (!actions) return null;
    btn = document.createElement("button");
    btn.id = "btn-service-loop-show";
    btn.type = "button";
    btn.className = "link-btn hidden";
    btn.title = "展开本周服务进度";
    btn.textContent = "服务进度";
    const status = document.getElementById("status");
    if (status?.nextSibling) actions.insertBefore(btn, status.nextSibling);
    else actions.prepend(btn);
    return btn;
  }

  function bindShowToggle() {
    const btn = ensureShowToggle();
    if (!btn || btn.dataset.bound) return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", async () => {
      await api("/api/service-loop", {
        method: "PATCH",
        body: { dismissed_bar: false },
      });
      await refresh();
    });
  }

  function barWouldShow(status) {
    if (!status) return false;
    const tasks = status.tasks || {};
    if (status.core_loop_done && tasks.distill_once) return false;
    return true;
  }

  function renderBar(status) {
    const bar = ensureBar();
    const showBtn = ensureShowToggle();
    bindShowToggle();

    const canShow = barWouldShow(status);
    const dismissed = !!(status && status.dismissed_bar);

    // 进度条被关掉后：顶栏显示「服务进度」开关
    if (showBtn) {
      const showToggle = canShow && dismissed;
      showBtn.classList.toggle("hidden", !showToggle);
    }

    if (!status || dismissed || !canShow) {
      bar.classList.add("hidden");
      return;
    }

    const tasks = status.tasks || {};
    const items = ["key_ok", "ingest_or_note", "ask_with_cite", "distill_once"]
      .map((k) => {
        const done = !!tasks[k];
        return (
          `<button type="button" class="sl-task ${done ? "is-done" : ""}" data-task="${k}">` +
          `<span class="sl-check">${done ? "✓" : "○"}</span>${esc(TASK_LABELS[k])}` +
          `</button>`
        );
      })
      .join("");
    bar.classList.remove("hidden");
    bar.innerHTML =
      `<div class="sl-bar-main">` +
      `<strong class="sl-bar-title">本周服务进度</strong>` +
      `<div class="sl-tasks">${items}</div>` +
      `</div>` +
      `<div class="sl-bar-actions">` +
      `<button type="button" class="link-btn" id="sl-open-templates">场景模板</button>` +
      `<button type="button" class="link-btn" id="sl-dismiss">收起</button>` +
      `</div>`;
    bar.querySelectorAll("[data-task]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const fn = TASK_ACTIONS[btn.dataset.task];
        if (fn) fn();
      });
    });
    bar.querySelector("#sl-open-templates")?.addEventListener("click", openModal);
    bar.querySelector("#sl-dismiss")?.addEventListener("click", async () => {
      await api("/api/service-loop", {
        method: "PATCH",
        body: { dismissed_bar: true },
      });
      await refresh();
    });
  }

  async function renderTemplateUi(status) {
    const modal = ensureTemplateModal();
    const templates = status?.templates || (await api("/api/service-loop/templates")).templates || [];
    const tabs = modal.querySelector("#sl-template-tabs");
    const form = modal.querySelector("#sl-template-form");
    const weeksEl = modal.querySelector("#sl-weeks");
    let active = status?.scenario || templates[0]?.id || "jiaoshi";
    if (!templates.find((t) => t.id === active)) active = templates[0]?.id;

    function paintForm() {
      const t = templates.find((x) => x.id === active);
      if (!t) {
        form.innerHTML = "<p class='hint'>暂无模板</p>";
        return;
      }
      form.dataset.templateId = t.id;
      form.innerHTML =
        `<p class="sl-loop"><strong>${esc(t.label)}</strong> · ${esc(t.loop)}</p>` +
        `<p class="hint">${esc(t.blurb)}</p>` +
        (t.fields || [])
          .map((f) => {
            const req = f.required ? " required" : "";
            return (
              `<label class="persona-field">` +
              `<span>${esc(f.label)}${f.required ? " *" : ""}</span>` +
              `<textarea data-field="${esc(f.key)}" rows="2"${req}></textarea>` +
              `</label>`
            );
          })
          .join("");
    }

    tabs.innerHTML = templates
      .map(
        (t) =>
          `<button type="button" class="sl-tab ${t.id === active ? "is-active" : ""}" data-id="${esc(t.id)}">${esc(t.label)}</button>`
      )
      .join("");
    tabs.querySelectorAll("[data-id]").forEach((btn) => {
      btn.addEventListener("click", () => {
        active = btn.dataset.id;
        tabs.querySelectorAll(".sl-tab").forEach((b) => b.classList.toggle("is-active", b.dataset.id === active));
        paintForm();
        draftRun = null;
        modal.querySelector("#sl-template-preview-wrap")?.classList.add("hidden");
      });
    });
    paintForm();

    const wm = status?.week_meta || {};
    const weeks = status?.weeks || {};
    weeksEl.innerHTML =
      `<h3>试用四周剧本</h3>` +
      `<ul class="sl-week-list">` +
      ["w1", "w2", "w3", "w4"]
        .map((k) => {
          const meta = wm[k] || {};
          const w = weeks[k] || {};
          return (
            `<li class="${w.done ? "is-done" : ""}">` +
            `<strong>${esc(meta.title || k)}</strong> — ${esc(meta.hint || "")}` +
            `${w.done ? " ✓" : ""}` +
            `</li>`
          );
        })
        .join("") +
      `</ul>`;
  }

  async function runTemplate() {
    const form = document.getElementById("sl-template-form");
    const statusEl = document.getElementById("sl-template-status");
    const tid = form?.dataset.templateId;
    if (!tid) return;
    const values = {};
    form.querySelectorAll("[data-field]").forEach((el) => {
      values[el.dataset.field] = el.value;
    });
    if (statusEl) statusEl.textContent = "正在生成草案…";
    const r = await api(`/api/service-loop/templates/${encodeURIComponent(tid)}/run`, {
      method: "POST",
      body: { values },
    });
    draftRun = r;
    const wrap = document.getElementById("sl-template-preview-wrap");
    const preview = document.getElementById("sl-template-preview");
    const title = document.getElementById("sl-commit-title");
    if (wrap) wrap.classList.remove("hidden");
    if (preview) preview.value = r.markdown || "";
    if (title) title.value = `${r.title_prefix || "草案"}-${new Date().toISOString().slice(0, 10)}`;
    if (statusEl) statusEl.textContent = "请审阅草案，确认后写入笔记。";
  }

  async function commitTemplate() {
    const form = document.getElementById("sl-template-form");
    const tid = form?.dataset.templateId || draftRun?.template_id;
    const markdown = document.getElementById("sl-template-preview")?.value || "";
    const title = document.getElementById("sl-commit-title")?.value || "";
    const statusEl = document.getElementById("sl-template-status");
    if (!tid) return;
    const r = await api(`/api/service-loop/templates/${encodeURIComponent(tid)}/commit`, {
      method: "POST",
      body: { title, markdown },
    });
    if (statusEl) statusEl.textContent = r.message || "已写入";
    await refresh();
    if (typeof window.uiInfo === "function") window.uiInfo(r.message || "已写入笔记");
  }

  async function refresh() {
    try {
      lastStatus = await api("/api/service-loop");
      renderBar(lastStatus);
      if (!document.getElementById("service-loop-modal")?.classList.contains("hidden")) {
        await renderTemplateUi(lastStatus);
      }
    } catch {
      /* backend not ready */
    }
  }

  function boot() {
    ensureBar();
    ensureTemplateModal();
    refresh();
    setInterval(refresh, 60000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
