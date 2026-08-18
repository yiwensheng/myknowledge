/** Unified background job polling, task center, and busy-state helpers */
(function () {
  const API = () => window.myknowledge?.apiBase || "http://127.0.0.1:18765";
  let pollTimer = null;
  const busyScopes = new Set();
  let handlers = {
    onUploadDone: null,
    onUrlDone: null,
    onLinkedDone: null,
    onIndexDone: null,
  };

  async function apiJson(path) {
    const res = await fetch(`${API()}${path}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  function uploadJobPct(j) {
    if (j.status === "done") return 100;
    const total = j.total || 0;
    const done = j.done || 0;
    if (j.phase === "index" || (total > 0 && done >= total)) return 92;
    if (!total) return 10;
    return Math.min(90, Math.round((90 * done) / total));
  }

  function uploadJobMessage(j) {
    const total = j.total || 0;
    const done = j.done || 0;
    if (j.phase === "index" || (total > 0 && done >= total && j.status === "running")) {
      return j.current || "正在更新检索库…";
    }
    if (j.current) return j.current;
    return `处理 ${done}/${total}`;
  }

  function normalizeJobs(data) {
    const out = [];
    for (const j of data.upload || []) {
      out.push({
        type: "upload",
        id: j.id,
        status: j.status,
        label: "文件上传",
        pct: uploadJobPct(j),
        message: uploadJobMessage(j),
        raw: j,
      });
    }
    for (const j of data.url || []) {
      out.push({
        type: "url",
        id: j.id,
        status: j.status,
        label: "网页抓取",
        pct: j.progress_pct ?? 10,
        message: j.current || j.phase || "处理中",
        raw: j,
      });
    }
    for (const j of data.linked || []) {
      out.push({
        type: "linked",
        id: j.id,
        status: j.status,
        label: "外联索引",
        pct: j.progress_pct ?? 10,
        message: j.current || ` ${j.done_files || 0}/${j.total_files || 0}`,
        raw: j,
      });
    }
    for (const j of data.index || []) {
      out.push({
        type: "index",
        id: j.id,
        status: j.status,
        label: "检索库更新",
        pct: j.progress_pct ?? 10,
        message: j.current || j.phase || "处理中",
        raw: j,
      });
    }
    return out.filter((j) => j.status === "queued" || j.status === "running");
  }

  function renderTaskCenter(jobs) {
    const btn = document.getElementById("btn-task-center");
    const drop = document.getElementById("task-center-dropdown");
    const panel = document.getElementById("global-job-panel");
    const panelText = document.getElementById("global-job-panel-text");
    const panelFill = document.getElementById("global-job-panel-fill");
    if (!btn || !drop) return;

    if (!jobs.length) {
      btn.classList.add("hidden");
      drop.classList.add("hidden");
      if (panel) panel.classList.add("hidden");
      return;
    }

    btn.classList.remove("hidden");
    btn.textContent = `任务 ${jobs.length}`;
    btn.setAttribute("aria-expanded", drop.classList.contains("hidden") ? "false" : "true");

    drop.innerHTML = jobs
      .map(
        (j) =>
          `<div class="task-center-item" data-type="${escAttr(j.type)}">` +
          `<strong>${escHtml(j.label)}</strong>` +
          `<span>${escHtml(j.message)}（${j.pct}%）</span>` +
          `<div class="task-center-bar"><span style="width:${j.pct}%"></span></div>` +
          `</div>`,
      )
      .join("");

    const primary = jobs[0];
    if (panel && panelText && panelFill) {
      panel.classList.remove("hidden");
      panelText.textContent = `${primary.label} · ${primary.message}（${primary.pct}%）`;
      panelFill.style.width = `${primary.pct}%`;
    }
  }

  function escHtml(s) {
    const d = document.createElement("div");
    d.textContent = String(s ?? "");
    return d.innerHTML;
  }
  function escAttr(s) {
    return escHtml(s).replace(/"/g, "&quot;");
  }

  function setBusy(scope, on) {
    if (!scope) return;
    if (on) busyScopes.add(scope);
    else busyScopes.delete(scope);
    document.body.classList.toggle(`busy-${scope}`, on);
    document.querySelectorAll(`[data-busy-scope="${scope}"]`).forEach((el) => {
      el.disabled = on;
      if (on && el.dataset.busyText) el.textContent = el.dataset.busyText;
      else if (!on && el.dataset.defaultText) el.textContent = el.dataset.defaultText;
    });
  }

  function isBusy(scope) {
    return busyScopes.has(scope);
  }

  let prevActiveIds = new Set();

  async function pollOnce() {
    let upload = [];
    let url = [];
    let linked = [];
    let index = [];
    try {
      upload = (await apiJson("/api/upload/jobs/active")).jobs || [];
    } catch {
      /* ignore */
    }
    try {
      url = (await apiJson("/api/url/jobs/active")).jobs || [];
    } catch {
      /* ignore */
    }
    try {
      linked = (await apiJson("/api/linked-dirs/jobs/active")).jobs || [];
    } catch {
      /* ignore */
    }
    try {
      index = (await apiJson("/api/index/jobs/active")).jobs || [];
    } catch {
      /* ignore */
    }

    const jobs = normalizeJobs({ upload, url, linked, index });
    renderTaskCenter(jobs);

    const activeIds = new Set(jobs.map((j) => `${j.type}:${j.id}`));
    for (const key of prevActiveIds) {
      if (!activeIds.has(key)) {
        const [type] = key.split(":");
        if (type === "upload" && handlers.onUploadDone) handlers.onUploadDone();
        if (type === "url" && handlers.onUrlDone) handlers.onUrlDone();
        if (type === "linked" && handlers.onLinkedDone) handlers.onLinkedDone();
        if (type === "index" && handlers.onIndexDone) handlers.onIndexDone();
      }
    }
    prevActiveIds = activeIds;

    if (jobs.length) {
      pollTimer = window.setTimeout(pollOnce, 900);
    } else {
      pollTimer = null;
    }
    return jobs;
  }

  function startPolling() {
    if (pollTimer) return;
    pollOnce();
  }

  function registerHandlers(h) {
    handlers = { ...handlers, ...h };
  }

  document.getElementById("btn-task-center")?.addEventListener("click", () => {
    const drop = document.getElementById("task-center-dropdown");
    if (!drop) return;
    drop.classList.toggle("hidden");
  });

  document.addEventListener("click", (e) => {
    const wrap = document.getElementById("task-center-wrap");
    if (!wrap || wrap.contains(e.target)) return;
    document.getElementById("task-center-dropdown")?.classList.add("hidden");
  });

  window.YizhiJobs = {
    startPolling,
    pollOnce,
    setBusy,
    isBusy,
    registerHandlers,
  };
})();
