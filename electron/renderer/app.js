const API = window.myknowledge?.apiBase || "http://127.0.0.1:18765";
const SESSION_KEY = "myk-session-id";
const REMEMBER_KEY = "myk-ask-remember";
const ARCHIVE_KEY = "myk-ask-archive";
const THEME_KEY = "myk-theme";

const TYPE_ZH = {
  concept: "概念",
  entity: "人物与工具",
  source: "外部资料",
  comparison: "对比分析",
  note: "笔记",
};
const STATUS_ZH = { draft: "草稿", refined: "已整理", archived: "已归档" };
const ASSET_CAT_ZH = {
  document: "文档",
  image: "图片",
  audio: "音频",
  video: "视频",
  other: "其他",
};

function typeZh(t) {
  return TYPE_ZH[t] || t || "";
}
function statusZh(s) {
  return STATUS_ZH[s] || s || "";
}
function assetCatZh(c) {
  return ASSET_CAT_ZH[c] || c || "文件";
}

function uiError(msg) {
  const text = typeof msg === "string" ? msg : msg?.message || String(msg);
  if (window.YizhiToast?.error) window.YizhiToast.error(text);
  else alert(text);
}
function uiInfo(msg) {
  const text = typeof msg === "string" ? msg : String(msg);
  if (window.YizhiToast?.info) window.YizhiToast.info(text);
  else alert(text);
}
async function uiConfirm(msg, opts = {}) {
  if (window.YizhiConfirm?.ask) return window.YizhiConfirm.ask(msg, opts);
  return confirm(msg);
}

const DEFAULT_PAGE_SIZE = 20;

const listState = { page: 1 };
const memoState = { page: 1, tag: "", date: "" };

let foldersCache = [];
let memoFolderIds = new Set();
let noteFolderIds = new Set();
let askFolderIds = new Set();

async function loadFolders() {
  const data = await api("/api/folders");
  foldersCache = data.items || [];
  return foldersCache;
}

function folderNameById(id) {
  return foldersCache.find((f) => f.id === id)?.name || id;
}

function renderFolderChips(containerId, selectedSet, onChange) {
  const container =
    typeof containerId === "string" ? document.getElementById(containerId) : containerId;
  if (!container) return;
  container.innerHTML = "";
  container.classList.add("folder-chips-row");
  if (!foldersCache.length) {
    const hint = document.createElement("span");
    hint.className = "hint folder-chips-hint";
    hint.textContent = "暂无资料夹";
    container.appendChild(hint);
    return;
  }
  for (const f of foldersCache) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "folder-chip" + (selectedSet.has(f.id) ? " active" : "");
    btn.textContent = f.name;
    btn.title = f.name;
    btn.addEventListener("click", () => {
      if (selectedSet.has(f.id)) selectedSet.delete(f.id);
      else selectedSet.add(f.id);
      onChange?.([...selectedSet]);
      renderFolderChips(container, selectedSet, onChange);
    });
    container.appendChild(btn);
  }
}

function getAskFolderIds() {
  return [...askFolderIds];
}

function refreshAllFolderChips() {
  renderFolderChips("memo-folder-chips", memoFolderIds);
  renderFolderChips("note-folder-chips", noteFolderIds);
  renderFolderChips("ask-folder-chips", askFolderIds);
}

async function renderFoldersManageList() {
  await loadFolders();
  const ul = document.getElementById("folders-list");
  if (!ul) return;
  ul.innerHTML = "";
  for (const f of foldersCache) {
    const li = document.createElement("li");
    li.className = "folders-list-item";
    const input = document.createElement("input");
    input.type = "text";
    input.className = "folder-rename-input";
    input.value = f.name;
    input.title = "重命名资料夹";
    const btnRename = document.createElement("button");
    btnRename.type = "button";
    btnRename.textContent = "重命名";
    btnRename.addEventListener("click", async () => {
      const name = input.value.trim();
      if (!name || name === f.name) return;
      try {
        const data = await api(`/api/folders?id=${encodeURIComponent(f.id)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name }),
        });
        foldersCache = data.items || [];
        renderFoldersManageList();
        refreshAllFolderChips();
        setStatus("资料夹已重命名");
      } catch (e) {
        uiError(e);
      }
    });
    const btnDel = document.createElement("button");
    btnDel.type = "button";
    btnDel.className = "danger";
    btnDel.textContent = "删除";
    btnDel.addEventListener("click", async () => {
      if (!(await uiConfirm(`删除资料夹「${f.name}」？\n\n已关联的内容不会删除，仅移除标签。`))) return;
      try {
        const data = await api(`/api/folders?id=${encodeURIComponent(f.id)}`, { method: "DELETE" });
        foldersCache = data.items || [];
        for (const set of [memoFolderIds, noteFolderIds, askFolderIds]) {
          set.delete(f.id);
        }
        renderFoldersManageList();
        refreshAllFolderChips();
        loadLinkedDirs();
        loadLibrary();
        setStatus("资料夹已删除");
      } catch (e) {
        uiError(e);
      }
    });
    li.append(input, btnRename, btnDel);
    ul.appendChild(li);
  }
  if (!foldersCache.length) {
    ul.innerHTML = '<li class="hint">暂无资料夹，请下方添加。</li>';
  }
  refreshAllFolderChips();
}

async function loadFoldersManage() {
  try {
    await renderFoldersManageList();
  } catch (e) {
    const ul = document.getElementById("folders-list");
    if (ul) ul.innerHTML = `<li class="hint">${escHtml(String(e))}</li>`;
  }
}

async function saveLinkedDirFolders(path, folderIds) {
  await api(`/api/linked-dirs/folders?path=${encodeURIComponent(path)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ folder_ids: folderIds }),
  });
}

async function saveAssetFolders(assetId, folderIds) {
  return api(`/api/library/assets/${encodeURIComponent(assetId)}/folders`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ folder_ids: folderIds }),
  });
}

async function openAssetFolderEditor(asset, tr) {
  if (!foldersCache.length) await loadFolders();
  const titleCell = tr.querySelector(".col-title");
  if (!titleCell) return;
  const existing = titleCell.querySelector(".asset-folder-editor");
  if (existing) {
    existing.remove();
    return;
  }
  const editor = document.createElement("div");
  editor.className = "asset-folder-editor folder-chips-wrap";
  const selected = new Set(asset.folder_ids || []);
  const onChange = async (ids) => {
    try {
      const rec = await saveAssetFolders(asset.id, ids);
      asset.folder_ids = rec.folder_ids || ids;
      setStatus("文件资料夹已更新");
      loadLibrary();
    } catch (e) {
      uiError(e);
      renderFolderChips(editor, new Set(asset.folder_ids || []), onChange);
    }
  };
  renderFolderChips(editor, selected, onChange);
  titleCell.appendChild(editor);
}

function renderLinkedDirFolderCell(item) {
  const td = document.createElement("td");
  td.className = "col-folders";
  const wrap = document.createElement("div");
  wrap.className = "linked-dir-folder-chips folder-chips-row";
  const selected = new Set(item.folder_ids || []);
  const onChange = async (ids) => {
    try {
      await saveLinkedDirFolders(item.path, ids);
      item.folder_ids = ids;
      setStatus("外联目录资料夹已更新");
    } catch (e) {
      uiError(e);
      renderFolderChips(wrap, new Set(item.folder_ids || []), onChange);
    }
  };
  renderFolderChips(wrap, selected, onChange);
  td.appendChild(wrap);
  return td;
}

function syncNoteFolderIds(ids) {
  noteFolderIds = new Set(ids || []);
  renderFolderChips("note-folder-chips", noteFolderIds);
}

function beijingTodayStr() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai" }).format(new Date());
}

function initMemoDatePicker() {
  const picker = document.getElementById("memo-date-picker");
  if (!picker) return;
  if (!memoState.date) memoState.date = beijingTodayStr();
  picker.value = memoState.date;
  picker.addEventListener("change", () => {
    memoState.date = picker.value || beijingTodayStr();
    memoState.page = 1;
    refreshMemos();
  });
}

function formatMemoDateLabel(dateStr) {
  const today = beijingTodayStr();
  if (dateStr === today) return "今天";
  const d = new Date(`${dateStr}T12:00:00+08:00`);
  if (Number.isNaN(d.getTime())) return dateStr;
  const wd = ["日", "一", "二", "三", "四", "五", "六"][d.getDay()];
  return `${dateStr} 周${wd}`;
}
let notesView = "timeline";
let memoEditorRec = null;
let noteEditorRec = null;

function initRichEditors() {
  const RE = window.YizhiRichEditor;
  if (!RE?.create) {
    console.warn("[易知] YizhiRichEditor 未加载");
    return;
  }
  try {
    const memoHost = document.getElementById("memo-editor-host");
    if (memoHost && !memoEditorRec) {
      memoEditorRec = RE.create(memoHost, {
        apiBase: API,
        compact: true,
        placeholder: "写闪念… 支持标题、列表、图片与 #标签，Ctrl+Enter 保存",
      });
      memoHost.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
          e.preventDefault();
          saveQuickMemo();
        }
      });
    }
    // 笔记正文编辑器在默认隐藏的面板内：勿在 display:none 时创建（ToastUI 高度会坏）
    // 切到「编辑器」视图时由 ensureNoteEditor() 懒加载
  } catch (err) {
    console.error("[易知] 初始化编辑器失败", err);
    uiError("笔记编辑器初始化失败，请重启易知。若仍不行请重装完整安装包。");
  }
}

function ensureNoteEditor() {
  const RE = window.YizhiRichEditor;
  const noteHost = document.getElementById("edit-body-host");
  if (!RE?.create || !noteHost) return null;
  const editorView = document.getElementById("notes-editor-view");
  if (editorView?.classList.contains("hidden")) return noteEditorRec;
  // 主题切换会重建 ToastUI，须用 live 实例（闪念同理）
  const live = RE.fromHost?.(noteHost);
  if (live?.editor) {
    noteEditorRec = live;
    window.setTimeout(() => RE.fitToParent?.(noteEditorRec), 40);
    return noteEditorRec;
  }
  try {
    noteEditorRec = RE.create(noteHost, {
      apiBase: API,
      placeholder: "正文… 支持标题、列表、表格、代码块与图片",
      minHeight: "320px",
    });
    window.setTimeout(() => RE.fitToParent?.(noteEditorRec), 40);
    return noteEditorRec;
  } catch (err) {
    console.error("[易知] 笔记编辑器创建失败", err);
    uiError("无法创建笔记编辑器");
    return null;
  }
}

function getNoteBodyMarkdown() {
  ensureNoteEditor();
  return window.YizhiRichEditor?.getMarkdown(noteEditorRec) || "";
}

function setNoteBodyMarkdown(md) {
  ensureNoteEditor();
  window.YizhiRichEditor?.setMarkdown(noteEditorRec, md || "");
  window.setTimeout(() => window.YizhiRichEditor?.fitToParent?.(noteEditorRec), 60);
}

function getMemoInputMarkdown() {
  const host = document.getElementById("memo-editor-host");
  if (host && window.YizhiRichEditor?.fromHost) {
    const live = window.YizhiRichEditor.fromHost(host);
    if (live) memoEditorRec = live;
  }
  if (!memoEditorRec && host) {
    initRichEditors();
  }
  return window.YizhiRichEditor?.getMarkdown(memoEditorRec) || "";
}

function clearMemoInput() {
  window.YizhiRichEditor?.reset(memoEditorRec);
}
const assetsState = { page: 1 };
const historyState = { page: 1 };
const queryState = { page: 1 };
const libAssetsState = { page: 1, q: "" };
const maintenanceState = { draftTotal: 0, busy: false };
let manageView = "import";

function setManageView(view) {
  manageView = view;
  document.querySelectorAll(".manage-tab").forEach((btn) => {
    const on = btn.dataset.manageView === view;
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });
  document.querySelectorAll(".manage-view").forEach((el) => {
    el.classList.toggle("hidden", el.id !== `manage-view-${view}`);
  });
  if (view === "import") loadWorkflows();
  else if (view === "drafts") loadMaintenanceDrafts();
  else if (view === "linked") {
    loadFolders().then(() => loadLinkedDirs()).catch(() => loadLinkedDirs());
  }
  else if (view === "assets") loadAssets();
}
const libRagState = { page: 1, q: "" };
const libExternalState = { page: 1, q: "" };
let libraryView = "assets";

function openAssetFile(path) {
  window.open(`${API}/api/assets/file?path=${encodeURIComponent(path)}`);
}

function assetExt(name) {
  const i = String(name || "").lastIndexOf(".");
  return i >= 0 ? name.slice(i + 1).toUpperCase() : "—";
}

async function browseAsset(asset, page = 0) {
  const openViewer = async () => {
    if (window.myknowledge?.openAssetViewer) {
      await window.myknowledge.openAssetViewer(asset.rel_path, asset.filename, page || 0);
      return;
    }
    const q = new URLSearchParams({
      path: asset.rel_path,
      name: asset.filename || "",
    });
    if (page) q.set("page", String(page));
    window.open(`${API}/viewer?${q.toString()}`);
  };

  try {
    let health = await fetch(`${API}/api/health`).then((r) => r.json());
    if (!health?.file_viewer?.ready) {
      if (window.myknowledge?.ensureFileViewer) {
        const r = await window.myknowledge.ensureFileViewer();
        if (!r?.ok) throw new Error(r?.error || "预览组件安装失败");
      }
      health = await fetch(`${API}/api/health`).then((r) => r.json());
    }
    if (!health?.file_viewer?.ready) {
      const tip = window.myknowledge
        ? "文件预览资源未就绪。请完全退出易知后重新打开；若仍失败，请重装完整安装包或联系客服。"
        : "文件预览组件未能自动安装。请确认已安装 Node.js，并重新运行「启动易知.bat」。";
      uiError(tip);
      return;
    }
    await openViewer();
  } catch (e) {
    uiError(e.message || e);
  }
}

async function renameLibraryAsset(asset) {
  const next = prompt("重命名文件", asset.filename);
  if (next === null) return;
  const filename = next.trim();
  if (!filename || filename === asset.filename) return;
  try {
    await api(`/api/library/assets/${encodeURIComponent(asset.id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename }),
    });
    await loadLibrary();
  } catch (e) {
    uiError(e);
  }
}

async function deleteLibraryAsset(asset) {
  const ok = await uiConfirm(`确定删除「${asset.filename}」？\n\n将同时删除关联笔记与检索片段。`);
  if (!ok) return;
  try {
    await api(`/api/library/assets/${encodeURIComponent(asset.id)}`, { method: "DELETE" });
    await loadLibrary();
  } catch (e) {
    uiError(e);
  }
}

function renderPager(containerId, meta, onPage) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = "";
  if (!meta || meta.pages <= 1) return;
  const prev = document.createElement("button");
  prev.type = "button";
  prev.textContent = "上一页";
  prev.disabled = meta.page <= 1;
  prev.addEventListener("click", () => onPage(meta.page - 1));
  const info = document.createElement("span");
  info.className = "pager-info";
  info.textContent = `第 ${meta.page}/${meta.pages} 页 · 共 ${meta.total} 条`;
  const next = document.createElement("button");
  next.type = "button";
  next.textContent = "下一页";
  next.disabled = meta.page >= meta.pages;
  next.addEventListener("click", () => onPage(meta.page + 1));
  el.appendChild(prev);
  el.appendChild(info);
  el.appendChild(next);
}

function applyTheme(theme) {
  const next = theme === "light" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem(THEME_KEY, next);
  document.querySelectorAll(".theme-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.theme === next);
  });
  window.YizhiRichEditor?.applyTheme?.();
}

function initTheme() {
  applyTheme(localStorage.getItem(THEME_KEY) || "dark");
  document.querySelectorAll(".theme-btn").forEach((btn) => {
    btn.addEventListener("click", () => applyTheme(btn.dataset.theme));
  });
}

initTheme();

function escHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function getSessionId() {
  let id = localStorage.getItem(SESSION_KEY);
  if (!id) {
    id = crypto.randomUUID().replace(/-/g, "").slice(0, 16);
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

function setSessionId(id) {
  localStorage.setItem(SESSION_KEY, id);
}

function initAskPrefs() {
  const rememberEl = document.getElementById("ask-remember");
  const archiveEl = document.getElementById("ask-archive");
  const remember = localStorage.getItem(REMEMBER_KEY);
  const archive = localStorage.getItem(ARCHIVE_KEY);
  if (rememberEl && remember !== null) rememberEl.checked = remember === "1";
  if (archiveEl && archive !== null) archiveEl.checked = archive === "1";
}

function renderTurnPlain(turn) {
  const div = document.createElement("div");
  div.className = `history-turn history-${turn.role}`;
  if (turn.role === "user") {
    div.innerHTML = `<p class="hist-q"><strong>问：</strong>${escHtml(turn.content)}</p>`;
  } else {
    div.innerHTML = `<div class="hist-a"><strong>答：</strong><div class="hist-body">${escHtml(turn.content).replace(/\n/g, "<br>")}</div></div>`;
  }
  return div;
}

async function renderAskThread() {
  const out = document.getElementById("ask-output");
  if (!out || askStreaming) return;
  const remember = document.getElementById("ask-remember")?.checked;
  if (!remember) {
    out.innerHTML = "";
    return;
  }
  try {
    const data = await api(`/api/memory/session?session_id=${encodeURIComponent(getSessionId())}`);
    out.innerHTML = "";
    for (const t of data.turns || []) {
      out.appendChild(renderTurnPlain(t));
    }
    out.scrollTop = out.scrollHeight;
  } catch {
    out.innerHTML = "";
  }
}

function refreshSessionHint() {  const el = document.getElementById("ask-session-hint");
  if (!el) return;
  const remember = document.getElementById("ask-remember")?.checked;
  if (!remember) {
    el.textContent = "单次提问模式：不会记住上一句";
    return;
  }
  el.textContent = "已开启连续对话，可以继续追问上一题";
}

document.getElementById("btn-new-session")?.addEventListener("click", () => {
  const id = crypto.randomUUID().replace(/-/g, "").slice(0, 16);
  setSessionId(id);
  document.getElementById("ask-output").innerHTML = "";
  hideAskFeedbackBar();
  refreshSessionHint();
});

document.getElementById("ask-remember")?.addEventListener("change", (e) => {
  localStorage.setItem(REMEMBER_KEY, e.target.checked ? "1" : "0");
  refreshSessionHint();
  renderAskThread();
});
document.getElementById("ask-archive")?.addEventListener("change", (e) => {
  localStorage.setItem(ARCHIVE_KEY, e.target.checked ? "1" : "0");
});
initAskPrefs();
refreshSessionHint();
renderAskThread();

const CONTINUITY_COLLAPSE_KEY = "myk-continuity-collapsed";
const CONTINUITY_DISMISS_KEY = "myk-continuity-dismiss-date";
let lastContinuity = null;

function beijingDateYmd() {
  try {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Shanghai",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date());
  } catch {
    const d = new Date();
    return d.toISOString().slice(0, 10);
  }
}

function formatContinuityHtml(data) {
  const title = data.last_session_title || "（尚无上次对话）";
  const purpose = data.purpose_excerpt || "（未配置 purpose.md）";
  const wd = data.week_delta || {};
  const evo = `近7日：+${wd.rules_added || 0} 条规则 · +${wd.qa_added || 0} 次问答 · +${wd.archived_added || 0} 篇归档`;
  return (
    `<strong>上次：</strong>${escHtml(title)}` +
    (data.last_session_updated ? ` <span class="muted">(${escHtml(data.last_session_updated)})</span>` : "") +
    `<br><strong>目标：</strong>${escHtml(purpose)}` +
    `<br><strong>规则：</strong>启用 ${data.rules_enabled ?? 0} / 共 ${data.rules_total ?? 0}` +
    `<br>${escHtml(evo)}`
  );
}

async function refreshContinuityBar() {
  const textEl = document.getElementById("ask-continuity-text");
  if (!textEl) return;
  try {
    lastContinuity = await api("/api/memory/continuity");
    textEl.innerHTML = formatContinuityHtml(lastContinuity);
  } catch (e) {
    textEl.textContent = "续航信息暂不可用：" + String(e);
  }
  await refreshFortuneStrip();
}

let lastFortune = null;

function formatFortuneHtml(data) {
  if (!data?.enabled || !data.slip) return "";
  const slip = data.slip;
  const yi = (slip.yi || []).map((x) => escHtml(x)).join("、");
  const ji = (slip.ji || []).map((x) => escHtml(x)).join("、");
  const lib = data.library;
  const vibe = lib?.vibe ? ` · 库况「${escHtml(lib.vibe)}」` : "";
  let body =
    `<strong>今日知签</strong>（${escHtml(slip.date || "")}）${vibe}<br>` +
    `<span class="fortune-yi"><strong>宜</strong> ${yi}</span><br>` +
    `<span class="fortune-ji"><strong>忌</strong> ${ji}</span><br>` +
    `<em>${escHtml(slip.motto || "")}</em>`;
  if (lib?.lines?.length) {
    body += `<br><strong>库运势</strong>：${escHtml(lib.lines[0] || "")}`;
  }
  body += `<br><span class="muted">${escHtml(slip.disclaimer || "")}</span>`;
  return body;
}

function formatFortunePanelHtml(data) {
  if (!data?.enabled) {
    return `<p class="hint">知签已关闭。可在「设置 → 对话与记忆」开启「今日知签 / 库运势」。</p>`;
  }
  const slip = data.slip || {};
  const lib = data.library || {};
  const yi = (slip.yi || []).map((x) => `<li>${escHtml(x)}</li>`).join("");
  const ji = (slip.ji || []).map((x) => `<li>${escHtml(x)}</li>`).join("");
  const lines = (lib.lines || []).map((x) => `<li>${escHtml(x)}</li>`).join("");
  return (
    `<p><strong>${escHtml(slip.date || "")}</strong> · 库况「${escHtml(lib.vibe || "—")}」</p>` +
    `<p class="fortune-yi"><strong>宜</strong></p><ul>${yi || "<li>—</li>"}</ul>` +
    `<p class="fortune-ji"><strong>忌</strong></p><ul>${ji || "<li>—</li>"}</ul>` +
    `<p><em>${escHtml(slip.motto || "")}</em></p>` +
    `<p><strong>库运势</strong></p><ul>${lines || "<li>—</li>"}</ul>` +
    `<p class="muted">${escHtml(lib.disclaimer || slip.disclaimer || "")}</p>`
  );
}

async function refreshFortuneStrip() {
  const slipEl = document.getElementById("ask-fortune-slip");
  const btn = document.getElementById("btn-open-fortune");
  try {
    lastFortune = await api("/api/memory/fortune?record=1");
    const on = !!(lastFortune?.enabled && lastFortune?.slip);
    if (slipEl) {
      slipEl.classList.toggle("hidden", !on);
      slipEl.innerHTML = on ? formatFortuneHtml(lastFortune) : "";
    }
    if (btn) btn.classList.toggle("hidden", !on);
  } catch {
    if (slipEl) {
      slipEl.classList.add("hidden");
      slipEl.textContent = "";
    }
    if (btn) btn.classList.add("hidden");
  }
}

function openFortuneModal() {
  const modal = document.getElementById("fortune-modal");
  const body = document.getElementById("fortune-modal-body");
  if (!modal || !body) return;
  body.innerHTML = formatFortunePanelHtml(lastFortune);
  modal.classList.remove("hidden");
}

function closeFortuneModal() {
  document.getElementById("fortune-modal")?.classList.add("hidden");
}

function renderFortuneSlipsList(data) {
  const ul = document.getElementById("memory-fortune-slips");
  if (!ul) return;
  const items = data?.slips?.items || [];
  if (!items.length) {
    ul.innerHTML = "<li class='hint'>尚无签册记录；打开提问页或点「记入今日签册」即可开始。</li>";
    return;
  }
  ul.innerHTML = "";
  for (const row of items) {
    const li = document.createElement("li");
    const yi = (row.yi || []).join("、");
    const ji = (row.ji || []).join("、");
    li.innerHTML =
      `<div><strong>${escHtml(row.date || "")}</strong>` +
      (row.recorded_at ? ` <span class="muted">${escHtml(row.recorded_at)}</span>` : "") +
      `</div>` +
      `<div class="hint">宜 ${escHtml(yi)} · 忌 ${escHtml(ji)}</div>` +
      (row.motto ? `<div class="hint"><em>${escHtml(row.motto)}</em></div>` : "");
    ul.appendChild(li);
  }
}

async function loadFortunePane() {
  const body = document.getElementById("memory-fortune-body");
  if (!body) return;
  body.innerHTML = "<p class='hint'>加载中…</p>";
  try {
    lastFortune = await api("/api/memory/fortune?record=1");
    body.innerHTML = formatFortunePanelHtml(lastFortune);
    renderFortuneSlipsList(lastFortune);
    await refreshFortuneStrip();
  } catch (e) {
    body.innerHTML = `<p class="error">${escHtml(String(e))}</p>`;
  }
}

async function setupProduceRitual() {
  const box = document.getElementById("produce-ritual-box");
  const host = document.getElementById("produce-ritual-checks");
  const stamp = document.getElementById("produce-ritual-stamp");
  if (!box || !host) return;
  try {
    const data = await api("/api/memory/fortune/checklist");
    const on = !!data.enabled_by_setting;
    box.classList.toggle("hidden", !on);
    if (!on) return;
    host.innerHTML = "";
    for (const item of data.items || []) {
      const lab = document.createElement("label");
      lab.className = "inline-check";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.dataset.ritualId = item.id || "";
      cb.addEventListener("change", () => {
        const all = [...host.querySelectorAll("input[type=checkbox]")];
        const ok = all.length > 0 && all.every((c) => c.checked);
        stamp?.classList.toggle("hidden", !ok);
      });
      lab.appendChild(cb);
      lab.appendChild(document.createTextNode(" " + (item.label || item.id || "")));
      host.appendChild(lab);
    }
    stamp?.classList.add("hidden");
    if (stamp && data.stamp) stamp.textContent = "✓ " + data.stamp;
  } catch {
    box.classList.add("hidden");
  }
}

document.getElementById("btn-open-fortune")?.addEventListener("click", () => openFortuneModal());
document.getElementById("btn-fortune-modal-close")?.addEventListener("click", () => closeFortuneModal());
document.querySelector("[data-close-fortune]")?.addEventListener("click", () => closeFortuneModal());
document.getElementById("btn-fortune-modal-memory")?.addEventListener("click", () => {
  closeFortuneModal();
  switchTab("memory");
  document.querySelector('.memory-tab[data-memory-tab="fortune"]')?.click();
});
document.getElementById("btn-fortune-refresh")?.addEventListener("click", () => loadFortunePane());
document.getElementById("btn-fortune-checkin")?.addEventListener("click", async () => {
  try {
    await api("/api/memory/fortune/checkin", { method: "POST" });
    window.YizhiToast?.info?.("已记入签册");
    await loadFortunePane();
  } catch (e) {
    uiInfo(String(e));
  }
});

function applyContinuityCollapsed() {
  const bar = document.getElementById("ask-continuity-bar");
  const btn = document.getElementById("btn-continuity-toggle");
  if (!bar) return;
  const collapsed = localStorage.getItem(CONTINUITY_COLLAPSE_KEY) === "1";
  bar.classList.toggle("collapsed", collapsed);
  if (btn) {
    btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
    btn.textContent = collapsed ? "▸" : "▾";
  }
}

async function continuityContinue() {
  const sid = lastContinuity?.last_session_id || localStorage.getItem(SESSION_KEY);
  if (sid) setSessionId(sid);
  document.getElementById("ask-remember").checked = true;
  localStorage.setItem(REMEMBER_KEY, "1");
  refreshSessionHint();
  await renderAskThread();
  switchTab("ask");
  closeContinuityModal();
}

async function continuityNewSession() {
  const id = crypto.randomUUID().replace(/-/g, "").slice(0, 16);
  setSessionId(id);
  document.getElementById("ask-output").innerHTML = "";
  hideAskFeedbackBar();
  refreshSessionHint();
  await refreshContinuityBar();
  closeContinuityModal();
}

function closeContinuityModal() {
  document.getElementById("continuity-modal")?.classList.add("hidden");
}

function maybeShowContinuityModal() {
  const today = beijingDateYmd();
  if (localStorage.getItem(CONTINUITY_DISMISS_KEY) === today) return;
  const modal = document.getElementById("continuity-modal");
  const body = document.getElementById("continuity-modal-body");
  if (!modal || !body || !lastContinuity) return;
  if (!lastContinuity.last_session_id && !(lastContinuity.rules_total > 0)) return;
  body.innerHTML = formatContinuityHtml(lastContinuity);
  modal.classList.remove("hidden");
}

document.getElementById("btn-continuity-toggle")?.addEventListener("click", () => {
  const collapsed = localStorage.getItem(CONTINUITY_COLLAPSE_KEY) === "1";
  localStorage.setItem(CONTINUITY_COLLAPSE_KEY, collapsed ? "0" : "1");
  applyContinuityCollapsed();
});
document.getElementById("btn-continuity-continue")?.addEventListener("click", () => continuityContinue());
document.getElementById("btn-continuity-new")?.addEventListener("click", () => continuityNewSession());
document.getElementById("btn-continuity-modal-continue")?.addEventListener("click", () => continuityContinue());
document.getElementById("btn-continuity-modal-new")?.addEventListener("click", () => continuityNewSession());
document.getElementById("btn-continuity-dismiss-today")?.addEventListener("click", () => {
  localStorage.setItem(CONTINUITY_DISMISS_KEY, beijingDateYmd());
  closeContinuityModal();
});
document.querySelectorAll("[data-close-continuity]").forEach((el) => {
  el.addEventListener("click", closeContinuityModal);
});
document.getElementById("btn-open-memory-panel")?.addEventListener("click", () => {
  switchTab("memory");
  refreshMemoryPanel();
});

applyContinuityCollapsed();
refreshContinuityBar().then(() => maybeShowContinuityModal());
setupProduceRitual();

function relatedQaFooterHtml(items) {
  if (!items?.length) return "";
  const lis = items
    .map((e) => {
      const q = escHtml((e.question || "").slice(0, 80));
      const id = e.id != null ? `#${e.id}` : "";
      const at = e.at ? ` · ${escHtml(e.at)}` : "";
      return `<li>${id} ${q}${at}</li>`;
    })
    .join("");
  return `<footer class="related-qa-footer"><p>参考历史问答</p><ul>${lis}</ul></footer>`;
}

function distillSourcesFooterHtml(items) {
  if (!items?.length) return "";
  const lis = items
    .map((e) => {
      const layer = e.layer === "principle" ? "原则" : "技能";
      const title = escHtml((e.title || "").slice(0, 60));
      const path = escHtml(e.rel_path || "");
      return `<li><span class="distill-layer">${layer}</span> ${title}${path ? ` · <code>${path}</code>` : ""}</li>`;
    })
    .join("");
  return `<footer class="distill-sources-footer"><p>个人技能与原则</p><ul>${lis}</ul></footer>`;
}

async function refreshMemoryPanel() {
  const banner = document.getElementById("memory-evolution-banner");
  try {
    const evo = await api("/api/memory/evolution?refresh=1");
    const wd = evo.week_delta || {};
    if (banner) {
      banner.textContent =
        `进化：启用规则 ${evo.rules_enabled}/${evo.rules_total} · 问答 ${evo.qa_log_entries} · 归档 ${evo.qa_archived_notes} · 会话 ${evo.sessions}` +
        ` ｜ 近7日 +${wd.rules_added || 0} 规则 / +${wd.qa_added || 0} 问答 / +${wd.archived_added || 0} 归档`;
    }
  } catch {
    if (banner) banner.textContent = "进化统计暂不可用";
  }
  await Promise.all([loadMemoryRules(), loadMemorySessions(), loadMemoryAudit(), loadContrarianAssumptions(), loadFortunePane()]);
}

async function loadContrarianAssumptions() {
  const ul = document.getElementById("memory-contrarian-list");
  const status = document.getElementById("contrarian-status");
  if (!ul) return;
  ul.innerHTML = "<li class='hint'>加载中…</li>";
  try {
    const data = await api("/api/memory/contrarian/assumptions?limit=80");
    const items = data.items || [];
    if (status && !status.dataset.scanMsg) {
      status.textContent = items.length
        ? `已收集 ${items.length} 条核心假设。`
        : "暂无假设。请开启「导入与入库 → 矛盾检测」后重新分析入库，或在笔记 YAML 写 assumptions。";
    }
    if (!items.length) {
      ul.innerHTML = "<li class='hint'>暂无假设可扫描。</li>";
      return;
    }
    ul.innerHTML = "";
    for (const row of items) {
      const li = document.createElement("li");
      li.innerHTML =
        `<div><strong>${escHtml(row.title || "")}</strong> · <code>${escHtml(row.rel_path || "")}</code></div>` +
        `<div class="hint">${escHtml((row.assumption || "").slice(0, 240))}</div>`;
      ul.appendChild(li);
    }
  } catch (e) {
    ul.innerHTML = `<li class="error">${escHtml(String(e))}</li>`;
  }
}

document.getElementById("btn-contrarian-refresh")?.addEventListener("click", () => {
  const status = document.getElementById("contrarian-status");
  if (status) delete status.dataset.scanMsg;
  loadContrarianAssumptions();
});

document.getElementById("btn-contrarian-scan")?.addEventListener("click", async () => {
  const btn = document.getElementById("btn-contrarian-scan");
  const status = document.getElementById("contrarian-status");
  if (btn) btn.disabled = true;
  if (status) {
    status.dataset.scanMsg = "1";
    status.textContent = "正在扫描矛盾（可能调用大模型）…";
  }
  try {
    const res = await api("/api/memory/contrarian/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ write_draft: true }),
    });
    const conflicts = res.conflicts || [];
    let msg = res.message || "完成";
    if (res.draft_path) msg += ` · 对照稿：${res.draft_path}`;
    if (status) {
      status.dataset.scanMsg = "1";
      status.textContent = msg;
    }
    if (conflicts.length) {
      const ul = document.getElementById("memory-contrarian-list");
      if (ul) {
        ul.innerHTML = "";
        for (const c of conflicts) {
          const li = document.createElement("li");
          li.innerHTML =
            `<div class="hint">冲突</div>` +
            `<div><strong>A</strong>（${escHtml(c.path_a || "—")}）：${escHtml(c.a || "")}</div>` +
            `<div><strong>B</strong>（${escHtml(c.path_b || "—")}）：${escHtml(c.b || "")}</div>` +
            (c.why ? `<div class="hint">${escHtml(c.why)}</div>` : "");
          ul.appendChild(li);
        }
      }
    } else {
      await loadContrarianAssumptions();
    }
  } catch (e) {
    if (status) {
      status.dataset.scanMsg = "1";
      status.textContent = `扫描失败：${e.message || e}`;
    }
  } finally {
    if (btn) btn.disabled = false;
  }
});

async function loadMemoryRules() {
  const ul = document.getElementById("memory-rules-list");
  if (!ul) return;
  ul.innerHTML = "<li class='hint'>加载中…</li>";
  try {
    const data = await api("/api/output-rules");
    const rules = data.rules || [];
    if (!rules.length) {
      ul.innerHTML = "<li class='hint'>暂无输出规则。可在提问后「将纠错写入输出规则」。</li>";
      return;
    }
    ul.innerHTML = "";
    for (const r of rules) {
      const li = document.createElement("li");
      li.className = "memory-rule-item";
      li.innerHTML =
        `<div><code>${escHtml(r.id)}</code> · ${escHtml(r.at || "")} · ${r.enabled ? "启用" : "已关闭"}</div>` +
        `<div class="hint">${escHtml((r.text || "").slice(0, 200))}</div>` +
        `<div class="memory-rule-actions">` +
        `<label class="inline-check"><input type="checkbox" data-rule-enable="${escHtml(r.id)}" ${r.enabled ? "checked" : ""}/> 启用</label>` +
        `<button type="button" data-rule-delete="${escHtml(r.id)}">删除</button>` +
        `</div>`;
      ul.appendChild(li);
    }
    ul.querySelectorAll("[data-rule-enable]").forEach((inp) => {
      inp.addEventListener("change", async () => {
        const id = inp.getAttribute("data-rule-enable");
        await api(`/api/output-rules/${encodeURIComponent(id)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enabled: inp.checked }),
        });
        refreshContinuityBar();
        loadMemoryRules();
      });
    });
    ul.querySelectorAll("[data-rule-delete]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.getAttribute("data-rule-delete");
        if (!confirm("删除该规则？")) return;
        await api(`/api/output-rules/${encodeURIComponent(id)}`, { method: "DELETE" });
        refreshContinuityBar();
        loadMemoryRules();
      });
    });
  } catch (e) {
    ul.innerHTML = `<li class="error">${escHtml(String(e))}</li>`;
  }
}

async function loadMemorySessions() {
  const ul = document.getElementById("memory-sessions-list");
  if (!ul) return;
  ul.innerHTML = "<li class='hint'>加载中…</li>";
  try {
    const sessions = await api("/api/memory/sessions");
    if (!sessions?.length) {
      ul.innerHTML = "<li class='hint'>暂无会话</li>";
      return;
    }
    ul.innerHTML = "";
    for (const s of sessions) {
      const li = document.createElement("li");
      li.className = "memory-session-item";
      const title = s.title || s.preview || s.id;
      li.innerHTML =
        `<div><strong>${escHtml(title)}</strong> · ${escHtml(s.updated || "")} · ${s.turn_count || 0} 轮</div>` +
        (s.summary ? `<div class="hint">摘要：${escHtml(s.summary.slice(0, 160))}</div>` : "") +
        `<div class="memory-session-actions">` +
        `<button type="button" data-sess-continue="${escHtml(s.id)}">继续</button>` +
        `<button type="button" data-sess-summarize="${escHtml(s.id)}">生成摘要</button>` +
        `<button type="button" data-sess-delete="${escHtml(s.id)}">删除</button>` +
        `</div>`;
      ul.appendChild(li);
    }
    ul.querySelectorAll("[data-sess-continue]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        setSessionId(btn.getAttribute("data-sess-continue"));
        document.getElementById("ask-remember").checked = true;
        localStorage.setItem(REMEMBER_KEY, "1");
        await renderAskThread();
        switchTab("ask");
      });
    });
    ul.querySelectorAll("[data-sess-summarize]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        btn.disabled = true;
        try {
          await api(`/api/memory/session/${encodeURIComponent(btn.getAttribute("data-sess-summarize"))}/summarize`, {
            method: "POST",
          });
          await loadMemorySessions();
        } finally {
          btn.disabled = false;
        }
      });
    });
    ul.querySelectorAll("[data-sess-delete]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!confirm("删除该会话全部轮次？")) return;
        await api(`/api/memory/session/${encodeURIComponent(btn.getAttribute("data-sess-delete"))}`, {
          method: "DELETE",
        });
        await loadMemorySessions();
        refreshContinuityBar();
      });
    });
  } catch (e) {
    ul.innerHTML = `<li class="error">${escHtml(String(e))}</li>`;
  }
}

async function loadMemoryAudit() {
  const ul = document.getElementById("memory-audit-list");
  if (!ul) return;
  ul.innerHTML = "<li class='hint'>加载中…</li>";
  try {
    const data = await api("/api/memory/audit?limit=80");
    const items = data.items || [];
    if (!items.length) {
      ul.innerHTML = "<li class='hint'>暂无审计记录</li>";
      return;
    }
    ul.innerHTML = "";
    for (const a of items) {
      const li = document.createElement("li");
      li.className = "memory-audit-item";
      li.innerHTML =
        `<div>${escHtml(a.at)} · <code>${escHtml(a.action)}</code> · ${escHtml(a.object_type)}/${escHtml(a.object_id)}</div>` +
        (a.detail ? `<div class="hint">${escHtml(a.detail)}</div>` : "");
      ul.appendChild(li);
    }
  } catch (e) {
    ul.innerHTML = `<li class="error">${escHtml(String(e))}</li>`;
  }
}

document.querySelectorAll(".memory-tab[data-memory-tab]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const tab = btn.dataset.memoryTab;
    document.querySelectorAll(".memory-tab").forEach((b) => b.classList.toggle("active", b === btn));
    document.getElementById("memory-pane-rules")?.classList.toggle("hidden", tab !== "rules");
    document.getElementById("memory-pane-sessions")?.classList.toggle("hidden", tab !== "sessions");
    document.getElementById("memory-pane-audit")?.classList.toggle("hidden", tab !== "audit");
    document.getElementById("memory-pane-contrarian")?.classList.toggle("hidden", tab !== "contrarian");
    document.getElementById("memory-pane-fortune")?.classList.toggle("hidden", tab !== "fortune");
    if (tab === "contrarian") loadContrarianAssumptions();
    if (tab === "fortune") loadFortunePane();
  });
});
document.getElementById("btn-memory-refresh")?.addEventListener("click", () => refreshMemoryPanel());

let currentPath = null;

async function api(path, opts = {}) {
  const res = await fetch(`${API}${path}`, opts);
  const ct = res.headers.get("content-type") || "";
  const t = await res.text();
  if (res.status === 402) {
    let lic = { licensed: false, reason: "expired" };
    try {
      const j = JSON.parse(t);
      lic = j.license || { licensed: false, reason: typeof j.detail === "string" ? j.detail : "expired" };
    } catch {
      /* keep default */
    }
    applyLicenseUi(lic);
    throw new Error(LICENSE_REASON_ZH[lic.reason] || "须订阅后继续使用");
  }
  if (!res.ok) {
    let msg = t || res.statusText;
    try {
      const j = JSON.parse(t);
      if (j?.detail) msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* keep raw text */
    }
    throw new Error(msg);
  }
  if (ct.includes("application/json")) return JSON.parse(t || "null");
  return t;
}

window.api = api;

function setStatus(msg) {
  document.getElementById("status").textContent = msg;
}

let uploadJobPollTimer = null;
let lastUploadJobSummary = "";
let linkedIndexJobPollTimer = null;

function renderLinkedIndexBanner(jobs) {
  const el = document.getElementById("linked-index-job-banner");
  if (!el) return;
  const active = (jobs || []).filter((j) => j.status === "queued" || j.status === "running");
  if (!active.length) {
    el.classList.add("hidden");
    el.textContent = "";
    return;
  }
  const job = active[0];
  const total = job.total_files || 0;
  const done = job.done_files || 0;
  const pct = job.progress_pct ?? (total ? Math.round((100 * done) / total) : 0);
  const phaseLabel =
    job.phase === "embed" ? "写入向量" : job.phase === "scan" ? "扫描" : "提取文本";
  el.classList.remove("hidden");
  if (total > 0) {
    el.textContent = job.current
      ? `外联索引 ${done}/${total}（${pct}%）· ${phaseLabel}：${job.current}`
      : `外联索引 ${done}/${total}（${pct}%）· ${phaseLabel}…`;
  } else {
    el.textContent = job.current ? `外联索引 · ${job.current}` : "外联索引 · 正在扫描目录…";
  }
  el.title = (job.paths || []).join("\n");
}

async function refreshLinkedIndexJobs() {
  try {
    const data = await api("/api/linked-dirs/jobs/active");
    const jobs = data.jobs || [];
    renderLinkedIndexBanner(jobs);
    return jobs;
  } catch {
    return [];
  }
}

function trackLinkedIndexJobs() {
  if (linkedIndexJobPollTimer) return;
  const tick = async () => {
    const jobs = await refreshLinkedIndexJobs();
    const active = jobs.filter((j) => j.status === "queued" || j.status === "running");
    if (document.getElementById("panel-manage")?.classList.contains("active")) {
      loadLinkedDirs();
    }
    if (active.length) {
      linkedIndexJobPollTimer = setTimeout(tick, 1200);
      return;
    }
    linkedIndexJobPollTimer = null;
    await refreshStatsLine();
    if (document.getElementById("panel-manage")?.classList.contains("active")) {
      loadLinkedDirs();
      const log = document.getElementById("manage-log");
      if (log?.textContent?.includes("正在后台建立 RAG 索引")) {
        log.textContent = "外联目录索引已完成，可直接在「提问」中引用该目录内容。\n";
      }
    }
  };
  tick();
}

function formatLinkedIndexCell(item) {
  const job = item.index_job;
  if (!job || (job.status !== "queued" && job.status !== "running")) {
    return escHtml(item.last_indexed_at || "—");
  }
  const total = job.total_files || 0;
  const done = job.done_files || 0;
  const pct = job.progress_pct ?? (total ? Math.min(99, Math.round((100 * done) / total)) : 5);
  const label =
    total > 0
      ? `索引中 ${done}/${total}（${pct}%）`
      : job.phase === "scan"
        ? "扫描中…"
        : "索引中…";
  const tip = job.current ? `${label} · ${job.current}` : label;
  return (
    `<div class="linked-index-status" title="${escHtml(tip)}">` +
    `<span class="linked-index-status-text">${escHtml(label)}</span>` +
    `<div class="linked-index-progress"><span style="width:${pct}%"></span></div>` +
    `</div>`
  );
}

let urlJobPollTimer = null;
let urlJobTrackId = null;
let urlJobCallbacks = null;
/** @type {HTMLElement | null} */
let workflowRunBusyCard = null;

function finishUrlJobCallbacks() {
  const cb = urlJobCallbacks;
  urlJobCallbacks = null;
  cb?.onDone?.();
}

function setWorkflowCardBusy(cardEl, busy) {
  if (!cardEl) return;
  const btn = cardEl.querySelector(".workflow-run");
  if (!btn) return;
  cardEl.classList.toggle("is-running", busy);
  btn.classList.toggle("is-busy", busy);
  btn.disabled = busy;
  if (busy) {
    if (!btn.dataset.defaultText) btn.dataset.defaultText = btn.textContent.trim() || "运行";
    btn.textContent = "工作中…";
  } else {
    btn.textContent = btn.dataset.defaultText || "运行";
  }
}

function releaseWorkflowRunBusy() {
  if (workflowRunBusyCard) {
    setWorkflowCardBusy(workflowRunBusyCard, false);
    workflowRunBusyCard = null;
  }
}

const URL_PHASE_LABELS = {
  queued: "排队中",
  cache: "检查缓存",
  fetch: "抓取网页",
  analyze: "分析文档",
  save: "保存笔记",
  index: "写入检索库",
  done: "完成",
};

function urlJobMessage(job) {
  if (!job) return "";
  const phase = URL_PHASE_LABELS[job.phase] || "处理中";
  const pct = job.progress_pct ?? 0;
  if (job.current) return `${phase}（${pct}%）· ${job.current}`;
  return `${phase}（${pct}%）…`;
}

function renderUrlJobUi(job) {
  const banner = document.getElementById("url-job-banner");
  const statusBox = document.getElementById("url-job-status");
  const statusText = document.getElementById("url-job-status-text");
  const progressFill = document.getElementById("url-job-progress-fill");
  const urlRow = document.querySelector(".url-row");
  const btnUrl = document.getElementById("btn-url");
  const active = job && (job.status === "queued" || job.status === "running");

  if (banner) {
    if (active) {
      banner.classList.remove("hidden");
      banner.textContent = `网页抓取 · ${urlJobMessage(job)}`;
      banner.title = job.url || "";
    } else {
      banner.classList.add("hidden");
      banner.textContent = "";
    }
  }

  if (statusBox && statusText && progressFill) {
    statusBox.classList.toggle("hidden", !active);
    statusBox.classList.remove("is-error");
    if (active) {
      statusText.textContent = urlJobMessage(job);
      progressFill.style.width = `${job.progress_pct ?? 5}%`;
    }
  }

  if (urlRow) urlRow.classList.toggle("is-busy", !!active);
  if (btnUrl) {
    btnUrl.disabled = !!active;
    btnUrl.textContent = active ? "抓取中…" : "保存网页";
  }

  const wfLog = document.getElementById("workflow-log");
  if (urlJobCallbacks?.workflowLabel && wfLog && active) {
    wfLog.classList.remove("hidden");
    wfLog.textContent = `${urlJobCallbacks.workflowLabel} · ${urlJobMessage(job)}\n`;
  }
}

async function refreshUrlJob(jobId) {
  if (jobId) {
    try {
      return await api(`/api/url/jobs/${jobId}`);
    } catch {
      return null;
    }
  }
  try {
    const data = await api("/api/url/jobs/active");
    return (data.jobs || [])[0] || null;
  } catch {
    return null;
  }
}

function formatUrlJobLog(job) {
  if (job.status === "failed") {
    return `✗ 抓取失败：${job.error || "未知错误"}\n`;
  }
  if (job.duplicate) {
    return `这篇网页之前已保存过：${job.wiki_page}\n链接：${job.url}\n`;
  }
  return (
    `✓ 已保存：${job.title}\n  笔记位置：${job.wiki_page}\n  原文备份：${job.localized}\n` +
    `  链接：${job.url}\n  抓取方式：${job.method}\n`
  );
}

function onUrlJobFinished(job) {
  renderUrlJobUi(null);
  const log = document.getElementById("manage-log");
  const wfLog = document.getElementById("workflow-log");
  const statusBox = document.getElementById("url-job-status");
  const statusText = document.getElementById("url-job-status-text");
  const progressFill = document.getElementById("url-job-progress-fill");
  const logText = formatUrlJobLog(job);

  if (job.status === "failed") {
    if (statusBox && statusText && progressFill) {
      statusBox.classList.remove("hidden");
      statusBox.classList.add("is-error");
      statusText.textContent = `抓取失败：${job.error || "未知错误"}`;
      progressFill.style.width = "100%";
    }
    if (log) log.textContent = logText;
    if (urlJobCallbacks?.workflowLabel && wfLog) {
      wfLog.classList.remove("hidden");
      wfLog.textContent = logText;
    }
    setStatus("网页抓取失败");
    window.setTimeout(() => statusBox?.classList.add("hidden"), 8000);
    finishUrlJobCallbacks();
    return;
  }

  if (statusBox) statusBox.classList.add("hidden");
  if (log) log.textContent = logText;
  if (urlJobCallbacks?.workflowLabel && wfLog) {
    wfLog.classList.remove("hidden");
    wfLog.textContent = logText;
    setStatus(`${urlJobCallbacks.workflowLabel} 已完成`);
  } else if (job.duplicate) {
    setStatus("网页此前已保存");
  } else {
    setStatus(`已保存网页：${job.title || "完成"}`);
    document.getElementById("url-input").value = "";
  }
  if (urlJobCallbacks?.clearUrlInput && job.status === "done" && !job.duplicate) {
    document.getElementById("url-input").value = "";
  }
  loadAssets();
  refreshStatsLine();
  if (job.quality_warning) {
    window.YizhiToast?.error(job.quality_warning);
  } else if (!job.duplicate) {
    window.YizhiToast?.success(`网页已保存：${job.title || "完成"}`);
  }
  finishUrlJobCallbacks();
}

async function submitUrlIngest(url, force, callbacks) {
  urlJobCallbacks = callbacks || null;
  const log = document.getElementById("manage-log");
  if (log && !callbacks?.workflowLabel) {
    log.textContent = "已提交网页抓取任务，后台处理中…\n";
  }
  const r = await api("/api/url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, force }),
  });
  if (r.already_running) {
    const msg = "已有网页抓取任务在进行中，请稍候…\n";
    if (log && !callbacks?.workflowLabel) log.textContent = msg;
    const wfLog = document.getElementById("workflow-log");
    if (callbacks?.workflowLabel && wfLog) {
      wfLog.classList.remove("hidden");
      wfLog.textContent = msg;
    }
  }
  trackUrlJobs(r.job_id);
  setStatus(callbacks?.workflowLabel ? `正在运行：${callbacks.workflowLabel}…` : "正在后台抓取网页…");
  return r;
}

function trackUrlJobs(jobId) {
  if (jobId) urlJobTrackId = jobId;
  if (urlJobPollTimer) return;
  const tick = async () => {
    const job = await refreshUrlJob(urlJobTrackId);
    if (job && (job.status === "queued" || job.status === "running")) {
      renderUrlJobUi(job);
      urlJobPollTimer = setTimeout(tick, 800);
      return;
    }
    urlJobPollTimer = null;
    urlJobTrackId = null;
    if (job) onUrlJobFinished(job);
    else renderUrlJobUi(null);
  };
  tick();
}

async function refreshUrlJobsActive() {
  try {
    const data = await api("/api/url/jobs/active");
    const jobs = data.jobs || [];
    if (jobs.length) renderUrlJobUi(jobs[0]);
    else if (!urlJobPollTimer) renderUrlJobUi(null);
    return jobs;
  } catch {
    return [];
  }
}

function renderUploadBanner(jobs) {
  const el = document.getElementById("upload-job-banner");
  if (!el) return;
  const active = (jobs || []).filter((j) => j.status === "queued" || j.status === "running");
  if (!active.length) {
    el.classList.add("hidden");
    el.textContent = "";
    return;
  }
  const total = active.reduce((s, j) => s + (j.total || 0), 0);
  const done = active.reduce((s, j) => s + (j.done || 0), 0);
  const indexing = active.some((j) => j.phase === "index" || (j.total > 0 && j.done >= j.total));
  const current = active.map((j) => {
    if (j.phase === "index" || (j.total > 0 && j.done >= j.total)) {
      return j.current || "正在更新检索库…";
    }
    return j.current;
  }).find(Boolean) || "";
  el.classList.remove("hidden");
  el.textContent = indexing
    ? `后台更新检索库（${done}/${total} 个文件已入库）…`
    : current
      ? `后台处理 ${done}/${total}：${current}`
      : `后台处理 ${done}/${total} 个文件…`;
  el.title = active.map((j) => j.items?.map((i) => i.name).join(", ")).filter(Boolean).join("\n");
}

async function refreshUploadJobs() {
  try {
    const data = await api("/api/upload/jobs/active");
    const jobs = data.jobs || [];
    renderUploadBanner(jobs);
    return jobs;
  } catch {
    return [];
  }
}

async function refreshStatsLine() {
  try {
    const s = await api("/api/stats");
    let extra = "";
    if (s.extra_dirs?.length) extra = ` · 外接文件夹 ${s.extra_dirs.length} 个`;
    setStatus(`${s.pages} 条笔记 · ${s.assets} 个文件${extra}`);
  } catch {
    /* ignore */
  }
}

function trackUploadJobs() {
  if (uploadJobPollTimer) return;
  const tick = async () => {
    const jobs = await refreshUploadJobs();
    const active = jobs.filter((j) => j.status === "queued" || j.status === "running");
    if (active.length) {
      uploadJobPollTimer = setTimeout(tick, 1200);
      return;
    }
    uploadJobPollTimer = null;
    await refreshStatsLine();
    if (document.getElementById("panel-manage")?.classList.contains("active")) loadAssets();
    if (document.getElementById("panel-library")?.classList.contains("active")) loadLibrary();
    if (lastUploadJobSummary) {
      const log = document.getElementById("manage-log");
      if (log && document.getElementById("panel-manage")?.classList.contains("active")) {
        log.textContent = lastUploadJobSummary;
      }
      lastUploadJobSummary = "";
    }
  };
  tick();
}

async function startBackgroundUpload(fileList, logEl) {
  const files = [...(fileList || [])];
  if (!files.length) {
    window.YizhiToast?.error("请选择文件");
    return;
  }
  if (window.YizhiJobs?.isBusy("upload")) return;
  window.YizhiJobs?.setBusy("upload", true);
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  if (logEl) logEl.textContent = `正在上传 ${files.length} 个文件…\n`;
  try {
    const res = await fetch(`${API}/api/upload/batch`, { method: "POST", body: fd });
    const text = await res.text();
    let j;
    try {
      j = JSON.parse(text);
    } catch {
      throw new Error(res.ok ? text.slice(0, 120) : `HTTP ${res.status}: ${text.slice(0, 120)}`);
    }
    if (!res.ok) {
      const detail = j.detail;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    lastUploadJobSummary =
      `✓ 已提交后台处理 ${j.total} 个文件（任务 ${j.job_id}）\n` +
      "可切换到其它页面；进度见任务中心。\n";
    if (logEl) logEl.textContent = lastUploadJobSummary;
    window.YizhiToast?.success(`已提交 ${j.total} 个文件后台处理`);
    window.YizhiJobs?.startPolling();
    return j;
  } finally {
    window.YizhiJobs?.setBusy("upload", false);
  }
}

function switchTab(name) {
  if (name !== "history") closeHistoryMenu();
  document.querySelectorAll(".tab").forEach((t) => {
    const on = t.dataset.tab === name;
    t.classList.toggle("active", on);
    t.setAttribute("aria-selected", on ? "true" : "false");
  });
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === `panel-${name}`));
  if (name === "list") {
    loadFolders().then(refreshAllFolderChips).catch(() => {});
    if (notesView === "timeline") refreshMemos();
    else refreshList();
  }
  if (name === "manage") {
    setManageView(manageView);
  }
  if (name === "produce") loadProduceGenres();
  if (name === "library") {
    loadFolders().then(() => loadLibrary()).catch(() => loadLibrary());
  }
  if (name === "history") loadHistory();
  if (name === "memory") refreshMemoryPanel();
  if (name === "deduce") {
    window.setTimeout(() => window.DeduceGraph?.relayout?.(), 120);
  }
}
window.switchTab = switchTab;

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  btn.addEventListener("keydown", (e) => {
    const tabs = [...document.querySelectorAll(".tab")];
    const i = tabs.indexOf(btn);
    if (e.key === "ArrowRight" && i < tabs.length - 1) {
      tabs[i + 1].focus();
      switchTab(tabs[i + 1].dataset.tab);
    } else if (e.key === "ArrowLeft" && i > 0) {
      tabs[i - 1].focus();
      switchTab(tabs[i - 1].dataset.tab);
    }
  });
});

document.getElementById("btn-ask").addEventListener("click", () => {
  askStream();
});

let askAbort = null;
let askStreaming = false;
let lastAskQuestion = "";
let materialScopePaths = [];

function getAskScopePayload() {
  const enabled = document.getElementById("ask-scope-enabled")?.checked;
  if (!enabled || !materialScopePaths.length) return [];
  return [...materialScopePaths];
}

function refreshScopeSummary() {
  const summary = document.getElementById("ask-scope-summary");
  const btn = document.getElementById("btn-ask-scope");
  const n = materialScopePaths.length;
  if (btn) btn.disabled = !document.getElementById("ask-scope-enabled")?.checked;
  if (!summary) return;
  if (n > 0) {
    summary.textContent = `已限定 ${n} 项资料：${materialScopePaths.slice(0, 3).map(pathBasename).join("、")}${n > 3 ? "…" : ""}`;
    summary.classList.remove("hidden");
  } else {
    summary.classList.add("hidden");
    summary.textContent = "";
  }
}

async function openCiteSource(path, page) {
  if (!path) return;
  const filename = pathBasename(path);
  await browseAsset({ rel_path: path, filename }, page || 0);
}

function showAskFeedbackBar(question) {
  lastAskQuestion = (question || "").trim();
  document.getElementById("ask-feedback-bar")?.classList.remove("hidden");
  const hint = document.getElementById("ask-feedback-hint");
  if (hint) hint.textContent = "";
}

function hideAskFeedbackBar() {
  document.getElementById("ask-feedback-bar")?.classList.add("hidden");
}

async function askFallback(payload, inner, out, remember) {
  const r = await api("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  let html = r.answer_html || r.answer || "";
  if (r.archived) {
    html += `<footer class="answer-archived"><p>已保存到知识库：<code>${escHtml(r.archived)}</code></p></footer>`;
  }
  html += relatedQaFooterHtml(r.related_qa);
  html += distillSourcesFooterHtml(r.distill_sources);
  inner.innerHTML = html;
  out.scrollTop = out.scrollHeight;
  if (remember) document.getElementById("ask-input").value = "";
  showAskFeedbackBar(payload.question);
}

async function askStream() {
  const question = document.getElementById("ask-input").value.trim();
  if (!question) return;
  const out = document.getElementById("ask-output");
  const btn = document.getElementById("btn-ask");

  if (askAbort) askAbort.abort();
  askAbort = new AbortController();
  btn.disabled = true;
  askStreaming = true;
  document.getElementById("ask-empty-hint")?.classList.add("hidden");

  const remember = document.getElementById("ask-remember").checked;
  let inner = out;
  let html = "";

  try {
    if (remember) {
      await renderAskThread();
      out.appendChild(renderTurnPlain({ role: "user", content: question }));
      const assistantWrap = document.createElement("div");
      assistantWrap.className = "history-turn history-assistant current-stream";
      assistantWrap.innerHTML =
        '<div class="hist-a"><strong>答：</strong><div class="hist-body answer-html-inner"></div></div>';
      out.appendChild(assistantWrap);
      inner = assistantWrap.querySelector(".answer-html-inner");
      inner.innerHTML = '<p class="hint">正在检索并生成…</p>';
    } else {
      out.innerHTML = '<p class="hint">正在检索并生成…</p>';
      inner = out;
    }

    const render = (streaming) => {
      inner.innerHTML = html + (streaming ? '<span class="stream-cursor" aria-hidden="true">▋</span>' : "");
      out.scrollTop = out.scrollHeight;
    };

    const autoArchive = document.getElementById("ask-archive").checked;
    const payload = {
      question,
      session_id: remember ? getSessionId() : "",
      remember,
      auto_archive: autoArchive,
      scope_paths: getAskScopePayload(),
      folder_ids: getAskFolderIds(),
    };

    const res = await fetch(`${API}/api/ask/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: askAbort.signal,
    });

    if (res.status === 404) {
      await askFallback(payload, inner, out, remember);
      return;
    }
    if (!res.ok) throw new Error(await res.text());

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";
      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data:")) continue;
        const ev = JSON.parse(line.slice(5).trim());
        if (ev.type === "status") {
          if (!html) {
            inner.innerHTML = `<p class="hint">${escHtml(ev.text || "正在处理…")}</p>`;
            out.scrollTop = out.scrollHeight;
          }
        } else if (ev.type === "html") {
          html = ev.text;
          render(true);
        } else if (ev.type === "token") {
          if (!html) html = "";
          html += ev.text;
          render(true);
        } else if (ev.type === "done") {
          html += ev.footer || "";
          if (ev.archived) {
            html += `<footer class="answer-archived"><p>已保存到知识库：<code>${ev.archived}</code></p></footer>`;
          }
          html += relatedQaFooterHtml(ev.related_qa);
          html += distillSourcesFooterHtml(ev.distill_sources);
          render(false);
          refreshContinuityBar();
        }
      }
    }
    render(false);
    if (remember) {
      document.getElementById("ask-input").value = "";
    }
    showAskFeedbackBar(question);
  } catch (e) {
    if (e.name !== "AbortError") {
      if (remember && inner !== out) {
        inner.innerHTML = `<p class="error">${escHtml(String(e))}</p>`;
      } else {
        out.innerHTML = `<p class="error">${escHtml(String(e))}</p>`;
      }
    }
  } finally {
    askStreaming = false;
    btn.disabled = false;
    askAbort = null;
  }
}

document.getElementById("btn-query").addEventListener("click", () => {
  queryState.page = 1;
  runQuery();
});

async function runQuery() {
  const q = document.getElementById("query-input").value.trim();
  const rag = document.getElementById("query-rag").checked;
  const box = document.getElementById("query-results");
  if (!q) {
    box.innerHTML = '<p class="empty-row">请输入要搜索的关键词</p>';
    return;
  }
  box.innerHTML = "正在查找…";
  try {
    const r = await api(
      `/api/query?q=${encodeURIComponent(q)}&rag=${rag}&page=${queryState.page}&size=${DEFAULT_PAGE_SIZE}`
    );
    box.innerHTML = "";
    for (const item of r.items || []) {
      const div = document.createElement("div");
      div.className = "item";
      if (r.mode === "rag") {
        let src = `${item.path} · 相关度 ${item.score?.toFixed(2) || "-"}`;
        if (item.asset_path) src += ` · 原文件 ${item.asset_path}`;
        div.innerHTML = `<strong>${escHtml(item.title || item.path)}</strong>
          <div class="path">${escHtml(src)}</div>
          <div>${escHtml((item.text || "").slice(0, 240))}…</div>`;
      } else {
        div.innerHTML = `<strong>${escHtml(item.title)}</strong>
          <div class="path">${escHtml(item.rel_path)} · ${typeZh(item.type)} · ${statusZh(item.status)}</div>`;
      }
      box.appendChild(div);
    }
    if (!r.items?.length) box.textContent = "没有找到相关内容";
    renderPager("query-pager", r, (p) => {
      queryState.page = p;
      runQuery();
    });
  } catch (e) {
    box.textContent = String(e);
    renderPager("query-pager", null, () => {});
  }
}

async function refreshList() {
  const type = document.getElementById("filter-type").value;
  const typeQ = type ? `&type=${encodeURIComponent(type)}` : "";
  const r = await api(`/api/pages?page=${listState.page}&size=30${typeQ}`);
  if (r.page && r.page !== listState.page) listState.page = r.page;
  const ul = document.getElementById("page-list");
  ul.innerHTML = "";
  for (const p of r.items || []) {
    const li = document.createElement("li");
    li.dataset.path = p.rel_path;
    li.innerHTML = `${escHtml(p.title)}<small>${typeZh(p.type)} · ${statusZh(p.status)}</small>`;
    li.addEventListener("click", () => selectPage(p.rel_path, li));
    ul.appendChild(li);
  }
  if (!r.items?.length) ul.innerHTML = '<li class="empty-item">暂无笔记</li>';
  renderPager("page-list-pager", r, (p) => {
    listState.page = p;
    refreshList();
  });
}

function removePageListItem(relPath) {
  const ul = document.getElementById("page-list");
  if (!ul || !relPath) return;
  const sel = `#page-list li[data-path="${CSS.escape(relPath)}"]`;
  ul.querySelector(sel)?.remove();
  if (!ul.querySelector("li:not(.empty-item)")) {
    ul.innerHTML = '<li class="empty-item">暂无笔记</li>';
  }
}

function formatMemoBody(text) {
  if (window.YizhiRichEditor?.renderMarkdown) {
    return window.YizhiRichEditor.renderMarkdown(text);
  }
  const escaped = escHtml(text || "");
  return escaped.replace(/#([\w\u4e00-\u9fff-]+)/g, '<span class="memo-hashtag">#$1</span>');
}

function memoBodyNeedsExpand(bodyEl) {
  if (!bodyEl) return false;
  if (bodyEl.querySelector("img, pre, blockquote, table, iframe, video")) return true;
  const wrap = bodyEl.closest(".memo-card-body-wrap");
  if (!wrap) return bodyEl.scrollHeight > bodyEl.clientHeight + 1;
  wrap.classList.add("is-collapsed");
  const needs = bodyEl.scrollHeight > bodyEl.clientHeight + 1;
  return needs;
}

function setupMemoBodyCollapse(item) {
  const wrap = item?.querySelector(".memo-card-body-wrap");
  if (!wrap) return;
  const body = wrap.querySelector(".memo-card-body");
  const btn = wrap.querySelector(".memo-expand-btn");
  if (!body || !btn) return;

  wrap.classList.add("is-collapsed");
  btn.textContent = "更多";
  btn.setAttribute("aria-expanded", "false");
  btn.classList.add("hidden");

  window.requestAnimationFrame(() => {
    if (memoBodyNeedsExpand(body)) {
      btn.classList.remove("hidden");
    } else {
      wrap.classList.remove("is-collapsed");
    }
  });
}

function bindMemoExpandBtn(item) {
  const btn = item.querySelector(".memo-expand-btn");
  if (!btn || btn.dataset.bound === "1") return;
  btn.dataset.bound = "1";
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    const wrap = btn.closest(".memo-card-body-wrap");
    if (!wrap) return;
    const collapsed = !wrap.classList.contains("is-collapsed");
    wrap.classList.toggle("is-collapsed", collapsed);
    btn.textContent = collapsed ? "更多" : "收起";
    btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
  });
}

function setNotesView(view) {
  notesView = view;
  document.querySelectorAll(".notes-view-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.notesView === view);
  });
  document.getElementById("notes-timeline-view")?.classList.toggle("hidden", view !== "timeline");
  document.getElementById("notes-editor-view")?.classList.toggle("hidden", view !== "editor");
  if (view === "timeline") refreshMemos();
  else {
    ensureNoteEditor();
    refreshList();
    window.setTimeout(() => window.YizhiRichEditor?.fitToParent?.(noteEditorRec), 80);
  }
}

function renderMemoTagFilter(tags) {
  const box = document.getElementById("memo-tag-filter");
  if (!box) return;
  box.innerHTML = "";
  const allBtn = document.createElement("button");
  allBtn.type = "button";
  allBtn.className = "memo-tag-chip" + (memoState.tag ? "" : " active");
  allBtn.textContent = "全部";
  allBtn.addEventListener("click", () => {
    memoState.tag = "";
    memoState.page = 1;
    refreshMemos();
  });
  box.appendChild(allBtn);
  for (const tag of tags || []) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "memo-tag-chip" + (memoState.tag === tag ? " active" : "");
    btn.textContent = `#${tag}`;
    btn.addEventListener("click", () => {
      memoState.tag = tag;
      memoState.page = 1;
      refreshMemos();
    });
    box.appendChild(btn);
  }
}

function nowMemoTimeStr() {
  return new Date().toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Shanghai",
  });
}

function ensureMemoTimelineList() {
  const box = document.getElementById("memo-timeline");
  if (!box) return null;
  box.querySelector(".memo-timeline-empty")?.remove();
  let list = box.querySelector(".memo-timeline-items");
  if (!list) {
    const rail = document.createElement("div");
    rail.className = "memo-timeline-rail";
    rail.innerHTML =
      `<div class="memo-timeline-axis" aria-hidden="true">` +
      `<div class="memo-timeline-arrow"></div>` +
      `<div class="memo-timeline-line"></div></div>` +
      `<div class="memo-timeline-items"></div>`;
    box.appendChild(rail);
    list = rail.querySelector(".memo-timeline-items");
  }
  return list;
}

function bumpMemoSummary(delta) {
  const summary = document.getElementById("memo-date-summary");
  if (!summary) return;
  const m = summary.textContent.match(/(\d+)\s*条闪记/);
  const n = Math.max(0, (m ? parseInt(m[1], 10) : 0) + delta);
  const label = formatMemoDateLabel(memoState.date || beijingTodayStr());
  summary.textContent = `${label} · ${n} 条闪记 · 时间向上`;
}

function prependMemoToTimeline(m) {
  const list = ensureMemoTimelineList();
  if (!list) return;
  const item = buildMemoTimelineItem(m);
  if (m._optimistic) item.classList.add("is-pending");
  list.insertBefore(item, list.firstChild);
}

function removeMemoTimelineItem(relPath) {
  document.querySelector(`.memo-timeline-item[data-path="${CSS.escape(relPath)}"]`)?.remove();
  const box = document.getElementById("memo-timeline");
  if (box && !box.querySelector(".memo-timeline-item")) {
    box.innerHTML =
      `<div class="memo-timeline-empty">` +
      `<p class="hint">${escHtml(formatMemoDateLabel(memoState.date))}还没有闪记</p>` +
      `<p class="hint">在上方写点什么，Ctrl+Enter 保存</p></div>`;
  }
}

let memoSaving = false;

async function refreshMemos() {
  if (!memoState.date) memoState.date = beijingTodayStr();
  const picker = document.getElementById("memo-date-picker");
  if (picker && picker.value !== memoState.date) picker.value = memoState.date;
  const tagQ = memoState.tag ? `&tag=${encodeURIComponent(memoState.tag)}` : "";
  const dateQ = `&date=${encodeURIComponent(memoState.date)}`;
  try {
    const r = await api(`/api/memos?page=${memoState.page}&size=50${tagQ}${dateQ}`);
    renderMemoTagFilter(r.tags || []);
    const summary = document.getElementById("memo-date-summary");
    if (summary) {
      const label = formatMemoDateLabel(r.date || memoState.date);
      const n = r.total_for_day ?? (r.items || []).length;
      summary.textContent = `${label} · ${n} 条闪记 · 时间向上`;
    }
    const box = document.getElementById("memo-timeline");
    box.innerHTML = "";
    const items = r.items || [];
    if (!items.length) {
      box.innerHTML =
        `<div class="memo-timeline-empty">` +
        `<p class="hint">${escHtml(formatMemoDateLabel(r.date || memoState.date))}还没有闪记</p>` +
        `<p class="hint">在上方写点什么，Ctrl+Enter 保存</p></div>`;
    } else {
      const rail = document.createElement("div");
      rail.className = "memo-timeline-rail";
      rail.innerHTML =
        `<div class="memo-timeline-axis" aria-hidden="true">` +
        `<div class="memo-timeline-arrow"></div>` +
        `<div class="memo-timeline-line"></div></div>` +
        `<div class="memo-timeline-items"></div>`;
      const list = rail.querySelector(".memo-timeline-items");
      for (const m of items) {
        list.appendChild(buildMemoTimelineItem(m));
      }
      box.appendChild(rail);
    }
    renderPager("memo-pager", r, (p) => {
      memoState.page = p;
      refreshMemos();
    });
  } catch (e) {
    const box = document.getElementById("memo-timeline");
    if (box) box.innerHTML = `<p class="error">${escHtml(String(e))}</p>`;
  }
}

function buildMemoTimelineItem(m) {
  const item = document.createElement("article");
  item.className = "memo-timeline-item" + (m.pinned ? " is-pinned" : "");
  item.dataset.path = m.rel_path;
  const pending = !!m._optimistic;
  const time = m.time || (m.updated || m.created || "").slice(11, 16) || nowMemoTimeStr();
  const statusBadge = pending
    ? `<span class="memo-status-badge">保存中…</span>`
    : m.pinned
      ? `<span class="memo-status-badge is-pinned">📌</span>`
      : "";
  const actionBtns = pending
    ? ""
    : `<button type="button" class="memo-act" data-act="pin" title="置顶">${m.pinned ? "取消置顶" : "置顶"}</button>` +
      `<button type="button" class="memo-act" data-act="edit" title="编辑">编辑</button>` +
      `<button type="button" class="memo-act" data-act="open" title="在编辑器中打开">整理</button>` +
      `<button type="button" class="memo-act danger" data-act="del" title="删除">删除</button>`;
  const headHtml =
    statusBadge || actionBtns
      ? `<header class="memo-card-head memo-card-head-compact">${statusBadge}` +
        `<div class="memo-card-actions">${actionBtns}</div></header>`
      : "";
  item.innerHTML =
    `<div class="memo-timeline-node">` +
    `<span class="memo-timeline-dot"></span>` +
    `<time class="memo-timeline-time">${escHtml(time)}</time></div>` +
    `<div class="memo-card">` +
    headHtml +
    `<div class="memo-card-body-wrap is-collapsed">` +
    `<div class="memo-card-body">${formatMemoBody(m.body)}</div>` +
    `<button type="button" class="memo-expand-btn hidden" aria-expanded="false">更多</button>` +
    `</div>` +
    (m.tags?.length ? `<footer class="memo-card-tags">${m.tags.map((t) => `<span class="memo-tag">#${escHtml(t)}</span>`).join("")}</footer>` : "") +
    `</div>`;
  bindMemoExpandBtn(item);
  setupMemoBodyCollapse(item);
  if (!pending) {
    item.querySelector('[data-act="pin"]')?.addEventListener("click", async (e) => {
      e.stopPropagation();
      await api(`/api/memos?path=${encodeURIComponent(m.rel_path)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pinned: !m.pinned }),
      });
      refreshMemos();
    });
    item.querySelector('[data-act="edit"]')?.addEventListener("click", (e) => {
      e.stopPropagation();
      openMemoInlineEdit(m, item);
    });
    item.querySelector('[data-act="open"]')?.addEventListener("click", (e) => {
      e.stopPropagation();
      openMemoInEditor(m.rel_path);
    });
    item.querySelector('[data-act="del"]')?.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!(await uiConfirm("删除这条闪记？"))) return;
      await api(`/api/pages?path=${encodeURIComponent(m.rel_path)}`, { method: "DELETE" });
      refreshMemos();
    });
  }
  return item;
}

function openMemoInlineEdit(m, itemEl) {
  const item = itemEl || document.querySelector(`.memo-timeline-item[data-path="${CSS.escape(m.rel_path)}"]`);
  if (!item) return;
  const card = item.querySelector(".memo-card");
  const bodyEl = card?.querySelector(".memo-card-body");
  const bodyWrap = card?.querySelector(".memo-card-body-wrap");
  if (!bodyEl || card.querySelector(".memo-inline-edit-host")) return;
  bodyWrap?.classList.add("hidden");
  const host = document.createElement("div");
  host.className = "memo-inline-edit-host yizhi-rich-editor-host";
  const actions = document.createElement("div");
  actions.className = "memo-inline-actions row";
  const btnSave = document.createElement("button");
  btnSave.type = "button";
  btnSave.className = "primary";
  btnSave.textContent = "保存";
  const btnCancel = document.createElement("button");
  btnCancel.type = "button";
  btnCancel.textContent = "取消";
  actions.append(btnCancel, btnSave);
  card.append(host, actions);

  const inlineRec = window.YizhiRichEditor?.create(host, {
    apiBase: API,
    compact: true,
    initialValue: m.body || "",
    minHeight: "120px",
  });

  const cleanup = () => {
    window.YizhiRichEditor?.destroy(inlineRec);
    host.remove();
    actions.remove();
    bodyWrap?.classList.remove("hidden");
  };

  btnCancel.addEventListener("click", () => refreshMemos());
  btnSave.addEventListener("click", async () => {
    const newBody = window.YizhiRichEditor?.getMarkdown(inlineRec) || "";
    if (!newBody) return uiInfo("内容不能为空");
    bodyEl.innerHTML = formatMemoBody(newBody);
    bodyWrap?.classList.remove("hidden");
    cleanup();
    setupMemoBodyCollapse(item);
    bindMemoExpandBtn(item);
    setStatus("闪记已更新");
    try {
      await api(`/api/memos?path=${encodeURIComponent(m.rel_path)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: newBody }),
      });
    } catch (err) {
      uiError(err);
      refreshMemos();
    }
  });
}

async function openMemoInEditor(relPath) {
  switchTab("list");
  setNotesView("editor");
  listState.page = 1;
  await refreshList();
  const li = document.querySelector(`#page-list li[data-path="${CSS.escape(relPath)}"]`);
  if (li) {
    await selectPage(relPath, li);
    return;
  }
  currentPath = relPath;
  const p = await api(`/api/pages/content?path=${encodeURIComponent(relPath)}`);
  document.getElementById("edit-type").value = p.type;
  document.getElementById("edit-status").value = p.status;
  document.getElementById("edit-title").value = p.title;
  setNoteBodyMarkdown(p.body);
  syncNoteFolderIds(p.folder_ids);
  document.querySelectorAll("#page-list li").forEach((el) => el.classList.remove("active"));
  window.setTimeout(() => window.YizhiRichEditor?.fitToParent?.(noteEditorRec), 80);
}

async function saveQuickMemo() {
  if (!memoEditorRec) {
    initRichEditors();
  }
  const content = getMemoInputMarkdown();
  if (memoSaving) return;
  if (!content) {
    uiInfo("请先输入闪念内容");
    window.YizhiRichEditor?.focus?.(memoEditorRec);
    return;
  }
  memoSaving = true;
  const btn = document.getElementById("btn-memo-save");
  const optimisticId = `pending-${Date.now()}`;
  memoState.date = beijingTodayStr();
  memoState.page = 1;
  const picker = document.getElementById("memo-date-picker");
  if (picker) picker.value = memoState.date;

  const optimistic = {
    rel_path: optimisticId,
    title: content.split("\n")[0].replace(/^#+\s*/, "").slice(0, 80) || "闪记",
    body: content,
    time: nowMemoTimeStr(),
    pinned: false,
    tags: [],
    _optimistic: true,
  };

  clearMemoInput();
  prependMemoToTimeline(optimistic);
  bumpMemoSummary(1);
  setStatus("闪记已保存");
  if (btn) btn.disabled = true;

  try {
    const m = await api("/api/memos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content, folder_ids: [...memoFolderIds] }),
    });
    removeMemoTimelineItem(optimisticId);
    prependMemoToTimeline(m);
    if (m.indexing) setStatus("闪记已保存，检索库后台更新中");
  } catch (e) {
    removeMemoTimelineItem(optimisticId);
    bumpMemoSummary(-1);
    window.YizhiRichEditor?.setMarkdown(memoEditorRec, content);
    uiError(e);
  } finally {
    memoSaving = false;
    if (btn) btn.disabled = false;
  }
}

document.querySelectorAll(".notes-view-btn").forEach((btn) => {
  btn.addEventListener("click", () => setNotesView(btn.dataset.notesView));
});
document.getElementById("btn-memo-save")?.addEventListener("click", saveQuickMemo);
document.getElementById("btn-memo-today")?.addEventListener("click", () => {
  memoState.date = beijingTodayStr();
  memoState.page = 1;
  const picker = document.getElementById("memo-date-picker");
  if (picker) picker.value = memoState.date;
  refreshMemos();
});

async function selectPage(path, li) {
  document.querySelectorAll("#page-list li").forEach((el) => el.classList.remove("active"));
  li?.classList.add("active");
  currentPath = path;
  try {
    ensureNoteEditor();
    const p = await api(`/api/pages/content?path=${encodeURIComponent(path)}`);
    const typeEl = document.getElementById("edit-type");
    if (typeEl && p.type && ![...typeEl.options].some((o) => o.value === p.type)) {
      const opt = document.createElement("option");
      opt.value = p.type;
      opt.textContent = typeZh(p.type) || p.type;
      typeEl.appendChild(opt);
    }
    if (typeEl) typeEl.value = p.type || "note";
    document.getElementById("edit-status").value = p.status || "draft";
    document.getElementById("edit-title").value = p.title || "";
    setNoteBodyMarkdown(p.body || "");
    syncNoteFolderIds(p.folder_ids);
    const al = document.getElementById("asset-link");
    if (p.asset_path) {
      al.innerHTML = `附件: <a href="#" data-asset="${escHtml(p.asset_path)}">${escHtml(p.asset_path)}</a> (${escHtml(p.asset_mime || "")})`;
      al.querySelector("a")?.addEventListener("click", (e) => {
        e.preventDefault();
        window.open(`${API}/api/assets/file?path=${encodeURIComponent(p.asset_path)}`);
      });
    } else {
      al.textContent = "";
    }
  } catch (e) {
    uiError(e);
  }
}

document.getElementById("btn-refresh-list").addEventListener("click", () => {
  if (notesView === "timeline") {
    memoState.page = 1;
    refreshMemos();
  } else {
    listState.page = 1;
    refreshList();
  }
});
document.getElementById("filter-type").addEventListener("change", () => {
  listState.page = 1;
  refreshList();
});

document.getElementById("btn-new-page").addEventListener("click", () => {
  currentPath = null;
  document.getElementById("edit-type").value = "note";
  document.getElementById("edit-status").value = "draft";
  document.getElementById("edit-title").value = "新笔记";
  setNoteBodyMarkdown("# 新笔记\n\n");
  document.getElementById("asset-link").textContent = "";
  syncNoteFolderIds([]);
});

document.getElementById("btn-save-page").addEventListener("click", async () => {
  const btn = document.getElementById("btn-save-page");
  if (btn?.disabled) return;
  const title = document.getElementById("edit-title").value.trim();
  if (!title) {
    uiInfo("请填写标题");
    return;
  }
  const body = {
    type: document.getElementById("edit-type").value,
    title,
    body: getNoteBodyMarkdown(),
    status: document.getElementById("edit-status").value,
    folder_ids: [...noteFolderIds],
  };
  const prevLabel = btn?.textContent || "保存";
  if (btn) {
    btn.disabled = true;
    btn.textContent = "保存中…";
  }
  setStatus("正在保存…");
  try {
    if (currentPath) {
      await api(`/api/pages?path=${encodeURIComponent(currentPath)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    } else {
      const p = await api("/api/pages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      currentPath = p.rel_path;
    }
    setStatus("已保存");
    window.YizhiToast?.success?.("笔记已保存");
    if (notesView === "timeline") refreshMemos();
    else refreshList();
  } catch (e) {
    uiError(e);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = prevLabel;
    }
  }
});

document.getElementById("btn-del-page").addEventListener("click", async () => {
  if (!currentPath) {
    uiInfo("请先在左侧列表选中要删除的笔记");
    return;
  }
  if (!(await uiConfirm(`确定删除「${currentPath}」？\n\n此操作不可恢复。`, { title: "删除笔记" }))) return;
  const deletedPath = currentPath;
  try {
    await api(`/api/pages?path=${encodeURIComponent(deletedPath)}`, { method: "DELETE" });
    currentPath = null;
    document.getElementById("edit-title").value = "";
    setNoteBodyMarkdown("");
    document.getElementById("asset-link").textContent = "";
    syncNoteFolderIds([]);
    removePageListItem(deletedPath);
    if (notesView === "timeline") await refreshMemos();
    else await refreshList();
    refreshStatsLine();
    setStatus("已删除");
  } catch (e) {
    uiError(e);
    try {
      if (notesView === "timeline") await refreshMemos();
      else await refreshList();
    } catch {
      /* ignore secondary refresh error */
    }
  }
});

let lastProduce = null;
let producePhase = "idle"; // idle | streaming | draft | finalized
let produceEditorRec = null;
const PODCAST_BTN_LABEL = "合成播客音频";
const PRODUCE_CONFIRM_STORAGE = "myk-produce-confirmed";

function getProduceMarkdown() {
  if (produceEditorRec && window.YizhiRichEditor?.getMarkdown) {
    const md = window.YizhiRichEditor.getMarkdown(produceEditorRec);
    if (md) return md;
  }
  return lastProduce?.content || "";
}

function syncProduceFromEditor() {
  const md = getProduceMarkdown();
  if (lastProduce) lastProduce.content = md;
  return md;
}

function destroyProduceEditor() {
  const host = document.getElementById("produce-editor-host");
  if (produceEditorRec && window.YizhiRichEditor?.destroy) {
    try {
      window.YizhiRichEditor.destroy(produceEditorRec);
    } catch {
      /* ignore */
    }
  }
  produceEditorRec = null;
  if (host) {
    host.classList.add("hidden");
    host.innerHTML = "";
  }
}

function mountProduceEditor(md) {
  const host = document.getElementById("produce-editor-host");
  if (!host) return;
  destroyProduceEditor();
  host.classList.remove("hidden");
  if (window.YizhiRichEditor?.create) {
    produceEditorRec = window.YizhiRichEditor.create(host, {
      apiBase: typeof API !== "undefined" ? API : "",
      initialValue: md || "",
      height: "auto",
      minHeight: "280px",
      growWithContent: true,
      placeholder: "直接编辑正文；也可在下方填写改稿要求…",
    });
  } else {
    const ta = document.createElement("textarea");
    ta.className = "produce-editor-fallback";
    ta.value = md || "";
    ta.style.cssText = "width:100%;min-height:280px;box-sizing:border-box;padding:10px;resize:vertical;";
    host.appendChild(ta);
    produceEditorRec = {
      el: host,
      editor: {
        getMarkdown: () => ta.value,
        setMarkdown: (v) => {
          ta.value = v || "";
        },
        destroy: () => ta.remove(),
      },
    };
  }
}

function setProduceReviseBarVisible(on) {
  document.getElementById("produce-revise-bar")?.classList.toggle("hidden", !on);
}

function updateProduceFinalizeUI() {
  const btn = document.getElementById("btn-produce-finalize");
  const meta = document.getElementById("produce-finalize-meta");
  if (!btn) return;
  if (producePhase === "finalized") {
    btn.textContent = "继续修改";
    if (meta) {
      meta.classList.remove("hidden");
      meta.textContent = lastProduce?.wiki_page
        ? `已定稿入库：${lastProduce.wiki_page}（草稿）。可继续修改后再定稿覆盖同一页。`
        : "已定稿。";
    }
  } else {
    btn.textContent = "确认定稿";
    if (meta) {
      if (lastProduce?.wiki_page) {
        meta.classList.remove("hidden");
        meta.textContent = `上次定稿：${lastProduce.wiki_page}（再定稿将覆盖）`;
      } else {
        meta.classList.add("hidden");
        meta.textContent = "";
      }
    }
  }
}

function setProduceActionBusy(busy) {
  for (const id of ["btn-produce", "btn-produce-revise", "btn-produce-finalize"]) {
    const el = document.getElementById(id);
    if (el) el.disabled = !!busy;
  }
}

function hashProduceDoc(r) {
  const s = `${r?.topic || ""}|${r?.title || ""}|${(r?.content || "").length}`;
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return `p${h >>> 0}`;
}

function loadProduceConfirmState(docKey) {
  try {
    const all = JSON.parse(sessionStorage.getItem(PRODUCE_CONFIRM_STORAGE) || "{}");
    return all[docKey] || {};
  } catch {
    return {};
  }
}

function saveProduceConfirmState(docKey, state) {
  try {
    const all = JSON.parse(sessionStorage.getItem(PRODUCE_CONFIRM_STORAGE) || "{}");
    all[docKey] = state;
    sessionStorage.setItem(PRODUCE_CONFIRM_STORAGE, JSON.stringify(all));
  } catch {
    /* ignore */
  }
}

function parsePendingConfirmItems(md) {
  const text = String(md || "");
  if (!text.includes("待人工确认")) return [];
  const lines = text.split(/\r?\n/);
  let inSection = false;
  const items = [];
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (/^#{1,4}\s*.*待人工确认/.test(line.trim())) {
      inSection = true;
      continue;
    }
    if (inSection && /^#{1,4}\s+\S/.test(line.trim())) break;
    if (!inSection) continue;
    const trimmed = line.trim();
    if (!trimmed) continue;
    if (/^\|/.test(trimmed) && /\|$/.test(trimmed)) {
      const cells = trimmed
        .replace(/^\|/, "")
        .replace(/\|$/, "")
        .split("|")
        .map((c) => c.trim());
      if (!cells.length) continue;
      if (cells.every((c) => /^:?-+:?$/.test(c) || c === "---")) continue;
      if (/^(确认项|说明|项目|备注)$/.test(cells[0])) continue;
      items.push({
        id: `r${items.length}`,
        label: cells[0] || `第 ${items.length + 1} 项`,
        detail: cells.slice(1).filter(Boolean).join(" · "),
      });
      continue;
    }
    const lm = trimmed.match(/^[-*+]\s+(.+)$/) || trimmed.match(/^\d+\.\s+(.+)$/);
    if (lm) {
      items.push({ id: `l${items.length}`, label: lm[1].trim(), detail: "" });
    }
  }
  return items;
}

function updateProduceConfirmToolbar(panel) {
  const bar = panel?.querySelector(".produce-confirm-bar");
  if (!bar) return;
  const checks = panel.querySelectorAll(".produce-confirm-check");
  const total = checks.length;
  const done = [...checks].filter((c) => c.checked).length;
  const status = bar.querySelector(".produce-confirm-status");
  if (status) {
    status.textContent =
      total === 0
        ? "暂无待确认项"
        : done >= total
          ? `已全部确认（${total} 项）`
          : `待确认 ${total - done} 项 · 已确认 ${done} 项`;
  }
  const summary = panel.querySelector("details > summary");
  if (summary) summary.textContent = `待人工确认（${done}/${total}）`;
  bar.classList.toggle("is-all-done", total > 0 && done >= total);
}

/** 正文在富文本编辑器内：确认操作放在独立面板，避免写进 editor DOM 后找不到 */
function renderProduceConfirmPanel(r) {
  const panel = document.getElementById("produce-confirm-panel");
  if (!panel) return;
  const md = r?.content || lastProduce?.content || "";
  const items = parsePendingConfirmItems(md);
  if (!items.length) {
    panel.classList.add("hidden");
    panel.innerHTML = "";
    return;
  }
  const docKey = hashProduceDoc(r || lastProduce || { content: md });
  const state = loadProduceConfirmState(docKey);
  const doneCount = items.filter((it) => state[it.id]).length;
  const openAttr = doneCount >= items.length ? "" : " open";
  let html =
    `<details${openAttr}>` +
    `<summary>待人工确认（${doneCount}/${items.length}）</summary>` +
    `<div class="produce-confirm-bar" data-doc-key="${escHtml(docKey)}">` +
    `<span class="produce-confirm-status"></span>` +
    `<button type="button" class="produce-confirm-all">全部标记已确认</button>` +
    `</div><ul class="produce-confirm-list">`;
  for (const it of items) {
    const checked = !!state[it.id];
    html +=
      `<li class="produce-confirm-item${checked ? " produce-confirm-done" : ""}">` +
      `<label class="produce-confirm-label">` +
      `<input type="checkbox" class="produce-confirm-check" data-confirm-id="${escHtml(it.id)}"${checked ? " checked" : ""} />` +
      `<span>已确认</span></label>` +
      `<div class="produce-confirm-item-title">${escHtml(it.label)}</div>` +
      (it.detail
        ? `<div class="produce-confirm-item-detail">${escHtml(it.detail)}</div>`
        : "") +
      `</li>`;
  }
  html += "</ul></details>";
  panel.innerHTML = html;
  panel.classList.remove("hidden");
  updateProduceConfirmToolbar(panel);
}

function renderPodcastDock(r) {
  const dock = document.getElementById("produce-podcast-dock");
  if (!dock) return;
  if (!r || (!r.merged_file && !(r.manifest || []).length && !r.merged_error)) {
    dock.classList.add("hidden");
    dock.innerHTML = "";
    return;
  }
  let html = `<h3>播客音频</h3>`;
  if (r.merged_file) {
    const mergedUrl = `${API}/api/podcast/audio?path=${encodeURIComponent(r.merged_file)}`;
    const mergedName = podcastDownloadFilename(r.title || lastProduce?.title || "播客", r.merged_format || "mp3");
    html += `<div class="podcast-merged-block">`;
    html += `<p class="hint">完整音频（由 ${r.segments || (r.manifest || []).length || 0} 段合并）</p>`;
    html += `<audio controls preload="metadata" class="podcast-merged-audio" src="${mergedUrl}"></audio>`;
    html += `<div class="podcast-dock-actions">`;
    html += `<button type="button" class="primary btn-podcast-download-full" data-path="${escHtml(r.merged_file)}" data-filename="${escHtml(mergedName)}">下载完整音频</button>`;
    html += `</div></div>`;
  } else if (r.merged_error) {
    html += `<p class="error">完整音频合并未成功：${escHtml(r.merged_error)}</p>`;
  }
  const segs = r.manifest || [];
  if (segs.length) {
    html += `<details class="podcast-segments-details"><summary>分段列表（${segs.length} 段）</summary><ol class="podcast-playlist">`;
    for (const item of segs) {
      const url = `${API}/api/podcast/audio?path=${encodeURIComponent(item.file)}`;
      html += `<li><strong>${escHtml(item.speaker || "")}</strong> `;
      html += `<audio controls preload="none" src="${url}"></audio> `;
      html += `<span class="hint">${escHtml((item.text || "").slice(0, 80))}</span></li>`;
    }
    html += `</ol></details>`;
  }
  if (r.directory) {
    html += `<p class="hint">保存在 ${escHtml(r.directory)}</p>`;
  }
  dock.innerHTML = html;
  dock.classList.remove("hidden");
  dock.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function setProducePodcastHint(text, kind = "") {
  const el = document.getElementById("produce-podcast-hint");
  if (!el) return;
  el.textContent = text || "";
  el.classList.toggle("hidden", !text);
  el.classList.toggle("is-busy", kind === "busy");
  el.classList.toggle("is-error", kind === "error");
}

async function loadProduceGenres() {
  const sel = document.getElementById("produce-genre");
  if (!sel || sel.options.length) return;
  try {
    const data = await api("/api/produce/genres");
    for (const g of data.genres || []) {
      const opt = document.createElement("option");
      opt.value = g.id;
      opt.textContent = `${g.label}（${g.description || ""}）`;
      opt.title = `建议不少于 ${g.min_chars || 0} 字`;
      sel.appendChild(opt);
    }
    if (data.default) sel.value = data.default;
  } catch {
    sel.innerHTML = '<option value="article">规范长文</option><option value="note">知识条目</option>';
  }
}

function renderProduceResult(r, opts = {}) {
  const out = document.getElementById("produce-output");
  const docxBtn = document.getElementById("btn-produce-docx");
  const podcastBtn = document.getElementById("btn-produce-podcast");
  const keepSources = !!opts.keepSources;
  const prevSources = keepSources ? lastProduce?.sources || [] : [];
  const sources =
    Array.isArray(r.sources) && r.sources.length ? r.sources : prevSources;

  lastProduce = {
    content: r.content || "",
    title: r.title || r.topic || "产出",
    genre: r.genre || lastProduce?.genre || "",
    topic: r.topic || lastProduce?.topic || "",
    sources,
    wiki_page: r.wiki_page || lastProduce?.wiki_page || "",
    wiki_type: r.wiki_type || lastProduce?.wiki_type || "",
  };
  producePhase = opts.finalized ? "finalized" : "draft";

  mountProduceEditor(lastProduce.content);
  setProduceReviseBarVisible(true);
  updateProduceFinalizeUI();
  renderProduceConfirmPanel(lastProduce);

  let footer = "";
  const meta = [];
  if (r.genre_label) meta.push(`体例：${escHtml(r.genre_label)}`);
  if (r.rag_chunks_used != null) meta.push(`引用 ${r.rag_chunks_used} 段素材`);
  if (sources?.length) meta.push(`${sources.length} 个来源`);
  if (meta.length) {
    footer += `<footer class="produce-footer"><p class="hint">${meta.join(" · ")}</p>`;
  }
  if (lastProduce.wiki_page && producePhase === "finalized") {
    footer += `<p>已保存到知识库：<code>${escHtml(lastProduce.wiki_page)}</code>（${typeZh(r.wiki_type || lastProduce.wiki_type || "note")} · 草稿）</p>`;
  } else if (r.saved_to) {
    footer += `<p>已保存：<code>${escHtml(r.saved_to)}</code></p>`;
  }
  if (footer) footer += "</footer>";
  out.innerHTML =
    footer ||
    `<p class="hint">可在上方编辑器直接修改；满意后点「确认定稿」写入知识库。</p>`;

  docxBtn.disabled = !lastProduce.content;
  if (podcastBtn) {
    const isPodcast = lastProduce.genre === "podcast";
    podcastBtn.classList.toggle("hidden", !isPodcast);
    podcastBtn.disabled = !isPodcast || !lastProduce.content;
  }
}

document.getElementById("btn-produce").addEventListener("click", () => {
  produceStream();
});
document.getElementById("btn-service-loop-templates")?.addEventListener("click", () => {
  window.YizhiServiceLoop?.openModal?.();
});

async function produceReviseFallback(payload) {
  const r = await api("/api/produce/revise", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  renderProduceResult(r, { keepSources: !payload.use_rag });
}

async function produceReviseStream() {
  const instruction = document.getElementById("produce-revise-input")?.value.trim() || "";
  if (!instruction) return uiInfo("请先填写改稿要求");
  const content = syncProduceFromEditor();
  if (!content.trim()) return uiInfo("当前正文为空");
  const useRag = !!document.getElementById("produce-revise-rag")?.checked;
  const out = document.getElementById("produce-output");
  const payload = {
    content,
    instruction,
    topic: lastProduce?.topic || document.getElementById("produce-input")?.value.trim() || "改稿",
    genre: lastProduce?.genre || document.getElementById("produce-genre")?.value || "article",
    brief: document.getElementById("produce-brief")?.value.trim() || "",
    use_rag: useRag,
    first_principles_review: !!document.getElementById("produce-first-principles")?.checked,
    scope_paths: getAskScopePayload(),
    folder_ids: getAskFolderIds(),
  };

  producePhase = "streaming";
  setProduceActionBusy(true);
  destroyProduceEditor();
  setProduceReviseBarVisible(true);
  let markdown = "";
  out.innerHTML = `<p class="hint">${useRag ? "正在检索并改稿…" : "正在按要求改稿…"}</p>`;

  const renderStreaming = () => {
    out.innerHTML =
      `<div class="produce-stream-wrap">${escHtml(markdown)}<span class="stream-cursor" aria-hidden="true">▋</span></div>`;
    out.scrollTop = out.scrollHeight;
  };

  try {
    const res = await fetch(`${API}/api/produce/revise/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (res.status === 404) {
      await produceReviseFallback(payload);
      return;
    }
    if (!res.ok) throw new Error(await res.text());
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let gotDone = false;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";
      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data:")) continue;
        const ev = JSON.parse(line.slice(5).trim());
        if (ev.type === "status") {
          if (!markdown) out.innerHTML = `<p class="hint">${escHtml(ev.text || "正在处理…")}</p>`;
        } else if (ev.type === "token") {
          markdown += ev.text;
          renderStreaming();
        } else if (ev.type === "error") {
          throw new Error(ev.text || "改稿失败");
        } else if (ev.type === "done") {
          gotDone = true;
          renderProduceResult(ev, { keepSources: !useRag });
        }
      }
    }
    if (!gotDone && markdown) {
      renderProduceResult(
        { content: markdown, topic: payload.topic, genre: payload.genre, title: lastProduce?.title },
        { keepSources: !useRag }
      );
    }
  } catch (e) {
    uiError(e);
    if (lastProduce?.content) renderProduceResult(lastProduce, { keepSources: true });
    else producePhase = "draft";
  } finally {
    setProduceActionBusy(false);
  }
}

async function produceFinalizeOrContinue() {
  if (producePhase === "finalized") {
    producePhase = "draft";
    updateProduceFinalizeUI();
    window.YizhiToast?.info?.("已回到草稿，可继续修改");
    return;
  }
  const content = syncProduceFromEditor();
  if (!content.trim()) return uiInfo("正文为空，无法定稿");
  const ritualBox = document.getElementById("produce-ritual-box");
  if (ritualBox && !ritualBox.classList.contains("hidden")) {
    const checks = [...ritualBox.querySelectorAll("input[type=checkbox]")];
    if (checks.length && !checks.every((c) => c.checked)) {
      const ok = window.confirm(
        "「今日可归档」清单尚未全部勾选。仍要定稿吗？（仅提醒，不强制）"
      );
      if (!ok) return;
    }
  }
  setProduceActionBusy(true);
  try {
    const r = await api("/api/produce/finalize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        content,
        topic: lastProduce?.topic || document.getElementById("produce-input")?.value.trim() || "未命名",
        genre: lastProduce?.genre || document.getElementById("produce-genre")?.value || "article",
        title: lastProduce?.title || "",
        wiki_page: lastProduce?.wiki_page || "",
        wiki_type: lastProduce?.wiki_type || "",
      }),
    });
    lastProduce = {
      ...(lastProduce || {}),
      content,
      title: r.title || lastProduce?.title,
      wiki_page: r.wiki_page,
      wiki_type: r.wiki_type || lastProduce?.wiki_type,
      topic: r.topic || lastProduce?.topic,
      genre: r.genre || lastProduce?.genre,
    };
    producePhase = "finalized";
    updateProduceFinalizeUI();
    const out = document.getElementById("produce-output");
    if (out) {
      out.innerHTML = `<footer class="produce-footer"><p>已保存到知识库：<code>${escHtml(
        r.wiki_page
      )}</code>（${typeZh(r.wiki_type || "note")} · 草稿）</p></footer>`;
    }
    window.YizhiToast?.success?.(`已定稿：${r.wiki_page}`);
  } catch (e) {
    uiError(e);
  } finally {
    setProduceActionBusy(false);
  }
}

document.getElementById("btn-produce-revise")?.addEventListener("click", () => {
  produceReviseStream();
});
document.getElementById("btn-produce-finalize")?.addEventListener("click", () => {
  produceFinalizeOrContinue();
});

function renderDeduceMarkdown(md) {
  const text = String(md || "");
  if (window.YizhiRichEditor?.renderMarkdown) {
    return window.YizhiRichEditor.renderMarkdown(text);
  }
  if (window.marked?.parse) {
    try {
      return window.marked.parse(text, { breaks: true, gfm: true });
    } catch {
      /* fall through */
    }
  }
  return escHtml(text).replace(/\n/g, "<br>");
}

let lastDeduce = null;

function setDeduceDownloadEnabled(on) {
  const dlBtn = document.getElementById("btn-deduce-download");
  if (dlBtn) dlBtn.disabled = !on;
}

function renderDeduceGraph(graph, onReady) {
  const host = document.getElementById("deduce-graph-host");
  if (!host || !window.DeduceGraph) {
    if (typeof onReady === "function") onReady();
    return;
  }
  window.DeduceGraph.render(
    host,
    graph || { nodes: [], edges: [] },
    (path) => openMemoInEditor(path),
    onReady
  );
}

function renderDeduceResult(r) {
  const out = document.getElementById("deduce-output");
  const hint = document.getElementById("deduce-saved-hint");
  let html = r.content_html || "";
  if (!html && r.content) {
    html = renderDeduceMarkdown(r.content);
  }
  let footer = "";
  if (r.rag_chunks_used != null) {
    footer += `<footer class="deduce-footer"><p class="hint">引用 ${r.rag_chunks_used} 段素材`;
    if (r.sources?.length) footer += ` · ${r.sources.length} 个来源`;
    footer += "</p>";
  }
  if (r.wiki_page) {
    footer += `<p>已保存为笔记：<code>${escHtml(r.wiki_page)}</code></p>`;
    hint.classList.remove("hidden");
    hint.innerHTML = `已保存至 <code>${escHtml(r.wiki_page)}</code>，可在「笔记」中查看。`;
  } else {
    hint.classList.add("hidden");
    hint.textContent = "";
  }
  if (footer) footer += "</footer>";
  out.innerHTML = html + footer;
  lastDeduce = {
    content: r.content || "",
    title: r.title || r.query || "推演",
    query: r.query || "",
    graph: r.graph || null,
  };
  setDeduceDownloadEnabled(Boolean(lastDeduce.content));
  renderDeduceGraph(r.graph);
}

async function deduceStream() {
  const query = document.getElementById("deduce-input").value.trim();
  if (!query) return;
  const out = document.getElementById("deduce-output");
  const btn = document.getElementById("btn-deduce");
  const hint = document.getElementById("deduce-saved-hint");
  const payload = { query, scope_paths: getAskScopePayload(), folder_ids: getAskFolderIds() };

  btn.disabled = true;
  setDeduceDownloadEnabled(false);
  lastDeduce = null;
  hint.classList.add("hidden");
  let markdown = "";
  let currentSection = "report";
  out.innerHTML = `<p class="hint">正在检索知识库并推演…</p>`;
  renderDeduceGraph({ nodes: [], edges: [] });

  const renderStreaming = () => {
    const bodyHtml = renderDeduceMarkdown(markdown);
    out.innerHTML = `<div class="deduce-stream-wrap">${bodyHtml}<span class="stream-cursor" aria-hidden="true">▋</span></div>`;
    out.scrollTop = out.scrollHeight;
  };

  try {
    const res = await fetch(`${API}/api/deduce/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";
      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data:")) continue;
        const ev = JSON.parse(line.slice(5).trim());
        if (ev.type === "status") {
          if (!markdown) {
            out.innerHTML = `<p class="hint">${escHtml(ev.text || "正在处理…")}</p>`;
          }
        } else if (ev.type === "graph") {
          renderDeduceGraph(ev.graph || { nodes: [], edges: [] });
        } else if (ev.type === "token") {
          if (ev.section === "graph_commentary" && currentSection !== "graph_commentary") {
            currentSection = "graph_commentary";
            markdown += "\n\n---\n\n";
          }
          markdown += ev.text;
          renderStreaming();
        } else if (ev.type === "done") {
          renderDeduceResult(ev);
        } else if (ev.type === "error") {
          out.innerHTML = `<p class="error">${escHtml(ev.message || "推演失败")}</p>`;
        }
      }
    }
  } catch (e) {
    out.innerHTML = `<p class="error">${escHtml(String(e))}</p>`;
  } finally {
    btn.disabled = false;
  }
}

document.getElementById("btn-deduce")?.addEventListener("click", () => {
  deduceStream();
});

document.getElementById("btn-deduce-download")?.addEventListener("click", async () => {
  if (!lastDeduce?.content) return;
  const btn = document.getElementById("btn-deduce-download");
  btn.disabled = true;
  try {
    const host = document.getElementById("deduce-graph-host");
    const graphPng = window.DeduceGraph?.exportPng ? await window.DeduceGraph.exportPng(host) : null;
    const res = await fetch(`${API}/api/deduce/export/docx`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: lastDeduce.title,
        content: lastDeduce.content,
        graph_png: graphPng || "",
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    const blob = await res.blob();
    const cd = res.headers.get("Content-Disposition") || "";
    let filename = "推演.docx";
    const m = cd.match(/filename\*=UTF-8''([^;]+)/i);
    if (m) filename = decodeURIComponent(m[1]);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    window.YizhiToast?.show?.(String(e), { type: "error" }) || alert(String(e));
  } finally {
    setDeduceDownloadEnabled(Boolean(lastDeduce?.content));
  }
});

async function produceFallback(payload) {
  const r = await api("/api/produce", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  renderProduceResult(r);
}

async function produceStream() {
  const topic = document.getElementById("produce-input").value.trim();
  if (!topic) return;
  const existing = (producePhase === "draft" || producePhase === "finalized") && getProduceMarkdown().trim();
  if (existing) {
    if (!confirm("当前有未定稿/已定稿内容，开始写将覆盖当前正文。确定继续？")) return;
  }
  const out = document.getElementById("produce-output");
  const btn = document.getElementById("btn-produce");
  const docxBtn = document.getElementById("btn-produce-docx");
  const genre = document.getElementById("produce-genre")?.value || "article";
  const brief = document.getElementById("produce-brief")?.value.trim() || "";
  const genreLabel = document.getElementById("produce-genre")?.selectedOptions?.[0]?.textContent?.split("（")[0] || "";
  const payload = {
    topic,
    genre,
    brief,
    save: false,
    save_to_wiki: false,
    first_principles_review: !!document.getElementById("produce-first-principles")?.checked,
    scope_paths: getAskScopePayload(),
    folder_ids: getAskFolderIds(),
  };

  producePhase = "streaming";
  destroyProduceEditor();
  setProduceReviseBarVisible(false);
  setProduceActionBusy(true);
  docxBtn.disabled = true;
  lastProduce = null;
  setProducePodcastHint("");
  let markdown = "";
  out.innerHTML = `<p class="hint">正在撰写${genreLabel ? `「${escHtml(genreLabel)}」` : ""}，检索知识库并生成正文…</p>`;

  const renderStreaming = () => {
    out.innerHTML =
      `<div class="produce-stream-wrap">${escHtml(markdown)}<span class="stream-cursor" aria-hidden="true">▋</span></div>`;
    out.scrollTop = out.scrollHeight;
  };

  try {
    const res = await fetch(`${API}/api/produce/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (res.status === 404) {
      await produceFallback(payload);
      return;
    }
    if (!res.ok) throw new Error(await res.text());

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let gotDone = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";
      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data:")) continue;
        const ev = JSON.parse(line.slice(5).trim());
        if (ev.type === "status") {
          if (!markdown) {
            out.innerHTML = `<p class="hint">${escHtml(ev.text || "正在处理…")}</p>`;
          }
        } else if (ev.type === "token") {
          markdown += ev.text;
          renderStreaming();
        } else if (ev.type === "error") {
          throw new Error(ev.text || "写作失败");
        } else if (ev.type === "done") {
          gotDone = true;
          renderProduceResult(ev);
        }
      }
    }
    if (!gotDone && markdown) {
      renderProduceResult({
        topic,
        genre,
        genre_label: genreLabel,
        content: markdown,
        title: topic,
      });
    }
  } catch (e) {
    const msg = String(e?.message || e);
    const isNet =
      e?.name === "TypeError" ||
      /failed to fetch|networkerror|load failed/i.test(msg);
    if (isNet) {
      out.innerHTML = `<p class="hint">流式写作连接失败，改用非流式重试…</p>`;
      try {
        await produceFallback(payload);
        return;
      } catch (e2) {
        out.innerHTML = `<p class="error">${escHtml(
          `写作请求失败（无法连接本地服务 18765）。请确认易知已完全启动后重试。\n${e2}`
        )}</p>`;
        producePhase = "idle";
        return;
      }
    }
    out.innerHTML = `<p class="error">${escHtml(msg)}</p>`;
    producePhase = "idle";
  } finally {
    setProduceActionBusy(false);
  }
}

function podcastDownloadFilename(title, ext) {
  const base = (title || "播客").replace(/[\\/:*?"<>|]/g, "-").slice(0, 60);
  return `${base}.${ext || "mp3"}`;
}

async function downloadPodcastFile(relPath, filename) {
  const res = await fetch(`${API}/api/podcast/audio?path=${encodeURIComponent(relPath)}`);
  if (!res.ok) throw new Error(await res.text());
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

document.getElementById("btn-produce-podcast")?.addEventListener("click", async () => {
  syncProduceFromEditor();
  if (!lastProduce?.content) return;
  const btn = document.getElementById("btn-produce-podcast");
  btn.disabled = true;
  btn.classList.add("is-busy");
  btn.textContent = "正在合成…";
  setProducePodcastHint("正在调用 TTS 合成播客音频（按对话分段，请稍候）…", "busy");
  setStatus("正在合成播客音频…");
  try {
    const r = await api("/api/produce/podcast-audio", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: lastProduce.content, title: lastProduce.title }),
    });
    if (r.merged_file) {
      setProducePodcastHint(`合成完成：已合并为 1 个完整文件（由 ${r.segments || 0} 段拼接）`, "");
    } else if (r.merged_error) {
      setProducePodcastHint(
        `分段已生成（${r.segments || 0}），完整合并失败：${r.merged_error}`,
        "error"
      );
    } else {
      setProducePodcastHint(`合成完成：共 ${r.segments || 0} 段音频（未生成完整文件）`, "error");
    }
    renderPodcastDock({ ...r, title: r.title || lastProduce?.title });
    renderProduceConfirmPanel(lastProduce);
    setStatus(r.merged_file ? "播客完整音频已就绪" : "播客分段已合成，完整合并失败");
  } catch (e) {
    setProducePodcastHint(String(e), "error");
    setStatus("播客音频合成失败");
  } finally {
    btn.classList.remove("is-busy");
    btn.textContent = PODCAST_BTN_LABEL;
    btn.disabled = !lastProduce?.content || lastProduce?.genre !== "podcast";
  }
});

document.getElementById("produce-genre")?.addEventListener("change", (e) => {
  const podcastBtn = document.getElementById("btn-produce-podcast");
  if (!podcastBtn) return;
  const isPodcast = e.target.value === "podcast";
  podcastBtn.classList.toggle("hidden", !isPodcast);
  podcastBtn.disabled = !isPodcast || !lastProduce?.content;
});

document.getElementById("btn-produce-docx")?.addEventListener("click", async () => {
  syncProduceFromEditor();
  if (!lastProduce?.content) return;
  const btn = document.getElementById("btn-produce-docx");
  btn.disabled = true;
  try {
    const res = await fetch(`${API}/api/produce/export/docx`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        content: lastProduce.content,
        title: lastProduce.title,
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const dispo = res.headers.get("Content-Disposition") || "";
    let filename = "产出.docx";
    const m = dispo.match(/filename\*=UTF-8''([^;]+)/i);
    if (m) filename = decodeURIComponent(m[1]);
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    uiError(e);
  } finally {
    btn.disabled = !lastProduce?.content;
  }
});

document.getElementById("btn-url").addEventListener("click", async () => {
  const url = document.getElementById("url-input").value.trim();
  if (!url) return uiInfo("请先粘贴网页地址");
  const btn = document.getElementById("btn-url");
  if (btn?.disabled) return;
  try {
    await submitUrlIngest(url, document.getElementById("url-force").checked);
  } catch (e) {
    document.getElementById("manage-log").textContent = `✗ ${e.message || e}\n`;
    renderUrlJobUi(null);
    finishUrlJobCallbacks();
  }
});

document.getElementById("btn-text-import")?.addEventListener("click", async () => {
  const text = document.getElementById("text-import-body")?.value.trim() || "";
  const title = document.getElementById("text-import-title")?.value.trim() || "";
  const log = document.getElementById("manage-log");
  if (!text) return uiInfo("请先粘贴文本内容");
  if (textImportBusy) return;

  const saveBtn = document.getElementById("btn-text-import");
  const steps = ["正在保存文本…", "正在写入检索库…"];
  let stepIdx = 0;
  setTextImportFeedback("");
  setTextImportBusy(true, steps[0]);
  saveBtn.textContent = "处理中…";
  log.textContent = "正在保存并写入检索库…\n";

  const stepTimer = window.setInterval(() => {
    stepIdx = Math.min(stepIdx + 1, steps.length - 1);
    setTextImportBusy(true, steps[stepIdx]);
  }, 600);

  try {
    const r = await api("/api/text", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, title }),
    });
    window.clearInterval(stepTimer);
    setTextImportBusy(false);
    setTextImportFeedback(`✓ 已保存「${r.title}」，约 ${r.chars} 字，已加入问答检索。`, "success");
    log.textContent = `✓ 已保存：${r.title}\n  笔记位置：${r.wiki_page}\n  原文备份：${r.localized}\n  字数：约 ${r.chars} 字\n`;
    document.getElementById("text-import-body").value = "";
    document.getElementById("text-import-title").value = "";
    loadAssets();
    window.setTimeout(() => {
      setTextImportFeedback("");
      closeTextImportModal(true);
    }, 900);
  } catch (e) {
    window.clearInterval(stepTimer);
    setTextImportBusy(false);
    const msg = e.message || String(e);
    setTextImportFeedback(`✗ ${msg}`, "error");
    log.textContent = `✗ ${msg}\n`;
  } finally {
    saveBtn.textContent = "保存并加入检索";
  }
});

async function loadWorkflows() {
  const grid = document.getElementById("workflow-grid");
  const skillSel = document.getElementById("workflow-custom-skill");
  if (!grid) return;
  try {
    const data = await api("/api/workflows");
    grid.innerHTML = "";
    const all = [...(data.custom || []), ...(data.builtin || [])];
    if (skillSel) {
      skillSel.innerHTML = "";
      for (const w of data.builtin || []) {
        const opt = document.createElement("option");
        opt.value = w.skill;
        opt.textContent = w.label;
        skillSel.appendChild(opt);
      }
    }
    for (const w of all) {
      grid.appendChild(buildWorkflowCard(w));
    }
    if (!all.length) {
      grid.innerHTML = '<p class="hint">暂无工作流</p>';
    }
  } catch (e) {
    grid.innerHTML = `<p class="error">${escHtml(String(e))}</p>`;
  }
}

function buildWorkflowCard(w) {
  const card = document.createElement("div");
  card.className = "workflow-card" + (w.builtin ? "" : " is-custom");
  const paramKey = w.param_key;
  let paramInput = "";
  if (paramKey) {
    paramInput =
      `<input type="text" class="workflow-param" data-key="${escHtml(paramKey)}" ` +
      `placeholder="${escHtml(w.param_placeholder || "")}" />`;
  }
  card.innerHTML =
    `<div class="workflow-card-head">` +
    `<strong>${escHtml(w.label)}</strong>` +
    (w.builtin ? "" : `<button type="button" class="workflow-del danger" title="删除">×</button>`) +
    `</div>` +
    `<p class="workflow-desc hint">${escHtml(w.description || "")}</p>` +
    paramInput +
    `<button type="button" class="workflow-run primary">运行</button>`;
  card.querySelector(".workflow-run")?.addEventListener("click", () => runWorkflowCard(w, card));
  card.querySelector(".workflow-del")?.addEventListener("click", async () => {
    if (!(await uiConfirm(`删除自定义工作流「${w.label}」？`))) return;
    await api(`/api/workflows?id=${encodeURIComponent(w.id)}`, { method: "DELETE" });
    loadWorkflows();
  });
  return card;
}

async function runWorkflowCard(w, cardEl) {
  if (workflowRunBusyCard) return;
  const log = document.getElementById("workflow-log");
  const manageLog = document.getElementById("manage-log");
  const params = { ...(w.default_params || {}) };
  const input = cardEl?.querySelector(".workflow-param");
  if (input?.dataset.key && input.value.trim()) {
    params[input.dataset.key] = input.value.trim();
  }
  if (w.skill === "wiki-url" && !params.url) {
    const urlVal = document.getElementById("url-input")?.value.trim();
    if (urlVal) params.url = urlVal;
  }
  if (w.skill === "wiki-url" && params.force === undefined) {
    params.force = document.getElementById("url-force")?.checked || false;
  }
  if (w.skill === "wiki-url" && !params.url) {
    return uiInfo("请在工作流卡片或上方输入框填写网页地址");
  }

  workflowRunBusyCard = cardEl;
  setWorkflowCardBusy(cardEl, true);

  if (w.skill === "wiki-url") {
    if (log) {
      log.classList.remove("hidden");
      log.textContent = `正在运行：${w.label}…\n`;
    }
    try {
      const r = await api("/api/workflows/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: w.id, params }),
      });
      if (!r.ok) {
        const msg = r.error || r.output || "工作流执行失败";
        if (log) log.textContent = String(msg);
        if (manageLog) manageLog.textContent = String(msg);
        releaseWorkflowRunBusy();
        return;
      }
      if (r.async && r.job_id) {
        if (log) log.textContent = `${r.output || "已提交后台抓取任务"}\n`;
        if (manageLog) manageLog.textContent = `${r.output || "已提交后台抓取任务"}\n`;
        urlJobCallbacks = {
          workflowLabel: w.label,
          clearUrlInput: true,
          onDone: releaseWorkflowRunBusy,
        };
        trackUrlJobs(r.job_id);
        setStatus(`正在运行：${w.label}…`);
        return;
      }
      const text = r.output || JSON.stringify(r, null, 2);
      if (log) log.textContent = text;
      if (manageLog) manageLog.textContent = text;
      setStatus(`${w.label} 已完成`);
      loadAssets();
    } catch (e) {
      const msg = String(e);
      if (log) log.textContent = msg;
      if (manageLog) manageLog.textContent = msg;
    } finally {
      releaseWorkflowRunBusy();
    }
    return;
  }

  if (log) {
    log.classList.remove("hidden");
    log.textContent = `正在运行：${w.label}…\n`;
  }
  try {
    const r = await api("/api/workflows/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: w.id, params }),
    });
    const text = r.output || JSON.stringify(r, null, 2);
    if (log) log.textContent = text;
    if (manageLog) manageLog.textContent = text;
    setStatus(`${w.label} 已完成`);
    if (w.skill === "wiki-ingest" || w.skill === "wiki-index") {
      loadAssets();
    }
    if (w.skill === "wiki-classify-suggest") {
      if (log) log.scrollTop = log.scrollHeight;
    }
  } catch (e) {
    const msg = String(e);
    if (log) log.textContent = msg;
    if (manageLog) manageLog.textContent = msg;
  } finally {
    releaseWorkflowRunBusy();
  }
}

document.getElementById("btn-workflow-add")?.addEventListener("click", async () => {
  const label = document.getElementById("workflow-custom-label")?.value.trim();
  const skill = document.getElementById("workflow-custom-skill")?.value;
  const param = document.getElementById("workflow-custom-param")?.value.trim();
  if (!label || !skill) return uiInfo("请填写名称并选择工作流类型");
  const params = {};
  const meta = await api("/api/workflows");
  const builtin = (meta.builtin || []).find((b) => b.skill === skill);
  if (param && builtin?.param_key) params[builtin.param_key] = param;
  try {
    await api("/api/workflows", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label, skill, params }),
    });
    document.getElementById("workflow-custom-label").value = "";
    document.getElementById("workflow-custom-param").value = "";
    loadWorkflows();
    setStatus("已添加自定义工作流");
  } catch (e) {
    uiError(e);
  }
});

document.getElementById("btn-upload").addEventListener("click", async () => {
  const input = document.getElementById("upload-file");
  const log = document.getElementById("manage-log");
  if (!input.files?.length) return uiInfo("请选择文件");
  const btn = document.getElementById("btn-upload");
  btn.disabled = true;
  try {
    await startBackgroundUpload(input.files, log);
    input.value = "";
  } catch (e) {
    if (log) log.textContent += `✗ ${e.message || e}\n`;
  } finally {
    btn.disabled = false;
  }
});

async function loadLinkedDirs() {
  const tbody = document.getElementById("linked-dirs-tbody");
  const meta = document.getElementById("linked-dirs-meta");
  if (!tbody) return;
  try {
    const data = await api("/api/linked-dirs");
    tbody.innerHTML = "";
    for (const item of data.items || []) {
      const tr = document.createElement("tr");
      const countLabel = item.truncated
        ? `${item.supported_count}+`
        : String(item.supported_count ?? 0);
      const statusHint = item.exists ? "" : "（目录不存在）";
      const pathTd = document.createElement("td");
      pathTd.className = "linked-dir-path";
      pathTd.innerHTML =
        `<strong>${escHtml(item.label || pathBasename(item.path))}</strong>` +
        `<small>${escHtml(item.path)}${statusHint}</small>`;
      tr.appendChild(pathTd);
      tr.appendChild(renderLinkedDirFolderCell(item));
      const countTd = document.createElement("td");
      countTd.className = "col-count";
      countTd.textContent = countLabel;
      tr.appendChild(countTd);
      const timeTd = document.createElement("td");
      timeTd.className = "col-time";
      timeTd.innerHTML = formatLinkedIndexCell(item);
      tr.appendChild(timeTd);
      const opsTd = document.createElement("td");
      opsTd.className = "col-ops";
      opsTd.innerHTML = `<div class="table-ops"><div class="btn-group"></div></div>`;
      tr.appendChild(opsTd);
      const group = tr.querySelector(".btn-group");
      const btnToggle = document.createElement("button");
      btnToggle.type = "button";
      btnToggle.textContent = item.enabled ? "暂停" : "启用";
      btnToggle.addEventListener("click", async () => {
        const r = await api(`/api/linked-dirs?path=${encodeURIComponent(item.path)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enabled: !item.enabled }),
        });
        loadLinkedDirs();
        if (r.indexing) trackLinkedIndexJobs();
      });
      const btnRemove = document.createElement("button");
      btnRemove.type = "button";
      btnRemove.className = "danger";
      btnRemove.textContent = "移除";
      btnRemove.addEventListener("click", async () => {
        if (!(await uiConfirm(`移除外联目录？\n${item.path}\n\n不会删除原文件夹，仅从 RAG 索引中排除。`))) return;
        await api(`/api/linked-dirs?path=${encodeURIComponent(item.path)}`, { method: "DELETE" });
        loadLinkedDirs();
        setStatus("已移除外联目录");
      });
      group.append(btnToggle, btnRemove);
      if (!item.enabled) tr.classList.add("is-disabled");
      if (item.index_job?.status === "queued" || item.index_job?.status === "running") {
        tr.classList.add("is-indexing");
      }
      tbody.appendChild(tr);
    }
    if (!data.items?.length) {
      tbody.innerHTML = '<tr class="empty-row"><td colspan="5">尚未添加外联目录。可指定任意本地文件夹，无需复制到易知。</td></tr>';
    }
    if (meta) {
      const indexing = (data.index_jobs || []).some(
        (j) => j.status === "queued" || j.status === "running",
      );
      meta.textContent =
        `已启用 ${data.active_count ?? 0} 个目录` +
        (data.auto_index ? ` · 自动监测变更（约 ${data.poll_seconds}s）` : " · 自动监测已关闭，请手动刷新索引") +
        (indexing ? " · 后台索引进行中…" : "");
    }
    const hasActive = (data.index_jobs || []).some(
      (j) => j.status === "queued" || j.status === "running",
    );
    if (hasActive) trackLinkedIndexJobs();
    else renderLinkedIndexBanner([]);
  } catch (e) {
    tbody.innerHTML = `<tr class="empty-row"><td colspan="5">${escHtml(String(e))}</td></tr>`;
  }
}

function pathBasename(p) {
  if (!p) return "";
  const parts = p.replace(/\\/g, "/").split("/");
  return parts[parts.length - 1] || p;
}

async function addLinkedDir() {
  const input = document.getElementById("linked-dir-input");
  const path = input?.value.trim();
  if (!path) {
    window.YizhiToast?.error("请输入或选择目录路径");
    return;
  }
  if (window.YizhiJobs?.isBusy("linked-add")) return;
  window.YizhiJobs?.setBusy("linked-add", true);
  try {
    const data = await api("/api/linked-dirs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    if (input) input.value = "";
    loadLinkedDirs();
    setStatus(data.indexing ? "外联目录已添加，正在后台索引…" : "外联目录已添加");
    document.getElementById("manage-log").textContent =
      "外联目录已添加，正在后台建立 RAG 索引（文件不复制，仅读取）。\n进度见任务中心。\n";
    if (data.indexing) {
      window.YizhiJobs?.startPolling();
      trackLinkedIndexJobs();
    }
    window.YizhiToast?.info("外联目录已添加，后台索引中");
  } catch (e) {
    window.YizhiToast?.error(String(e));
  } finally {
    window.YizhiJobs?.setBusy("linked-add", false);
  }
}

document.getElementById("btn-linked-dir-add")?.addEventListener("click", addLinkedDir);

async function browseLinkedDirectory() {
  const input = document.getElementById("linked-dir-input");
  if (window.myknowledge?.pickDirectory) {
    try {
      const picked = await window.myknowledge.pickDirectory();
      if (picked && input) {
        input.value = picked;
        return;
      }
      if (picked === null) return;
    } catch (e) {
      console.warn("Electron pickDirectory failed:", e);
    }
  }
  try {
    const r = await api("/api/pick-directory", { method: "POST" });
    if (r.canceled) return;
    if (r.path && input) input.value = r.path;
  } catch (e) {
    uiError(`无法打开文件夹选择器：${e.message || e}\n请直接在输入框粘贴目录路径。`);
  }
}

document.getElementById("btn-linked-dir-browse")?.addEventListener("click", browseLinkedDirectory);
document.getElementById("btn-linked-dir-reindex")?.addEventListener("click", async () => {
  const log = document.getElementById("manage-log");
  if (window.YizhiJobs?.isBusy("linked-reindex")) return;
  window.YizhiJobs?.setBusy("linked-reindex", true);
  if (log) log.textContent = "已提交外联目录索引任务，后台并发处理中…\n";
  try {
    const r = await api("/api/linked-dirs/reindex", { method: "POST" });
    loadLinkedDirs();
    setStatus("外联索引已在后台刷新");
    window.YizhiJobs?.startPolling();
    trackLinkedIndexJobs();
    window.YizhiToast?.info("外联索引任务已提交");
    if (r.already_running && log) log.textContent = "已有索引任务在进行中，请稍候…\n";
  } catch (e) {
    if (log) log.textContent = String(e);
    window.YizhiToast?.error(String(e));
  } finally {
    window.YizhiJobs?.setBusy("linked-reindex", false);
  }
});

async function loadAssets() {
  const r = await api(`/api/assets?page=${assetsState.page}&size=${DEFAULT_PAGE_SIZE}`);
  const ul = document.getElementById("asset-list");
  ul.innerHTML = "";
  for (const a of r.items || []) {
    const li = document.createElement("li");
    li.className = "clickable-asset";
    li.innerHTML = `${escHtml(a.filename)}<small>${assetCatZh(a.category)} · ${escHtml(a.rel_path)}</small>`;
    li.title = "点击打开原文件";
    li.addEventListener("click", () => openAssetFile(a.rel_path));
    ul.appendChild(li);
  }
  if (!r.items?.length) ul.innerHTML = '<li class="empty-item">暂无已导入文件</li>';
  renderPager("asset-list-pager", r, (p) => {
    assetsState.page = p;
    loadAssets();
  });
}

async function loadLibrary() {
  const q = document.getElementById("library-search")?.value.trim() || "";
  if (libraryView === "assets") {
    libAssetsState.q = q;
    const r = await api(
      `/api/library/assets?page=${libAssetsState.page}&size=${DEFAULT_PAGE_SIZE}&q=${encodeURIComponent(q)}`
    );
    const tbody = document.getElementById("library-asset-tbody");
    tbody.innerHTML = "";
    const startNo = ((r.page || 1) - 1) * (r.size || DEFAULT_PAGE_SIZE);
    for (let i = 0; i < (r.items || []).length; i++) {
      const a = r.items[i];
      const tr = document.createElement("tr");
      const folderNames = (a.folder_ids || [])
        .map((id) => folderNameById(id))
        .filter(Boolean)
        .map((n) => `<span class="folder-chip folder-chip-sm">${escHtml(n)}</span>`)
        .join("");
      tr.innerHTML =
        `<td class="col-no">${startNo + i + 1}</td>` +
        `<td class="col-title title-cell"><strong>${escHtml(a.filename)}</strong>` +
        (a.wiki_page ? `<small>笔记：${escHtml(a.wiki_page)}</small>` : "") +
        (folderNames ? `<div class="asset-folder-names">${folderNames}</div>` : "") +
        `</td>` +
        `<td class="col-type">${escHtml(assetExt(a.filename).toLowerCase())}</td>` +
        `<td class="col-ops"><div class="table-ops"><div class="btn-group"></div></div></td>`;
      const group = tr.querySelector(".btn-group");
      const btnFolders = document.createElement("button");
      btnFolders.type = "button";
      btnFolders.textContent = "资料夹";
      btnFolders.title = "分配资料夹";
      btnFolders.addEventListener("click", (ev) => {
        ev.stopPropagation();
        openAssetFolderEditor(a, tr);
      });
      const btnView = document.createElement("button");
      btnView.type = "button";
      btnView.className = "primary";
      btnView.textContent = "浏览";
      btnView.title = "浏览";
      btnView.addEventListener("click", (ev) => {
        ev.stopPropagation();
        browseAsset(a);
      });
      const btnRename = document.createElement("button");
      btnRename.type = "button";
      btnRename.textContent = "重命名";
      btnRename.title = "重命名";
      btnRename.addEventListener("click", (ev) => {
        ev.stopPropagation();
        renameLibraryAsset(a);
      });
      const btnDel = document.createElement("button");
      btnDel.type = "button";
      btnDel.className = "danger";
      btnDel.textContent = "删除";
      btnDel.title = "删除";
      btnDel.addEventListener("click", (ev) => {
        ev.stopPropagation();
        deleteLibraryAsset(a);
      });
      group.appendChild(btnView);
      group.appendChild(btnFolders);
      group.appendChild(btnRename);
      group.appendChild(btnDel);
      tbody.appendChild(tr);
    }
    if (!r.items?.length) {
      tbody.innerHTML = '<tr class="empty-row"><td colspan="4">暂无原始文件，可点「上传」添加</td></tr>';
    }
    renderPager("library-asset-pager", r, (p) => {
      libAssetsState.page = p;
      loadLibrary();
    });
    return;
  }

  if (libraryView === "external") {
    libExternalState.q = q;
    const r = await api(
      `/api/library/external?page=${libExternalState.page}&size=${DEFAULT_PAGE_SIZE}&q=${encodeURIComponent(q)}`
    );
    const box = document.getElementById("library-external-list");
    box.innerHTML = "";
    for (const item of r.items || []) {
      const div = document.createElement("div");
      div.className = "item";
      div.innerHTML =
        `<strong>${escHtml(item.title || item.rel_path)}</strong>` +
        `<div class="library-item-meta">${escHtml(item.external_path || "")}</div>` +
        `<div>${escHtml(item.preview || "")}…</div>`;
      box.appendChild(div);
    }
    if (!r.items?.length) {
      box.innerHTML = '<p class="empty-row">暂无外联索引内容，请在「导入资料」添加外联目录</p>';
    }
    renderPager("library-external-pager", r, (p) => {
      libExternalState.page = p;
      loadLibrary();
    });
    return;
  }

  libRagState.q = q;
  const r = await api(
    `/api/library/rag?page=${libRagState.page}&size=${DEFAULT_PAGE_SIZE}&q=${encodeURIComponent(q)}`
  );
  const box = document.getElementById("library-rag-list");
  box.innerHTML = "";
  for (const item of r.items || []) {
    const div = document.createElement("div");
    div.className = "item";
    const tags = (item.tags || []).map((t) => `<span class="library-tag">${escHtml(t)}</span>`).join("");
    let source = item.rel_path || "";
    if (item.asset_filename) source += ` · 原文件：${item.asset_filename}`;
    else if (item.asset_path) source += ` · 原文件：${item.asset_path}`;
    div.innerHTML =
      `<strong>${escHtml(item.title || item.id)}</strong>` +
      (tags ? `<div>${tags}</div>` : "") +
      `<div class="library-item-meta">${escHtml(source)}</div>` +
      `<div>${escHtml((item.text || "").slice(0, 280))}…</div>`;
    if (item.asset_path) {
      const link = document.createElement("button");
      link.type = "button";
      link.className = "link-btn";
      link.textContent = "浏览原文件";
      link.style.marginTop = "6px";
      link.addEventListener("click", () =>
        browseAsset({ rel_path: item.asset_path, filename: item.asset_filename || item.asset_path })
      );
      div.appendChild(link);
    }
    box.appendChild(div);
  }
  if (!r.items?.length) box.textContent = "暂无检索知识片段";
  renderPager("library-rag-pager", r, (p) => {
    libRagState.page = p;
    loadLibrary();
  });
}

function switchLibraryView(view) {
  libraryView = view;
  document.querySelectorAll(".lib-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.lib === view);
  });
  document.getElementById("library-assets-view")?.classList.toggle("hidden", view !== "assets");
  document.getElementById("library-rag-view")?.classList.toggle("hidden", view !== "rag");
  document.getElementById("library-external-view")?.classList.toggle("hidden", view !== "external");
  if (view === "assets") libAssetsState.page = 1;
  else if (view === "rag") libRagState.page = 1;
  else libExternalState.page = 1;
  loadLibrary();
}

document.querySelectorAll(".lib-tab").forEach((btn) => {
  btn.addEventListener("click", () => switchLibraryView(btn.dataset.lib));
});
document.getElementById("btn-library-refresh")?.addEventListener("click", () => {
  if (libraryView === "assets") libAssetsState.page = 1;
  else if (libraryView === "external") libExternalState.page = 1;
  else libRagState.page = 1;
  loadLibrary();
});
document.getElementById("btn-library-upload")?.addEventListener("click", () => {
  document.getElementById("library-upload-input")?.click();
});
document.getElementById("library-upload-input")?.addEventListener("change", async (e) => {
  const input = e.target;
  if (!input.files?.length) return;
  try {
    await startBackgroundUpload(input.files, null);
  } catch (err) {
    uiError(err.message || err);
  }
  input.value = "";
});
document.getElementById("library-search")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    if (libraryView === "assets") libAssetsState.page = 1;
    else libRagState.page = 1;
    loadLibrary();
  }
});

let selectedHistoryEntry = null;
let historyMenuCloseHandler = null;

function closeHistoryMenu() {
  document.querySelectorAll(".history-menu-pop").forEach((el) => el.remove());
  if (historyMenuCloseHandler) {
    document.removeEventListener("click", historyMenuCloseHandler);
    historyMenuCloseHandler = null;
  }
}

function openHistoryMenu(btn, entry) {
  closeHistoryMenu();
  const pop = document.createElement("div");
  pop.className = "history-menu-pop";
  pop.innerHTML =
    '<button type="button" data-act="rename">修改</button>' +
    '<button type="button" data-act="export">导出</button>' +
    '<button type="button" data-act="delete" class="danger">删除</button>';
  document.body.appendChild(pop);

  const rect = btn.getBoundingClientRect();
  const left = Math.min(rect.left, window.innerWidth - pop.offsetWidth - 8);
  pop.style.top = `${rect.bottom + 4}px`;
  pop.style.left = `${Math.max(8, left)}px`;

  pop.addEventListener("click", (e) => {
    e.stopPropagation();
    const act = e.target.closest("button")?.dataset.act;
    if (!act) return;
    closeHistoryMenu();
    if (act === "rename") renameHistoryEntry(entry);
    else if (act === "export") exportHistoryEntry(entry);
    else if (act === "delete") deleteHistoryEntry(entry);
  });

  historyMenuCloseHandler = (e) => {
    if (!pop.contains(e.target) && e.target !== btn) closeHistoryMenu();
  };
  setTimeout(() => document.addEventListener("click", historyMenuCloseHandler), 0);
}

async function renameHistoryEntry(entry) {
  const next = prompt("修改对话名称", entry.question || "");
  if (next === null) return;
  const question = next.trim();
  if (!question || question === entry.question) return;
  try {
    await api(`/api/memory/history/${entry.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    await loadHistory();
  } catch (e) {
    uiError(e);
  }
}

async function exportHistoryEntry(entry) {
  try {
    const res = await fetch(`${API}/api/memory/history/${entry.id}/export/docx`);
    if (!res.ok) throw new Error(await res.text());
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const dispo = res.headers.get("Content-Disposition") || "";
    let filename = "对话记录.docx";
    const m = dispo.match(/filename\*=UTF-8''([^;]+)/i);
    if (m) filename = decodeURIComponent(m[1]);
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    uiError(e);
  }
}

async function deleteHistoryEntry(entry) {
  const ok = await uiConfirm(`确定删除这条对话？\n\n${entry.question || ""}`);
  if (!ok) return;
  try {
    await api(`/api/memory/history/${entry.id}`, { method: "DELETE" });
    if (selectedHistoryEntry?.id === entry.id) {
      selectedHistoryEntry = null;
      renderHistoryDetail(null);
    }
    await loadHistory();
  } catch (e) {
    uiError(e);
  }
}

function formatHistoryMeta(entry) {
  const parts = [];
  if (entry.at) parts.push(entry.at);
  if (entry.session_id) parts.push("同一次对话");
  parts.push(entry.grounded ? "有依据" : "资料不足");
  return parts.join(" · ");
}

function renderHistoryDetail(entry) {
  const box = document.getElementById("history-detail");
  if (!entry) {
    box.innerHTML = '<p class="hint">选择左侧一条记录查看详情</p>';
    return;
  }
  let extra = "";
  if (entry.wiki_page) {
    extra += `<p class="hist-meta">已保存：<code>${escHtml(entry.wiki_page)}</code></p>`;
  }
  if (entry.sources?.length) {
    extra += `<p class="hist-meta">参考了 ${entry.sources.length} 处资料</p>`;
  }
  box.innerHTML =
    `<p class="hist-meta">${escHtml(formatHistoryMeta(entry))}</p>` +
    `<h3>问</h3><p>${escHtml(entry.question || "").replace(/\n/g, "<br>")}</p>` +
    `<h3>答</h3><div class="hist-body">${escHtml(entry.answer || "").replace(/\n/g, "<br>")}</div>` +
    extra;
}

async function loadHistorySessions() {
  const sel = document.getElementById("history-session-filter");
  const current = sel.value;
  const sessions = await api("/api/memory/sessions");
  sel.innerHTML = '<option value="">全部会话</option>';
  for (const s of sessions) {
    const opt = document.createElement("option");
    opt.value = s.id;
    const preview = s.preview ? ` — ${s.preview.slice(0, 40)}` : "";
    opt.textContent = `${(s.turn_count || 0)} 轮对话${preview}`;
    sel.appendChild(opt);
  }
  if ([...sel.options].some((o) => o.value === current)) sel.value = current;
}

async function loadHistory() {
  closeHistoryMenu();
  await loadHistorySessions();
  const sessionId = document.getElementById("history-session-filter").value;
  const q = sessionId ? `&session_id=${encodeURIComponent(sessionId)}` : "";
  const data = await api(`/api/memory/history?page=${historyState.page}&limit=${DEFAULT_PAGE_SIZE}${q}`);
  const ul = document.getElementById("history-list");
  ul.innerHTML = "";
  selectedHistoryEntry = null;
  renderHistoryDetail(null);
  for (const entry of data.entries || []) {
    const li = document.createElement("li");
    li.className = "history-item";
    li.dataset.sessionId = entry.session_id || "";
    li.dataset.qaId = String(entry.id);
    const qPreview = (entry.question || "").slice(0, 48);
    const body = document.createElement("div");
    body.className = "history-item-body";
    body.innerHTML =
      `<strong>${escHtml(qPreview)}${(entry.question || "").length > 48 ? "…" : ""}</strong>` +
      `<small>${escHtml(formatHistoryMeta(entry))}</small>`;
    const menuBtn = document.createElement("button");
    menuBtn.type = "button";
    menuBtn.className = "history-menu-btn";
    menuBtn.title = "更多操作";
    menuBtn.textContent = "⋯";
    menuBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      openHistoryMenu(menuBtn, entry);
    });
    li.appendChild(body);
    li.appendChild(menuBtn);
    body.addEventListener("click", () => {
      document.querySelectorAll("#history-list li").forEach((x) => x.classList.remove("active"));
      li.classList.add("active");
      selectedHistoryEntry = entry;
      renderHistoryDetail(entry);
    });
    ul.appendChild(li);
  }
  if (!data.entries?.length) {
    ul.innerHTML = '<li class="empty-item">暂无历史问答</li>';
  }
  renderPager("history-list-pager", data, (p) => {
    historyState.page = p;
    loadHistory();
  });
}

function continueHistorySession() {
  const sid =
    selectedHistoryEntry?.session_id ||
    document.getElementById("history-session-filter").value;
  if (!sid) return uiInfo("请先选一条记录，或指定一次对话");
  setSessionId(sid);
  refreshSessionHint();
  switchTab("ask");
  renderAskThread();
}

document.getElementById("btn-history-refresh")?.addEventListener("click", async () => {
  historyState.page = 1;
  await loadHistorySessions();
  await loadHistory();
});
document.getElementById("history-session-filter")?.addEventListener("change", () => {
  historyState.page = 1;
  loadHistory();
});
document.getElementById("btn-history-continue")?.addEventListener("click", continueHistorySession);

const LICENSE_REASON_ZH = {
  no_license: "订阅易知后可使用全部功能（导入、问答、写作等）。",
  trial_expired: "30 天试用已结束，请订阅后继续使用（按自然日计算，与是否使用无关）。",
  expired: "订阅已到期，请续费后继续使用。",
  device_mismatch: "授权与当前电脑不匹配。换电脑需联系客服解绑后再激活。",
  invalid_token: "授权无效，请重新激活。",
  offline_grace_exceeded: "已超过 7 天未联网校验，请连接网络后重试。",
};

let licensePollTimer = null;
let currentLicenseOrderId = null;
let selectedLicensePlanId = null;
let currentLicenseStatus = null;
let licenseOverlayForced = false;

function isLicenseBlocked(lic) {
  return !!(lic && !lic.licensed && lic.reason !== "not_required");
}

function licenseBannerText(lic) {
  if (!lic || lic.reason === "not_required") return "";
  // 左上角仅展示已付费订阅；试用中不打扰
  if (lic.reason === "trial" || !lic.licensed) return "";
  if (lic.plan === "lifetime") {
    return "永久用户";
  }
  if (lic.reason === "ok") {
    const plan = planLabelZh(lic.plan);
    if (lic.expires_at) {
      const exp = String(lic.expires_at).slice(0, 10);
      return `订阅版 · ${plan} · 有效期至 ${exp}`;
    }
    return `订阅版 · ${plan}`;
  }
  return "";
}

function updateLicenseBanner(lic) {
  const el = document.getElementById("license-banner");
  if (!el) return;
  const text = licenseBannerText(lic);
  if (!text) {
    el.classList.add("hidden");
    el.textContent = "";
    el.classList.remove("is-lifetime");
    return;
  }
  el.textContent = text;
  el.classList.toggle("is-lifetime", lic.licensed && lic.plan === "lifetime");
  el.classList.remove("hidden");
}

function applyLicenseUi(lic) {
  currentLicenseStatus = lic;
  updateLicenseBanner(lic);
  updateLicenseAbout(lic);
  if (isLicenseBlocked(lic)) {
    document.body.classList.add("app-license-locked");
    showLicenseOverlay(lic, { forced: true });
    return false;
  }
  document.body.classList.remove("app-license-locked");
  licenseOverlayForced = false;
  const overlay = document.getElementById("license-overlay");
  overlay?.classList.remove("is-forced");
  return true;
}

function resetLicensePaymentUi() {
  selectedLicensePlanId = null;
  currentLicenseOrderId = null;
  document.getElementById("license-qr-wrap")?.classList.add("hidden");
  document.getElementById("license-qr").innerHTML = "";
  document.getElementById("license-order-meta").textContent = "";
  document.getElementById("btn-license-mock-pay")?.classList.add("hidden");
  document.getElementById("license-plans")?.classList.remove("has-selection");
  document.querySelectorAll(".license-plan-btn").forEach((btn) => {
    btn.classList.remove("is-selected", "is-dimmed");
    btn.disabled = false;
  });
}

function setLicensePlanSelection(planId) {
  selectedLicensePlanId = planId || null;
  const box = document.getElementById("license-plans");
  if (!box) return;
  const buttons = box.querySelectorAll(".license-plan-btn");
  if (!planId) {
    box.classList.remove("has-selection");
    buttons.forEach((btn) => btn.classList.remove("is-selected", "is-dimmed"));
    return;
  }
  box.classList.add("has-selection");
  buttons.forEach((btn) => {
    const active = btn.dataset.plan === planId;
    btn.classList.toggle("is-selected", active);
    btn.classList.toggle("is-dimmed", !active);
  });
}

function showLicenseOverlay(status, opts = {}) {
  const forced = opts.forced === true || (opts.forced !== false && isLicenseBlocked(status));
  licenseOverlayForced = forced;
  const overlay = document.getElementById("license-overlay");
  const reason = document.getElementById("license-reason");
  reason.textContent = LICENSE_REASON_ZH[status.reason] || "";
  resetLicensePaymentUi();
  overlay.classList.toggle("is-forced", forced);
  overlay.classList.remove("hidden");
  if (forced) {
    document.body.classList.add("app-license-locked");
  }
  loadLicensePlans();
  loadLicenseDeviceHint();
  const assetsHost = document.getElementById("license-assets");
  window.YizhiServiceLoop?.renderLicenseAssets?.(assetsHost, status);
}

async function loadLicenseDeviceHint() {
  const el = document.getElementById("license-device-hint");
  if (!el) return;
  try {
    const r = await api("/api/license/device-id");
    el.textContent = r.device_id ? `本机标识：${r.device_id}` : "";
  } catch {
    el.textContent = "";
  }
}

function hideLicenseOverlay(opts = {}) {
  if (licenseOverlayForced && !opts.force) return;
  licenseOverlayForced = false;
  document.body.classList.remove("app-license-locked");
  const overlay = document.getElementById("license-overlay");
  overlay?.classList.add("hidden");
  overlay?.classList.remove("is-forced");
  if (licensePollTimer) {
    clearInterval(licensePollTimer);
    licensePollTimer = null;
  }
  resetLicensePaymentUi();
  setLicenseLog("");
}

function setLicenseLog(msg) {
  document.getElementById("license-log").textContent = msg || "";
}

function friendlyLicenseError(err) {
  const s = String(err ?? "");
  if (s.includes("<html") || s.includes("502") || s.includes("源站")) {
    return "创建订单失败：授权服务器暂时不可用(502)。请在服务器上测试本机 create-order，并查看 stderr.log。";
  }
  if (s.length > 240) return s.slice(0, 240) + "…";
  return s || "未知错误";
}

function planLabelZh(plan) {
  if (plan === "year") return "年付";
  if (plan === "month") return "月付";
  if (plan === "lifetime") return "终身";
  return plan || "—";
}

async function loadLicensePlans() {
  const box = document.getElementById("license-plans");
  box.innerHTML = "加载套餐…";
  try {
    const data = await api("/api/license/plans");
    box.innerHTML = "";
    for (const p of data.plans || []) {
      const btn = document.createElement("button");
      btn.type = "button";
      const planId = String(p.id || "").trim();
      const planClass = planId.replace(/[^a-z0-9_-]/gi, "") || "plan";
      btn.className = `license-plan-btn license-plan--${planClass}${p.lifetime ? " is-featured" : ""}`;
      btn.dataset.plan = planId;
      const term = p.lifetime ? "永久有效" : `${p.days} 天`;
      const price = Number(p.price);
      const priceText = Number.isFinite(price) ? (price % 1 === 0 ? price.toFixed(0) : price.toFixed(2)) : p.price;
      const badge = p.lifetime ? '<span class="license-plan-badge">推荐</span>' : "";
      btn.innerHTML = `
        ${badge}
        <span class="license-plan-name">${escHtml(p.name)}</span>
        <span class="license-plan-price"><span class="license-plan-currency">¥</span>${escHtml(String(priceText))}</span>
        <span class="license-plan-term">${escHtml(term)}</span>
      `;
      btn.addEventListener("click", () => {
        if (selectedLicensePlanId === planId && !document.getElementById("license-qr-wrap")?.classList.contains("hidden")) {
          return;
        }
        setLicensePlanSelection(planId);
        startLicenseOrder(p.id);
      });
      box.appendChild(btn);
    }
    if (!data.plans?.length) {
      box.innerHTML = '<p class="hint">未配置授权服务器</p>';
    }
  } catch (e) {
    box.innerHTML = `<p class="hint">${escHtml(String(e))}</p>`;
  }
}

function renderLicenseQr(qrUrl, orderId, amount) {
  const wrap = document.getElementById("license-qr-wrap");
  const qr = document.getElementById("license-qr");
  const meta = document.getElementById("license-order-meta");
  const mockBtn = document.getElementById("btn-license-mock-pay");
  wrap.classList.remove("hidden");
  meta.textContent = `订单 ${orderId} · ¥${amount}`;
  currentLicenseOrderId = orderId;
  if (qrUrl.startsWith("mock://")) {
    qr.innerHTML = '<p class="hint">开发模式：支付完成后点下方按钮</p>';
    mockBtn.classList.remove("hidden");
  } else {
    mockBtn.classList.add("hidden");
    qr.innerHTML = "";
    const isQrcodeImg =
      /url_qrcode|qrcode|\.png|\.jpg|\.jpeg|\.gif|\.webp/i.test(qrUrl) ||
      qrUrl.includes("xunhupay.com");
    if (isQrcodeImg) {
      const img = document.createElement("img");
      img.src = qrUrl;
      img.width = 200;
      img.height = 200;
      img.alt = "支付二维码";
      img.referrerPolicy = "no-referrer";
      qr.appendChild(img);
    } else {
      const hint = document.createElement("p");
      hint.className = "hint";
      hint.textContent = "请用微信「扫一扫」扫描下方二维码";
      qr.appendChild(hint);
      const img = document.createElement("img");
      img.width = 200;
      img.height = 200;
      img.alt = "支付二维码";
      img.src = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(qrUrl)}`;
      img.onerror = () => {
        hint.textContent = "二维码加载失败，请点击下方打开支付页";
        img.remove();
      };
      qr.appendChild(img);
      const openBtn = document.createElement("button");
      openBtn.type = "button";
      openBtn.className = "license-open-pay";
      openBtn.textContent = "打开支付页";
      openBtn.addEventListener("click", () => window.myknowledge?.openExternal?.(qrUrl));
      const row = document.createElement("p");
      row.className = "hint";
      row.appendChild(openBtn);
      qr.appendChild(row);
    }
  }
}

async function startLicenseOrder(plan) {
  setLicensePlanSelection(plan);
  setLicenseLog("正在创建订单…");
  try {
    if (licensePollTimer) {
      clearInterval(licensePollTimer);
      licensePollTimer = null;
    }
    const order = await api("/api/license/create-order", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan }),
    });
    renderLicenseQr(order.qr_url || "", order.order_id, order.amount);
    setLicenseLog("等待支付…");
    if (licensePollTimer) clearInterval(licensePollTimer);
    licensePollTimer = setInterval(() => pollLicenseOrder(order.order_id), 2500);
  } catch (e) {
    setLicenseLog(friendlyLicenseError(e));
  }
}

async function pollLicenseOrder(orderId) {
  try {
    const order = await api(`/api/license/order/${encodeURIComponent(orderId)}`);
    if (order.status === "paid" || order.token) {
      await api("/api/license/activate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ order_id: orderId }),
      });
      hideLicenseOverlay({ force: true });
      setLicenseLog("");
      await initApp();
    }
  } catch {
    /* keep polling */
  }
}

async function activateLicenseCode() {
  const code = document.getElementById("license-code-input").value.trim();
  if (!code) return uiInfo("请输入激活码");
  setLicenseLog("正在激活…");
  try {
    await api("/api/license/activate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    });
    hideLicenseOverlay({ force: true });
    await initApp();
  } catch (e) {
    setLicenseLog(String(e));
  }
}

document.getElementById("btn-license-code")?.addEventListener("click", activateLicenseCode);
document.getElementById("btn-license-close")?.addEventListener("click", () => hideLicenseOverlay());
document.getElementById("license-overlay")?.addEventListener("click", (e) => {
  if (e.target.id === "license-overlay") hideLicenseOverlay();
});
document.addEventListener("keydown", (e) => {
  const overlay = document.getElementById("license-overlay");
  if (e.key === "Escape" && overlay && !overlay.classList.contains("hidden")) {
    hideLicenseOverlay();
  }
});
document.getElementById("btn-license-mock-pay")?.addEventListener("click", async () => {
  if (!currentLicenseOrderId) return;
  setLicenseLog("模拟支付中…");
  try {
    await api("/api/license/mock-pay", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ order_id: currentLicenseOrderId }),
    });
    await pollLicenseOrder(currentLicenseOrderId);
  } catch (e) {
    setLicenseLog(String(e));
  }
});

function updateLicenseAbout(lic) {
  const el = document.getElementById("about-license");
  const actions = document.getElementById("about-license-actions");
  if (!el) return;
  if (!lic || lic.reason === "not_required") {
    el.textContent = "授权：开发模式（未启用订阅）";
    actions?.classList.add("hidden");
    return;
  }
  actions?.classList.remove("hidden");
  if (lic.reason === "trial") {
    el.textContent = `试用中 · 剩余 ${lic.trial_days_left ?? 0} 天（按自然日计，第 31 天起需订阅）`;
    return;
  }
  if (lic.licensed) {
    const planText = planLabelZh(lic.plan);
    if (lic.plan === "lifetime") {
      el.textContent = `订阅有效 · ${planText} · 永久有效`;
    } else {
      el.textContent = `订阅有效 · ${planText} · 到期 ${lic.expires_at || "—"}`;
    }
  } else {
    el.textContent = "未激活或已过期";
  }
}

async function refreshAboutLicense() {
  try {
    const lic = await api("/api/license/status");
    updateLicenseBanner(lic);
    updateLicenseAbout(lic);
    currentLicenseStatus = lic;
    return lic;
  } catch {
    return null;
  }
}

async function loadMaintenanceDrafts() {
  const meta = document.getElementById("maintenance-meta");
  const ul = document.getElementById("maintenance-draft-list");
  const selectAll = document.getElementById("maintenance-select-all");
  if (!ul) return;
  try {
    const data = await api("/api/maintenance/drafts?limit=50");
    maintenanceState.draftTotal = data.draft_total ?? 0;
    const shown = (data.items || []).length;
    if (meta) {
      let line = `${data.draft_total ?? 0} 篇草稿 · ${data.no_links_total ?? 0} 篇无链接`;
      if (shown < maintenanceState.draftTotal) {
        line += ` · 本页显示 ${shown} 条`;
      }
      meta.textContent = line;
    }
    ul.innerHTML = "";
    for (const item of data.items || []) {
      const li = document.createElement("li");
      li.className = "maintenance-draft-item";
      li.dataset.path = item.rel_path;
      li.innerHTML =
        `<label class="maintenance-draft-check" title="选中以便批量整理">` +
        `<input type="checkbox" class="draft-select" /></label>` +
        `<div class="maintenance-draft-body">` +
        `<strong>${escHtml(item.title)}</strong>` +
        `<small>${escHtml(item.rel_path)} · links ${item.links_count ?? 0}</small></div>` +
        `<div class="maintenance-draft-actions">` +
        `<button type="button" data-act="open">打开编辑</button>` +
        `<button type="button" data-act="refine">标为已整理</button></div>`;
      li.querySelector('[data-act="open"]')?.addEventListener("click", async (e) => {
        e.stopPropagation();
        try {
          await openMemoInEditor(item.rel_path);
        } catch (err) {
          uiError(err);
        }
      });
      li.querySelector('[data-act="refine"]')?.addEventListener("click", async (e) => {
        e.stopPropagation();
        await refineDraftPaths([item.rel_path], { confirmOne: item.title });
      });
      li.querySelector(".draft-select")?.addEventListener("change", syncMaintenanceSelectAll);
      ul.appendChild(li);
    }
    if (!data.items?.length) ul.innerHTML = '<li class="empty-item">暂无待整理草稿</li>';
    if (selectAll) selectAll.checked = false;
  } catch (e) {
    if (meta) meta.textContent = String(e);
  }
}

function getSelectedDraftPaths() {
  return [...document.querySelectorAll("#maintenance-draft-list .draft-select:checked")]
    .map((cb) => cb.closest("li")?.dataset.path)
    .filter(Boolean);
}

function syncMaintenanceSelectAll() {
  const selectAll = document.getElementById("maintenance-select-all");
  const boxes = [...document.querySelectorAll("#maintenance-draft-list .draft-select")];
  if (!selectAll || !boxes.length) {
    if (selectAll) selectAll.checked = false;
    return;
  }
  selectAll.checked = boxes.every((cb) => cb.checked);
  selectAll.indeterminate = !selectAll.checked && boxes.some((cb) => cb.checked);
}

function setMaintenanceBusy(on, text = "") {
  const meta = document.getElementById("maintenance-meta");
  const panel = document.getElementById("global-job-panel");
  const panelText = document.getElementById("global-job-panel-text");
  const panelFill = document.getElementById("global-job-panel-fill");
  const btnSel = document.getElementById("btn-maintenance-refine-selected");
  const btnAll = document.getElementById("btn-maintenance-refine-all");
  if (btnSel) btnSel.disabled = on;
  if (btnAll) btnAll.disabled = on;
  if (on) {
    if (meta) meta.textContent = text || "正在标为已整理…";
    panel?.classList.remove("hidden");
    if (panelText) panelText.textContent = text || "正在标为已整理…";
    if (panelFill) panelFill.style.width = "35%";
  } else {
    panel?.classList.add("hidden");
    if (panelFill) panelFill.style.width = "0";
  }
}

async function refineDraftPaths(paths, { confirmOne = "" } = {}) {
  const unique = [...new Set((paths || []).filter(Boolean))];
  if (!unique.length) {
    uiInfo("请先勾选要整理的条目");
    return null;
  }
  if (maintenanceState.busy) return null;
  let ok = true;
  if (confirmOne) {
    ok = await uiConfirm(`将「${confirmOne}」标为「已整理」？`);
  } else {
    ok = await uiConfirm(`将 ${unique.length} 篇标为「已整理」？`);
  }
  if (!ok) return null;
  maintenanceState.busy = true;
  setMaintenanceBusy(true, `正在标为已整理（${unique.length} 篇）…`);
  try {
    const result = await api("/api/maintenance/refine", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paths: unique }),
    });
    const n = result.refined_count ?? 0;
    const errN = (result.errors || []).length;
    if (n > 0) {
      window.YizhiToast?.success(`已标为已整理：${n} 篇（索引页后台更新中）`);
      refreshStatsLine();
    } else if (errN) {
      uiError(`整理失败 ${errN} 篇`);
    } else {
      uiInfo("所选条目已是「已整理」状态");
    }
    await loadMaintenanceDrafts();
    return result;
  } catch (e) {
    uiError(e);
    return null;
  } finally {
    maintenanceState.busy = false;
    setMaintenanceBusy(false);
  }
}

async function refineAllDrafts() {
  const total = maintenanceState.draftTotal;
  if (!total) {
    uiInfo("暂无待整理草稿");
    return;
  }
  if (maintenanceState.busy) return;
  const ok = await uiConfirm(
    `将全部 ${total} 篇草稿标为「已整理」？\n\n此操作会批量改状态，不会删除正文；建议仅用于已确认无需再改的条目。`
  );
  if (!ok) return;
  maintenanceState.busy = true;
  setMaintenanceBusy(true, `正在标为已整理（全部 ${total} 篇）…`);
  try {
    const result = await api("/api/maintenance/refine", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ all_drafts: true }),
    });
    const n = result.refined_count ?? 0;
    window.YizhiToast?.success(`已标为已整理：${n} 篇（索引页后台更新中）`);
    refreshStatsLine();
    await loadMaintenanceDrafts();
  } catch (e) {
    uiError(e);
  } finally {
    maintenanceState.busy = false;
    setMaintenanceBusy(false);
  }
}

async function loadCapabilities() {
  const ul = document.getElementById("capabilities-list");
  if (!ul) return;
  try {
    const data = await api("/api/capabilities");
    ul.innerHTML = "";
    for (const item of data.items || []) {
      const li = document.createElement("li");
      li.className = item.ok ? "cap-ok" : "cap-missing";
      li.innerHTML = `<strong>${escHtml(item.label)}</strong> — ${escHtml(item.detail)}<small>${escHtml(item.impact || "")}</small>`;
      ul.appendChild(li);
    }
  } catch {
    ul.innerHTML = "<li>无法加载能力检测</li>";
  }
}

async function setupOptionalTools() {
  const btn = document.getElementById("btn-setup-optional-tools");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "安装中…";
  }
  setSettingsFeedback("正在安装 ffmpeg / bun 等可选工具，请稍候…");
  try {
    const data = await api("/api/capabilities/setup-tools", { method: "POST" });
    await loadCapabilities();
    if (data.ok) {
      setSettingsFeedback("可选工具安装完成", "success");
    } else {
      setSettingsFeedback(data.output || "部分工具安装失败", "error");
    }
  } catch (e) {
    setSettingsFeedback(String(e), "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "一键修复可选工具";
    }
  }
}

async function initApp() {
  const reconnect = document.getElementById("reconnect-banner");
  try {
    reconnect?.classList.add("hidden");
    const lic = await api("/api/license/status");
    if (!applyLicenseUi(lic)) {
      setStatus("须订阅后使用");
      scheduleAutoUpdateCheckOnce();
      return;
    }
    const h = await api("/api/health");
    const s = await api("/api/stats");
    let extra = "";
    if (s.extra_dirs?.length) extra = ` · 外接文件夹 ${s.extra_dirs.length} 个`;
    setStatus(`${s.pages} 条笔记 · ${s.assets} 个文件${extra}`);
    window.YizhiJobs?.registerHandlers({
      onUploadDone: () => {
        refreshStatsLine();
        loadAssets();
        loadLibrary();
        window.YizhiToast?.success("文件后台处理完成");
      },
      onLinkedDone: () => {
        loadLinkedDirs();
        window.YizhiToast?.success("外联目录索引完成");
      },
      onIndexDone: () => {
        window.YizhiToast?.success("检索库更新完成");
      },
    });
    window.YizhiJobs?.startPolling();
    const urlJobs = await refreshUrlJobsActive();
    if (urlJobs.some((j) => j.status === "queued" || j.status === "running")) {
      trackUrlJobs(urlJobs[0]?.id);
    }
    window.YizhiOnboarding?.maybeAutoStart();
    scheduleAutoUpdateCheckOnce();
  } catch (e) {
    setStatus("未连上后台服务");
    reconnect?.classList.remove("hidden");
  }
}

document.getElementById("btn-reconnect")?.addEventListener("click", () => initApp());

initApp();

const aboutModal = document.getElementById("about-modal");
const textImportModal = document.getElementById("text-import-modal");
let textImportBusy = false;

function openAbout() {
  aboutModal.classList.remove("hidden");
  refreshAboutLicense();
  refreshAboutVersion();
  resetAboutUpdateStatus();
  loadCommercialLinks();
  const audio = document.getElementById("about-self-intro-audio");
  if (audio instanceof HTMLAudioElement) {
    audio.pause();
    audio.currentTime = 0;
    const btn = document.getElementById("btn-about-promo-audio");
    if (btn) btn.textContent = "自我介绍";
  }
}
function closeAbout() {
  aboutModal.classList.add("hidden");
  const audio = document.getElementById("about-self-intro-audio");
  if (audio instanceof HTMLAudioElement) {
    audio.pause();
    audio.currentTime = 0;
  }
  const btn = document.getElementById("btn-about-promo-audio");
  if (btn) btn.textContent = "自我介绍";
}

function refreshAboutVersion() {
  const el = document.getElementById("about-version");
  if (!el) return;
  const ver = window.myknowledge?.appVersion || "";
  el.textContent = ver ? `当前版本 ${ver}` : "";
}

function resetAboutUpdateStatus() {
  const status = document.getElementById("about-update-status");
  const dlBtn = document.getElementById("btn-about-download");
  if (status) {
    status.textContent = "";
    status.classList.add("hidden");
    status.classList.remove("is-error", "is-success");
  }
  dlBtn?.classList.add("hidden");
  if (dlBtn) dlBtn.dataset.url = "";
}

function setAboutUpdateStatus(message, kind = "") {
  const status = document.getElementById("about-update-status");
  if (!status) return;
  status.textContent = message || "";
  status.classList.toggle("hidden", !message);
  status.classList.toggle("is-error", kind === "error");
  status.classList.toggle("is-success", kind === "success");
}

let aboutUpdateDownloadUrl = "";
let commercialLinksCache = { purchase_url: "", faq_url: "", changelog_url: "" };

async function loadCommercialLinks() {
  try {
    commercialLinksCache = await api("/api/commercial/links");
  } catch {
    commercialLinksCache = {
      purchase_url: "https://www.yzwhysxx.cn/yizhi/purchase.html",
      faq_url: "https://www.yzwhysxx.cn/yizhi/faq.html",
      changelog_url: "https://www.yzwhysxx.cn/yizhi/changelog.html",
    };
  }
  return commercialLinksCache;
}

function openCommercialLink(key) {
  const url = commercialLinksCache[key];
  if (!url) return;
  window.myknowledge?.openExternal?.(url);
}

async function checkAboutUpdate() {
  const btn = document.getElementById("btn-about-check-update");
  const dlBtn = document.getElementById("btn-about-download");
  if (!btn) return;
  btn.disabled = true;
  aboutUpdateDownloadUrl = "";
  dlBtn?.classList.add("hidden");
  setAboutUpdateStatus("正在检查更新…");
  try {
    const appVersion = window.myknowledge?.appVersion || "";
    const data = await api(`/api/update/check?app_version=${encodeURIComponent(appVersion)}`);
    if (!data.ok) {
      setAboutUpdateStatus(data.message || "检查更新失败", "error");
      return;
    }
    let msg = data.message || "";
    if (data.release_notes) {
      msg = msg ? `${msg} · ${data.release_notes}` : data.release_notes;
    }
    if (data.current_recalled) {
      setAboutUpdateStatus(msg, "error");
      if (data.download_url && dlBtn) {
        aboutUpdateDownloadUrl = data.download_url;
        dlBtn.classList.remove("hidden");
      }
    } else if (data.update_available) {
      setAboutUpdateStatus(msg, "success");
      if (data.download_url && dlBtn) {
        aboutUpdateDownloadUrl = data.download_url;
        dlBtn.classList.remove("hidden");
      }
    } else {
      setAboutUpdateStatus(msg || "当前已是最新版本", "success");
    }
  } catch (e) {
    setAboutUpdateStatus(String(e), "error");
  } finally {
    btn.disabled = false;
  }
}

/** 本次进程只自动检查一次：有网且有新版才弹窗；无网/已最新静默。 */
let autoUpdateCheckDone = false;

function scheduleAutoUpdateCheckOnce() {
  if (autoUpdateCheckDone) return;
  window.setTimeout(() => {
    maybeAutoCheckUpdateOnce().catch(() => {});
  }, 2500);
}

async function maybeAutoCheckUpdateOnce() {
  if (autoUpdateCheckDone) return;
  autoUpdateCheckDone = true;
  try {
    const appVersion = window.myknowledge?.appVersion || "";
    const data = await api(`/api/update/check?app_version=${encodeURIComponent(appVersion)}`);
    if (!data?.ok) return;
    if (!data.update_available && !data.current_recalled) return;
    const latest = data.latest_version || "";
    const current = data.current_version || appVersion || "";
    const notes = String(data.release_notes || "").trim().slice(0, 240);
    let msg = data.current_recalled
      ? data.message || `当前版本 ${current} 已撤回，请升级到 ${latest}`
      : `发现新版本 ${latest}（当前 ${current}）。\n\n是否打开下载页？`;
    if (notes) msg += `\n\n${notes}`;
    const go = await (window.YizhiConfirm?.ask?.(msg, { title: "发现新版本" }) ??
      Promise.resolve(window.confirm(msg)));
    if (go && data.download_url) {
      window.myknowledge?.openExternal?.(data.download_url);
    }
  } catch {
    /* 无网络或更新源不可达：静默，不打扰 */
  }
}

function setTextImportBusy(busy, message) {
  textImportBusy = busy;
  const card = textImportModal?.querySelector(".modal-card-form");
  const busyEl = document.getElementById("text-import-busy");
  const busyText = document.getElementById("text-import-busy-text");
  const saveBtn = document.getElementById("btn-text-import");
  const cancelBtn = document.getElementById("btn-text-import-cancel");
  if (!card || !busyEl) return;
  card.classList.toggle("is-busy", busy);
  busyEl.classList.toggle("hidden", !busy);
  if (busyText && message) busyText.textContent = message;
  if (saveBtn) saveBtn.disabled = busy;
  if (cancelBtn) cancelBtn.disabled = busy;
}
function setTextImportFeedback(message, kind = "") {
  const el = document.getElementById("text-import-feedback");
  if (!el) return;
  el.textContent = message;
  el.classList.remove("hidden", "is-error", "is-success");
  if (!message) {
    el.classList.add("hidden");
    return;
  }
  if (kind === "error") el.classList.add("is-error");
  else if (kind === "success") el.classList.add("is-success");
}
function openTextImportModal() {
  setTextImportBusy(false);
  setTextImportFeedback("");
  textImportModal.classList.remove("hidden");
  document.getElementById("text-import-body")?.focus();
}
function closeTextImportModal(force = false) {
  if (textImportBusy && !force) return;
  textImportModal.classList.add("hidden");
  setTextImportBusy(false);
  setTextImportFeedback("");
  const saveBtn = document.getElementById("btn-text-import");
  if (saveBtn) saveBtn.textContent = "保存并加入检索";
}
document.getElementById("btn-open-text-import")?.addEventListener("click", openTextImportModal);
document.getElementById("btn-text-import-cancel")?.addEventListener("click", closeTextImportModal);
textImportModal?.querySelectorAll("[data-close-text-import]").forEach((el) => {
  el.addEventListener("click", closeTextImportModal);
});

const personaModal = document.getElementById("persona-modal");
let personaToneOptions = [];
let personaPrefOptions = [];
let personaApplyingPreset = false;

function setPersonaFeedback(msg, kind = "") {
  const el = document.getElementById("persona-feedback");
  if (!el) return;
  el.textContent = msg || "";
  el.classList.toggle("hidden", !msg);
  el.classList.toggle("is-error", kind === "error");
  el.classList.toggle("is-success", kind === "success");
}

function renderPersonaCheckboxes(containerId, options, selected) {
  const box = document.getElementById(containerId);
  if (!box) return;
  box.innerHTML = "";
  const sel = new Set(selected || []);
  for (const opt of options) {
    const lab = document.createElement("label");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = opt.id;
    cb.checked = sel.has(opt.id);
    lab.appendChild(cb);
    lab.appendChild(document.createTextNode(opt.label));
    box.appendChild(lab);
  }
}

function readPersonaCheckboxes(containerId) {
  const box = document.getElementById(containerId);
  if (!box) return [];
  return [...box.querySelectorAll('input[type="checkbox"]:checked')].map((el) => el.value);
}

function collectPersonaOwner() {
  return {
    real_name: document.getElementById("persona-owner-name")?.value.trim() || "",
    gender: document.getElementById("persona-owner-gender")?.value.trim() || "",
    nickname: document.getElementById("persona-owner-nickname")?.value.trim() || "",
    phone: document.getElementById("persona-owner-phone")?.value.trim() || "",
    email: document.getElementById("persona-owner-email")?.value.trim() || "",
    wechat: document.getElementById("persona-owner-wechat")?.value.trim() || "",
    avatar: document.getElementById("persona-avatar-preview")?.dataset.avatarPath || "",
    organization: document.getElementById("persona-owner-org")?.value.trim() || "",
    job_title: document.getElementById("persona-owner-title")?.value.trim() || "",
    aliases: document.getElementById("persona-owner-aliases")?.value.trim() || "",
    bio: document.getElementById("persona-owner-bio")?.value.trim() || "",
  };
}

function fillPersonaOwner(owner) {
  const o = owner || {};
  document.getElementById("persona-owner-name").value = o.real_name || "";
  document.getElementById("persona-owner-nickname").value = o.nickname || "";
  document.getElementById("persona-owner-gender").value = o.gender || "";
  document.getElementById("persona-owner-org").value = o.organization || "";
  document.getElementById("persona-owner-title").value = o.job_title || "";
  document.getElementById("persona-owner-phone").value = o.phone || "";
  document.getElementById("persona-owner-email").value = o.email || "";
  document.getElementById("persona-owner-wechat").value = o.wechat || "";
  document.getElementById("persona-owner-aliases").value = o.aliases || "";
  document.getElementById("persona-owner-bio").value = o.bio || "";
  const img = document.getElementById("persona-avatar-preview");
  if (img) img.dataset.avatarPath = o.avatar || "";
}

function setPersonaAvatarPreview(url, avatarPath) {
  const img = document.getElementById("persona-avatar-preview");
  if (!img) return;
  if (url) {
    img.src = url;
    img.classList.remove("hidden");
    if (avatarPath) img.dataset.avatarPath = avatarPath;
    return;
  }
  img.removeAttribute("src");
  img.classList.add("hidden");
  img.dataset.avatarPath = avatarPath || "";
}

function collectPersonaForm() {
  return {
    enabled: document.getElementById("persona-enabled")?.checked || false,
    owner: collectPersonaOwner(),
    preset: document.getElementById("persona-preset")?.value || "curator",
    role_name: document.getElementById("persona-role-name")?.value.trim() || "",
    role_intro: document.getElementById("persona-role-intro")?.value.trim() || "",
    audience: document.getElementById("persona-audience")?.value.trim() || "",
    domain: document.getElementById("persona-domain")?.value.trim() || "",
    tones: readPersonaCheckboxes("persona-tones"),
    preferences: readPersonaCheckboxes("persona-preferences"),
    custom_notes: document.getElementById("persona-custom-notes")?.value.trim() || "",
    keep_grounded_rules: document.getElementById("persona-grounded")?.checked !== false,
  };
}

function fillPersonaForm(cfg) {
  personaApplyingPreset = true;
  document.getElementById("persona-enabled").checked = !!cfg.enabled;
  document.getElementById("persona-preset").value = cfg.preset || "curator";
  document.getElementById("persona-role-name").value = cfg.role_name || "";
  document.getElementById("persona-role-intro").value = cfg.role_intro || "";
  document.getElementById("persona-audience").value = cfg.audience || "";
  document.getElementById("persona-domain").value = cfg.domain || "";
  document.getElementById("persona-custom-notes").value = cfg.custom_notes || "";
  document.getElementById("persona-grounded").checked = cfg.keep_grounded_rules !== false;
  fillPersonaOwner(cfg.owner || {});
  renderPersonaCheckboxes("persona-tones", personaToneOptions, cfg.tones);
  renderPersonaCheckboxes("persona-preferences", personaPrefOptions, cfg.preferences);
  syncPersonaFormState();
  personaApplyingPreset = false;
}

function syncPersonaFormState() {
  const enabled = document.getElementById("persona-enabled")?.checked;
  const fields = document.getElementById("persona-form-fields");
  if (fields) fields.classList.toggle("disabled", !enabled);
}

let activePersonaTab = "profile";

function switchPersonaTab(tabId) {
  activePersonaTab = tabId || "profile";
  document.querySelectorAll("#persona-tabs .modal-tab[data-persona-tab]").forEach((btn) => {
    const active = btn.dataset.personaTab === activePersonaTab;
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });
  document.querySelectorAll("#persona-form-fields .persona-panel[data-persona-tab]").forEach((panel) => {
    panel.classList.toggle("hidden", panel.dataset.personaTab !== activePersonaTab);
    panel.classList.toggle("is-active", panel.dataset.personaTab === activePersonaTab);
  });
}

function bindPersonaTabs() {
  const tabs = document.getElementById("persona-tabs");
  if (!tabs || tabs.dataset.bound) return;
  tabs.dataset.bound = "1";
  tabs.querySelectorAll(".modal-tab[data-persona-tab]").forEach((btn) => {
    btn.addEventListener("click", () => switchPersonaTab(btn.dataset.personaTab));
  });
}

async function openPersonaModal() {
  setPersonaFeedback("");
  switchPersonaTab("profile");
  personaModal?.classList.remove("hidden");
  try {
    const data = await api("/api/persona");
    personaToneOptions = data.tone_options || [];
    personaPrefOptions = data.preference_options || [];
    const genderSel = document.getElementById("persona-owner-gender");
    if (genderSel && genderSel.options.length === 0) {
      const blank = document.createElement("option");
      blank.value = "";
      blank.textContent = "（未设置）";
      genderSel.appendChild(blank);
      for (const g of data.gender_options || ["男", "女", "不愿透露", "其他"]) {
        const opt = document.createElement("option");
        opt.value = g;
        opt.textContent = g;
        genderSel.appendChild(opt);
      }
    }
    const presetSel = document.getElementById("persona-preset");
    if (presetSel && presetSel.options.length === 0) {
      for (const p of data.presets || []) {
        const opt = document.createElement("option");
        opt.value = p.id;
        opt.textContent = p.label;
        presetSel.appendChild(opt);
      }
    }
    fillPersonaForm(data.config || {});
    if (data.avatar_url) {
      setPersonaAvatarPreview(`${API}${data.avatar_url}?t=${Date.now()}`, data.config?.owner?.avatar || "");
    } else {
      setPersonaAvatarPreview("", "");
    }
    document.getElementById("persona-preview").value = data.rendered || "";
  } catch (e) {
    setPersonaFeedback(String(e), "error");
  }
}

function closePersonaModal() {
  personaModal?.classList.add("hidden");
  setPersonaFeedback("");
}

async function previewPersona() {
  const body = collectPersonaForm();
  try {
    const data = await api("/api/persona/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    document.getElementById("persona-preview").value = data.rendered || "（暂无预览内容）";
    switchPersonaTab("preview");
  } catch (e) {
    setPersonaFeedback(String(e), "error");
  }
}

async function savePersona() {
  const body = collectPersonaForm();
  try {
    const data = await api("/api/persona", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    document.getElementById("persona-preview").value = data.rendered || "";
    const ownerSaved = body.owner?.real_name || body.owner?.nickname;
    let msg = body.enabled ? "人设已保存，下次提问/推演时生效" : "已保存基本信息";
    if (ownerSaved) msg += "；「我」将关联到你本人";
    setPersonaFeedback(msg, "success");
    if (data.avatar_url) {
      setPersonaAvatarPreview(`${API}${data.avatar_url}?t=${Date.now()}`, data.config?.owner?.avatar || "");
    }
    setTimeout(closePersonaModal, 900);
  } catch (e) {
    setPersonaFeedback(String(e), "error");
  }
}

document.getElementById("btn-persona")?.addEventListener("click", openPersonaModal);
document.getElementById("btn-persona-cancel")?.addEventListener("click", closePersonaModal);
bindPersonaTabs();
document.getElementById("btn-persona-preview")?.addEventListener("click", previewPersona);
document.getElementById("btn-persona-save")?.addEventListener("click", savePersona);
document.getElementById("persona-enabled")?.addEventListener("change", syncPersonaFormState);
personaModal?.querySelectorAll("[data-close-persona]").forEach((el) => {
  el.addEventListener("click", closePersonaModal);
});
document.getElementById("persona-preset")?.addEventListener("change", async (e) => {
  if (personaApplyingPreset) return;
  const pid = e.target.value;
  if (pid === "custom") return;
  try {
    const data = await api(`/api/persona/preset/${encodeURIComponent(pid)}`);
    fillPersonaForm({ ...data.config, enabled: document.getElementById("persona-enabled")?.checked });
    await previewPersona();
  } catch (err) {
    setPersonaFeedback(String(err), "error");
  }
});
document.getElementById("btn-persona-reset")?.addEventListener("click", async () => {
  if (!(await uiConfirm("恢复为系统默认人设？将清除已保存的自定义配置（含基本信息）。"))) return;
  try {
    const data = await api("/api/persona/reset", { method: "POST" });
    fillPersonaForm(data.config || {});
    setPersonaAvatarPreview("", "");
    document.getElementById("persona-preview").value = "";
    setPersonaFeedback("已恢复默认", "success");
  } catch (e) {
    setPersonaFeedback(String(e), "error");
  }
});

document.getElementById("btn-persona-avatar-pick")?.addEventListener("click", () => {
  document.getElementById("persona-avatar-file")?.click();
});

document.getElementById("persona-avatar-file")?.addEventListener("change", async (e) => {
  const input = e.target;
  const file = input.files?.[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  try {
    setPersonaFeedback("正在上传头像…");
    const res = await fetch(`${API}/api/persona/avatar`, { method: "POST", body: fd });
    const text = await res.text();
    let j;
    try {
      j = JSON.parse(text);
    } catch {
      throw new Error(text.slice(0, 120));
    }
    if (!res.ok) throw new Error(j.detail || text.slice(0, 120));
    setPersonaAvatarPreview(`${API}${j.avatar_url}?t=${Date.now()}`, j.avatar || "");
    setPersonaFeedback("头像已更新", "success");
  } catch (err) {
    setPersonaFeedback(String(err), "error");
  } finally {
    input.value = "";
  }
});

const settingsModal = document.getElementById("settings-modal");
let settingsSnapshot = null;
let activeSettingsHelpPopover = null;

function closeSettingsHelpPopover() {
  if (activeSettingsHelpPopover) {
    activeSettingsHelpPopover.remove();
    activeSettingsHelpPopover = null;
  }
}

function positionSettingsHelpPopover(pop, anchor) {
  const pad = 8;
  const rect = anchor.getBoundingClientRect();
  pop.style.visibility = "hidden";
  pop.style.left = "0";
  pop.style.top = "0";
  document.body.appendChild(pop);
  const pw = pop.offsetWidth;
  const ph = pop.offsetHeight;
  let left = rect.left;
  let top = rect.bottom + 6;
  if (left + pw > window.innerWidth - pad) left = window.innerWidth - pw - pad;
  if (left < pad) left = pad;
  if (top + ph > window.innerHeight - pad) top = rect.top - ph - 6;
  if (top < pad) top = pad;
  pop.style.left = `${left}px`;
  pop.style.top = `${top}px`;
  pop.style.visibility = "visible";
}

function toggleSettingsHelpPopover(btn, text) {
  if (activeSettingsHelpPopover?.dataset.anchor === btn) {
    closeSettingsHelpPopover();
    return;
  }
  closeSettingsHelpPopover();
  const pop = document.createElement("div");
  pop.className = "settings-help-popover";
  pop.dataset.anchor = "1";
  pop.textContent = text;
  positionSettingsHelpPopover(pop, btn);
  activeSettingsHelpPopover = pop;
  btn.dataset.helpAnchor = "1";
}

document.addEventListener("click", (e) => {
  if (
    activeSettingsHelpPopover &&
    !e.target.closest(".settings-help-btn") &&
    !e.target.closest(".settings-help-popover")
  ) {
    closeSettingsHelpPopover();
  }
});

function appendSettingsLabel(parent, field) {
  const labelRow = document.createElement("div");
  labelRow.className = "settings-label-row";
  const label = document.createElement("span");
  label.textContent = field.label;
  labelRow.appendChild(label);
  if (field.help) {
    const helpBtn = document.createElement("button");
    helpBtn.type = "button";
    helpBtn.className = "settings-help-btn";
    helpBtn.setAttribute("aria-label", `${field.label}说明`);
    helpBtn.textContent = "?";
    helpBtn.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      toggleSettingsHelpPopover(helpBtn, field.help);
    });
    labelRow.appendChild(helpBtn);
  }
  parent.appendChild(labelRow);
  return labelRow;
}

function setSettingsFeedback(msg, kind = "") {
  const el = document.getElementById("settings-feedback");
  if (!el) return;
  el.textContent = msg || "";
  el.classList.toggle("hidden", !msg);
  el.classList.toggle("is-error", kind === "error");
  el.classList.toggle("is-success", kind === "success");
}

function renderSettingsTableRow(field) {
  const tr = document.createElement("tr");
  tr.className = "settings-field-row";
  tr.dataset.fieldKey = field.key;

  const labelTd = document.createElement("td");
  labelTd.className = "form-table-label settings-table-label";
  appendSettingsLabel(labelTd, field);
  tr.appendChild(labelTd);

  const controlTd = document.createElement("td");
  controlTd.className = "form-table-control settings-table-control";
  const id = `setting-${field.key}`;

  if (field.type === "bool") {
    const checkLabel = document.createElement("label");
    checkLabel.className = "settings-bool-control";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.id = id;
    input.dataset.key = field.key;
    input.dataset.type = "bool";
    input.checked = !!field.value;
    checkLabel.appendChild(input);
    const text = document.createElement("span");
    text.textContent = "开启";
    checkLabel.appendChild(text);
    controlTd.appendChild(checkLabel);
  } else if (field.type === "tts_voice") {
    const row = document.createElement("div");
    row.className = "settings-voice-row";
    const input = document.createElement("select");
    input.id = id;
    input.dataset.key = field.key;
    input.dataset.type = "tts_voice";
    for (const opt of field.options || []) {
      const o = document.createElement("option");
      o.value = opt.value;
      o.textContent = opt.label;
      input.appendChild(o);
    }
    input.value = String(field.value ?? "");
    const previewBtn = document.createElement("button");
    previewBtn.type = "button";
    previewBtn.className = "btn-tts-voice-preview";
    previewBtn.textContent = "试听";
    previewBtn.addEventListener("click", () => previewTtsVoice(input, previewBtn));
    row.appendChild(input);
    row.appendChild(previewBtn);
    controlTd.appendChild(row);
  } else {
    let input;
    if (field.type === "select") {
      input = document.createElement("select");
      input.id = id;
      input.dataset.key = field.key;
      input.dataset.type = "select";
      for (const opt of field.options || []) {
        const o = document.createElement("option");
        o.value = opt.value;
        o.textContent = opt.label;
        input.appendChild(o);
      }
      input.value = String(field.value ?? "");
    } else {
      input = document.createElement("input");
      input.id = id;
      input.dataset.key = field.key;
      input.dataset.type = field.type;
      if (field.type === "password") {
        input.type = "password";
        input.placeholder = field.placeholder || "留空则不修改";
        input.autocomplete = "off";
      } else if (field.type === "number") {
        input.type = "number";
        if (field.min != null) input.min = String(field.min);
        if (field.max != null) input.max = String(field.max);
        if (field.step != null) input.step = String(field.step);
      } else {
        input.type = "text";
        if (field.placeholder) input.placeholder = field.placeholder;
      }
      input.value = field.type === "password" ? "" : String(field.value ?? "");
    }
    controlTd.appendChild(input);
  }

  if (field.hint) {
    const hint = document.createElement("small");
    hint.className = "settings-hint form-table-hint";
    hint.textContent = field.hint;
    controlTd.appendChild(hint);
  }
  tr.appendChild(controlTd);
  return tr;
}

let activeSettingsTab = "capabilities";

const SETTINGS_TAB_SHORT = {
  capabilities: "能力",
  folders: "资料夹",
  llm: "大模型",
  memory: "记忆",
  rag: "RAG",
  style: "写作",
  ingest: "导入",
  docubrowser: "文档",
  tts: "播客",
  license: "授权",
  other: "其它",
  init: "初始化",
};

function settingsTabLabel(group) {
  return SETTINGS_TAB_SHORT[group.id] || group.label;
}

function switchSettingsTab(tabId) {
  activeSettingsTab = tabId || "capabilities";
  const form = document.getElementById("settings-form");
  if (!form) return;
  form.querySelectorAll(".modal-tab[data-tab]").forEach((btn) => {
    const active = btn.dataset.tab === activeSettingsTab;
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });
  form.querySelectorAll(".settings-panel[data-tab]").forEach((panel) => {
    panel.classList.toggle("hidden", panel.dataset.tab !== activeSettingsTab);
    panel.classList.toggle("is-active", panel.dataset.tab === activeSettingsTab);
  });
  if (activeSettingsTab === "folders") {
    loadFoldersManage().catch(() => {});
  }
  if (activeSettingsTab === "init") {
    loadWikiResetPanel().catch(() => {});
  }
}

function bindSettingsTabs() {
  const form = document.getElementById("settings-form");
  if (!form || form.dataset.tabsBound) return;
  form.dataset.tabsBound = "1";
  form.querySelectorAll(".modal-tab[data-tab]").forEach((btn) => {
    btn.addEventListener("click", () => switchSettingsTab(btn.dataset.tab));
  });
  switchSettingsTab(activeSettingsTab);
}

function renderSettingsForm(data) {
  const form = document.getElementById("settings-form");
  const note = document.getElementById("settings-note");
  if (!form) return;
  const prevTab = activeSettingsTab;
  form.innerHTML = "";
  form.dataset.tabsBound = "";
  if (note) note.textContent = data.note || "";
  settingsSnapshot = data;

  const tabs = document.createElement("nav");
  tabs.className = "modal-tabs settings-tabs";
  tabs.setAttribute("role", "tablist");
  tabs.setAttribute("aria-label", "设置分类");

  const panels = document.createElement("div");
  panels.className = "settings-panels";

  const tabDefs = [
    { id: "capabilities", label: "能力检测" },
    { id: "folders", label: "资料夹" },
    ...(data.groups || []),
    { id: "init", label: "初始化" },
  ];

  for (const group of tabDefs) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "modal-tab";
    btn.dataset.tab = group.id;
    btn.setAttribute("role", "tab");
    btn.textContent = settingsTabLabel(group);
    btn.title = group.label;
    tabs.appendChild(btn);

    const panel = document.createElement("section");
    panel.className = "settings-panel hidden";
    panel.dataset.tab = group.id;
    panel.setAttribute("role", "tabpanel");

    if (group.id === "capabilities") {
      const toolbar = document.createElement("div");
      toolbar.className = "capabilities-toolbar";
      const fixBtn = document.createElement("button");
      fixBtn.type = "button";
      fixBtn.id = "btn-setup-optional-tools";
      fixBtn.textContent = "一键修复可选工具";
      fixBtn.addEventListener("click", () => {
        setupOptionalTools().catch((e) => setSettingsFeedback(String(e), "error"));
      });
      toolbar.appendChild(fixBtn);
      const hint = document.createElement("p");
      hint.className = "capabilities-toolbar-hint hint";
      hint.textContent = "安装 ffmpeg、bun 与 baoyu-fetch，用于播客合并与网页/公众号抓取。";
      panel.appendChild(toolbar);
      panel.appendChild(hint);
      const ul = document.createElement("ul");
      ul.id = "capabilities-list";
      ul.className = "capabilities-list";
      panel.appendChild(ul);
    } else if (group.id === "folders") {
      const section = document.createElement("section");
      section.className = "folders-section settings-folders-panel";
      section.innerHTML =
        `<p class="hint">默认含「工作 / 学习 / 生活 / 阅读 / 归档」。笔记、闪念、上传与外联目录可多选归属；提问与写文章可按资料夹限定范围，不选则检索全部知识。</p>` +
        `<ul id="folders-list" class="folders-list"></ul>` +
        `<div class="row folders-add-row">` +
        `<input id="folder-name-input" type="text" placeholder="新资料夹名称" />` +
        `<button id="btn-folder-add" type="button" class="primary">添加</button>` +
        `</div>`;
      panel.appendChild(section);
      section.querySelector("#btn-folder-add")?.addEventListener("click", onFolderAddClick);
      section.querySelector("#folder-name-input")?.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          onFolderAddClick();
        }
      });
    } else if (group.id === "init") {
      const section = document.createElement("section");
      section.className = "settings-init-panel";
      section.id = "settings-init-panel";
      section.innerHTML =
        `<p class="hint">加载清空预览…</p>`;
      panel.appendChild(section);
    } else {
      const wrap = document.createElement("div");
      wrap.className = "form-table-wrap";
      const table = document.createElement("table");
      table.className = "form-table settings-table";
      const tbody = document.createElement("tbody");
      for (const field of group.fields || []) {
        tbody.appendChild(renderSettingsTableRow(field));
      }
      table.appendChild(tbody);
      wrap.appendChild(table);
      panel.appendChild(wrap);
      if (group.id === "llm") {
        const probeRow = document.createElement("div");
        probeRow.className = "row settings-llm-probe-row";
        probeRow.innerHTML =
          `<button type="button" id="btn-llm-probe" class="primary">测试连接</button>` +
          `<span id="llm-probe-result" class="hint"></span>`;
        panel.appendChild(probeRow);
        probeRow.querySelector("#btn-llm-probe")?.addEventListener("click", async () => {
          const out = document.getElementById("llm-probe-result");
          if (out) out.textContent = "测试中…";
          try {
            // 先保存当前表单，避免测的是旧 Key
            await saveSettingsForm();
            const r = await (window.YizhiServiceLoop?.probeAndMark?.() ||
              api("/api/llm/probe", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: "{}",
              }));
            if (out) {
              out.textContent = r.ok ? r.message || "连接成功" : r.error || "失败";
              out.classList.toggle("error-text", !r.ok);
            }
            setSettingsFeedback(r.ok ? "大模型连接正常" : r.error || "连接失败", r.ok ? "success" : "error");
          } catch (e) {
            if (out) out.textContent = String(e);
            setSettingsFeedback(String(e), "error");
          }
        });
      }
    }
    panels.appendChild(panel);
  }

  form.appendChild(tabs);
  form.appendChild(panels);
  bindSettingsTabs();
  switchSettingsTab(prevTab);
  bindTtsProviderChange();
  loadCapabilities();
  if (prevTab === "folders") loadFoldersManage().catch(() => {});
}

function collectSettingsValues() {
  const values = {};
  document.querySelectorAll("#settings-form [data-key]").forEach((el) => {
    const key = el.dataset.key;
    const type = el.dataset.type;
    if (type === "bool") values[key] = el.checked;
    else values[key] = el.value;
  });
  return values;
}

function currentTtsProviderFromForm() {
  return document.querySelector('#settings-form [data-key="MYKNOWLEDGE_TTS_PROVIDER"]')?.value || "";
}

async function refreshTtsVoiceOptions(provider) {
  const selects = document.querySelectorAll('#settings-form [data-type="tts_voice"]');
  if (!selects.length) return;
  for (const sel of selects) {
    const cur = sel.value;
    const data = await api(
      `/api/tts/voices?provider=${encodeURIComponent(provider || "")}&current=${encodeURIComponent(cur)}`
    );
    sel.innerHTML = "";
    for (const opt of data.options || []) {
      const o = document.createElement("option");
      o.value = opt.value;
      o.textContent = opt.label;
      sel.appendChild(o);
    }
    const values = (data.options || []).map((o) => o.value);
    sel.value = values.includes(cur) ? cur : values[0] || "";
  }
}

function bindTtsProviderChange() {
  const provEl = document.querySelector('#settings-form [data-key="MYKNOWLEDGE_TTS_PROVIDER"]');
  if (!provEl || provEl.dataset.ttsBound) return;
  provEl.dataset.ttsBound = "1";
  provEl.addEventListener("change", () => {
    refreshTtsVoiceOptions(provEl.value).catch((e) => setSettingsFeedback(String(e), "error"));
  });
}

let ttsPreviewAudio = null;

async function previewTtsVoice(selectEl, btn) {
  const voice = selectEl?.value;
  if (!voice) return;
  btn.disabled = true;
  btn.textContent = "试听中…";
  setSettingsFeedback("");
  try {
    const res = await fetch(`${API}/api/tts/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ voice, provider: currentTtsProviderFromForm() || undefined }),
    });
    if (!res.ok) {
      let msg = `试听失败（HTTP ${res.status}）`;
      try {
        const err = await res.json();
        msg = err.detail || msg;
      } catch {
        msg = (await res.text()) || msg;
      }
      throw new Error(msg);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    if (ttsPreviewAudio) {
      ttsPreviewAudio.pause();
      URL.revokeObjectURL(ttsPreviewAudio.src);
    }
    ttsPreviewAudio = new Audio(url);
    ttsPreviewAudio.onended = () => {
      URL.revokeObjectURL(url);
      if (ttsPreviewAudio?.src === url) ttsPreviewAudio = null;
    };
    await ttsPreviewAudio.play();
  } catch (e) {
    setSettingsFeedback(String(e), "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "试听";
  }
}

async function onFolderAddClick() {
  const input = document.getElementById("folder-name-input");
  const name = input?.value.trim();
  if (!name) return uiInfo("请输入资料夹名称");
  const btn = document.getElementById("btn-folder-add");
  if (btn) btn.disabled = true;
  try {
    const data = await api("/api/folders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    foldersCache = data.items || [];
    if (input) input.value = "";
    await renderFoldersManageList();
    refreshAllFolderChips();
    setStatus("资料夹已添加");
  } catch (e) {
    uiError(e);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function openSettingsModal() {
  setSettingsFeedback("");
  closeSettingsHelpPopover();
  settingsModal?.classList.remove("hidden");
  try {
    const data = await api("/api/settings");
    renderSettingsForm(data);
  } catch (e) {
    setSettingsFeedback(String(e), "error");
  }
}

function closeSettingsModal() {
  closeSettingsHelpPopover();
  settingsModal?.classList.add("hidden");
  setSettingsFeedback("");
}

async function loadWikiResetPanel() {
  const host = document.getElementById("settings-init-panel");
  if (!host) return;
  try {
    const p = await api("/api/wiki/reset/preview");
    const phrase = escHtml(p.confirm_phrase || "确认清空知识库");
    const dirs = (p.will_delete_dirs || []).map((x) => `<li><code>${escHtml(x)}</code></li>`).join("")
      || "<li>（暂无内容目录）</li>";
    const cfgs = (p.will_reset_config || []).map((x) => `<li><code>${escHtml(x)}</code></li>`).join("")
      || "<li>（无额外配置文件）</li>";
    const linked = (p.linked_external_paths_untouched || [])
      .map((x) => `<li><code>${escHtml(x)}</code></li>`)
      .join("") || "<li>（当前无外联登记）</li>";
    const preserved = (p.preserved || []).map((x) => `<li>${escHtml(x)}</li>`).join("");
    host.innerHTML =
      `<div class="settings-init-warn" role="alert">` +
      `<strong>危险操作 · 不可撤销</strong>` +
      `<p>${escHtml(p.disclaimer || "")}</p>` +
      `<p class="settings-init-path">知识库路径：<code>${escHtml(p.wiki_root || "")}</code></p>` +
      `</div>` +
      `<h4 class="settings-init-h">将删除 / 重置（知识库内）</h4>` +
      `<ul class="settings-init-list">${dirs}${cfgs}</ul>` +
      `<h4 class="settings-init-h">外联真实目录（只取消登记，不删磁盘文件）</h4>` +
      `<ul class="settings-init-list">${linked}</ul>` +
      `<h4 class="settings-init-h">保留</h4>` +
      `<ul class="settings-init-list">${preserved}</ul>` +
      `<label class="settings-init-check">` +
      `<input type="checkbox" id="wiki-reset-ack" />` +
      ` 我已阅读上述说明与免责，知悉外联外部文件不会被删除，并自行承担清空后果` +
      `</label>` +
      `<label class="settings-init-confirm-label">请输入确认语 <code>${phrase}</code></label>` +
      `<input type="text" id="wiki-reset-confirm" class="settings-init-confirm" autocomplete="off" spellcheck="false" />` +
      `<div class="row settings-init-actions">` +
      `<button type="button" id="btn-wiki-reset" class="danger">清空知识库</button>` +
      `</div>` +
      `<p id="wiki-reset-result" class="hint settings-init-result"></p>`;
    host.querySelector("#btn-wiki-reset")?.addEventListener("click", () => {
      runWikiReset().catch((e) => setSettingsFeedback(String(e), "error"));
    });
  } catch (e) {
    host.innerHTML = `<p class="hint error-text">无法加载预览：${escHtml(String(e))}</p>`;
  }
}

async function runWikiReset() {
  const ack = document.getElementById("wiki-reset-ack");
  const input = document.getElementById("wiki-reset-confirm");
  const resultEl = document.getElementById("wiki-reset-result");
  const btn = document.getElementById("btn-wiki-reset");
  if (!ack?.checked) {
    setSettingsFeedback("请先勾选风险确认", "error");
    return;
  }
  const confirm = (input?.value || "").trim();
  if (!confirm) {
    setSettingsFeedback("请输入确认语", "error");
    return;
  }
  if (
    !window.confirm(
      "最后确认：将清空知识库内全部用户资料（笔记、索引、记忆、外联登记等）。\n" +
        "外联指向的外部文件夹与文件不会删除。\n\n此操作不可撤销，是否继续？"
    )
  ) {
    return;
  }
  if (btn) btn.disabled = true;
  if (resultEl) resultEl.textContent = "正在清空…";
  try {
    const r = await api("/api/wiki/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirm, acknowledged: true }),
    });
    const msg = r.message || "已清空";
    if (resultEl) {
      resultEl.textContent =
        msg +
        (r.deleted?.length ? ` · 已处理 ${r.deleted.length} 项` : "") +
        (r.errors?.length ? ` · 失败 ${r.errors.length} 项` : "");
    }
    setSettingsFeedback(msg, r.ok === false ? "error" : "success");
    // 刷新列表/工作流等界面状态
    try {
      await loadFoldersManage();
    } catch {
      /* ignore */
    }
    try {
      await loadWikiResetPanel();
    } catch {
      /* ignore */
    }
  } catch (e) {
    if (resultEl) resultEl.textContent = String(e);
    setSettingsFeedback(String(e), "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function saveSettingsForm() {
  const values = collectSettingsValues();
  try {
    const data = await api("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values }),
    });
    renderSettingsForm(data);
    setSettingsFeedback("设置已保存并立即生效", "success");
    setTimeout(closeSettingsModal, 900);
  } catch (e) {
    setSettingsFeedback(String(e), "error");
  }
}

document.getElementById("btn-settings")?.addEventListener("click", openSettingsModal);
document.getElementById("btn-settings-cancel")?.addEventListener("click", closeSettingsModal);
document.getElementById("btn-settings-save")?.addEventListener("click", saveSettingsForm);
settingsModal?.querySelectorAll("[data-close-settings]").forEach((el) => {
  el.addEventListener("click", closeSettingsModal);
});

let feedbackEditorRec = null;
const feedbackModal = document.getElementById("feedback-modal");

function destroyFeedbackEditor() {
  if (feedbackEditorRec && window.YizhiRichEditor?.destroy) {
    try {
      window.YizhiRichEditor.destroy(feedbackEditorRec);
    } catch {
      /* ignore */
    }
  }
  feedbackEditorRec = null;
  const host = document.getElementById("feedback-editor-host");
  if (host) host.innerHTML = "";
}

function mountFeedbackEditor() {
  const host = document.getElementById("feedback-editor-host");
  if (!host) return;
  destroyFeedbackEditor();
  // 布局未完成时 clientHeight 可能为 0；保证正文区至少约半屏可写
  const measured = Math.floor(host.clientHeight || 0);
  const h = Math.max(280, measured || Math.floor(window.innerHeight * 0.42));
  if (window.YizhiRichEditor?.create) {
    feedbackEditorRec = window.YizhiRichEditor.create(host, {
      apiBase: typeof API !== "undefined" ? API : "",
      initialValue: "",
      height: `${h}px`,
      minHeight: "260px",
      compact: true,
      placeholder: "请尽量写清：操作步骤、期望结果、实际现象…",
    });
    // 弹窗 flex 定高后再贴齐宿主高度，避免只剩工具栏一条缝
    requestAnimationFrame(() => {
      const live = Math.max(260, Math.floor(host.clientHeight || h));
      try {
        feedbackEditorRec?.editor?.setHeight?.(`${live}px`);
      } catch {
        /* ignore */
      }
    });
  } else {
    const ta = document.createElement("textarea");
    ta.id = "feedback-fallback-ta";
    ta.style.cssText = `width:100%;min-height:${h}px;height:100%;box-sizing:border-box;padding:10px;resize:vertical;`;
    ta.placeholder = "请描述问题…";
    host.appendChild(ta);
    feedbackEditorRec = {
      el: host,
      editor: {
        getMarkdown: () => ta.value,
        getHTML: () => `<p>${String(ta.value || "").replace(/</g, "&lt;").replace(/\n/g, "<br>")}</p>`,
        setMarkdown: (v) => {
          ta.value = v || "";
        },
        destroy: () => ta.remove(),
      },
    };
  }
}

function getFeedbackHtml() {
  if (!feedbackEditorRec) return "";
  if (typeof feedbackEditorRec.editor?.getHTML === "function") {
    const html = String(feedbackEditorRec.editor.getHTML() || "").trim();
    if (html && html !== "<p><br></p>") return html;
  }
  const md = window.YizhiRichEditor?.getMarkdown
    ? window.YizhiRichEditor.getMarkdown(feedbackEditorRec)
    : feedbackEditorRec.editor?.getMarkdown?.() || "";
  if (!md.trim()) return "";
  if (window.YizhiRichEditor?.renderMarkdown) {
    return window.YizhiRichEditor.renderMarkdown(md);
  }
  return `<p>${escHtml(md).replace(/\n/g, "<br>")}</p>`;
}

function openFeedback() {
  if (!feedbackModal) return;
  feedbackModal.classList.remove("hidden");
  const status = document.getElementById("feedback-status");
  if (status) status.textContent = "";
  const subj = document.getElementById("feedback-subject");
  const contact = document.getElementById("feedback-contact");
  if (subj) subj.value = "";
  if (contact) contact.value = "";
  // 等弹窗布局完成后再量高挂载编辑器
  requestAnimationFrame(() => {
    requestAnimationFrame(() => mountFeedbackEditor());
  });
}

function closeFeedback() {
  feedbackModal?.classList.add("hidden");
  destroyFeedbackEditor();
}

async function submitFeedback() {
  const btn = document.getElementById("feedback-submit");
  const status = document.getElementById("feedback-status");
  const html = getFeedbackHtml();
  const plain = html.replace(/<[^>]+>/g, "").replace(/&nbsp;/g, " ").trim();
  if (plain.length < 5) {
    if (status) status.textContent = "请填写更具体的反馈内容";
    return;
  }
  if (btn) btn.disabled = true;
  if (status) status.textContent = "正在提交…";
  try {
    const r = await api("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        html,
        subject: document.getElementById("feedback-subject")?.value.trim() || "",
        contact: document.getElementById("feedback-contact")?.value.trim() || "",
      }),
    });
    if (r.sent) {
      if (r.mailed) {
        window.YizhiToast?.success?.("反馈已发送至邮箱，感谢！");
        if (status) status.textContent = "已发送邮件";
      } else {
        window.YizhiToast?.success?.("反馈已提交，邮件将稍后送达");
        if (status) {
          status.textContent = r.mail_error
            ? `已送达服务器（邮件待发：${r.mail_error}）`
            : "已送达服务器，邮件稍后发送";
        }
      }
      closeFeedback();
    } else {
      window.YizhiToast?.info?.("暂无网络，已保存到本地，联网后会自动发送");
      if (status) {
        status.textContent = r.error
          ? `已排队本地（${r.error}）。联网后自动重试。`
          : "已排队本地，联网后自动发送";
      }
      setTimeout(closeFeedback, 1400);
    }
  } catch (e) {
    if (status) status.textContent = String(e?.message || e);
    uiError(e);
  } finally {
    if (btn) btn.disabled = false;
  }
}

document.getElementById("btn-feedback")?.addEventListener("click", openFeedback);
document.getElementById("feedback-cancel")?.addEventListener("click", closeFeedback);
document.getElementById("feedback-submit")?.addEventListener("click", submitFeedback);
feedbackModal?.querySelectorAll("[data-close-feedback]").forEach((el) => {
  el.addEventListener("click", closeFeedback);
});

document.getElementById("btn-about").addEventListener("click", openAbout);
document.getElementById("btn-about-check-update")?.addEventListener("click", checkAboutUpdate);
document.getElementById("btn-about-purchase")?.addEventListener("click", () => openCommercialLink("purchase_url"));
document.getElementById("btn-about-faq")?.addEventListener("click", () => openCommercialLink("faq_url"));
document.getElementById("btn-about-changelog")?.addEventListener("click", () => openCommercialLink("changelog_url"));
document.getElementById("btn-about-download")?.addEventListener("click", () => {
  if (!aboutUpdateDownloadUrl) return;
  window.myknowledge?.openExternal?.(aboutUpdateDownloadUrl);
});
document.getElementById("btn-about-tour")?.addEventListener("click", () => {
  closeAbout();
  window.YizhiOnboarding?.restart();
});
document.getElementById("btn-about-promo-audio")?.addEventListener("click", async () => {
  const btn = document.getElementById("btn-about-promo-audio");
  const status = document.getElementById("about-promo-audio-status");
  const audio = document.getElementById("about-self-intro-audio");
  if (!(audio instanceof HTMLAudioElement)) {
    if (status) {
      status.textContent = "未找到自我介绍音频组件";
      status.classList.add("is-error");
    }
    return;
  }
  status?.classList.remove("hidden", "is-error", "is-success");
  try {
    if (!audio.paused) {
      audio.pause();
      if (btn) btn.textContent = "自我介绍";
      if (status) status.textContent = "已暂停";
      return;
    }
    // Restart from beginning each full play session after ended
    if (audio.ended || audio.currentTime > 0 && audio.paused && audio.currentTime >= audio.duration - 0.5) {
      audio.currentTime = 0;
    }
    if (audio.readyState < 2) {
      audio.load();
    }
    await audio.play();
    if (btn) btn.textContent = "暂停";
    if (status) {
      status.textContent = "正在播放预置自我介绍…";
      status.classList.add("is-success");
    }
    setStatus("正在播放自我介绍");
  } catch (e) {
    if (status) {
      status.textContent = `无法播放自我介绍音频：${e.message || e}`;
      status.classList.add("is-error");
    }
    window.YizhiToast?.show?.(String(e.message || e), { type: "error" });
  }
});
document.getElementById("about-self-intro-audio")?.addEventListener("ended", () => {
  const btn = document.getElementById("btn-about-promo-audio");
  const status = document.getElementById("about-promo-audio-status");
  if (btn) btn.textContent = "自我介绍";
  if (status) status.textContent = "播放完毕";
});
document.getElementById("about-self-intro-audio")?.addEventListener("pause", () => {
  const audio = document.getElementById("about-self-intro-audio");
  const btn = document.getElementById("btn-about-promo-audio");
  if (audio instanceof HTMLAudioElement && !audio.ended && btn) {
    btn.textContent = "自我介绍";
  }
});
document.getElementById("btn-about-renew")?.addEventListener("click", async () => {
  closeAbout();
  try {
    const lic = await api("/api/license/status");
    showLicenseOverlay(lic, { forced: false });
    await loadLicensePlans();
  } catch (e) {
    setLicenseLog(String(e));
  }
});
document.getElementById("btn-about-self-unbind")?.addEventListener("click", async () => {
  if (!(await uiConfirm("自助换机会解除本机绑定（每年限 1 次），之后需在新电脑重新激活。确定继续？"))) return;
  try {
    await api("/api/license/self-unbind", { method: "POST" });
    closeAbout();
    const lic = await api("/api/license/status");
    applyLicenseUi(lic);
    setStatus("已解绑，请在新设备激活");
  } catch (e) {
    uiError(e);
  }
});
document.getElementById("about-close").addEventListener("click", closeAbout);
aboutModal.querySelectorAll("[data-close-about]").forEach((el) => {
  el.addEventListener("click", closeAbout);
});

const scopeModal = document.getElementById("scope-modal");
let scopeDraft = new Set();

async function loadScopeOptions(filter = "") {
  const assetsUl = document.getElementById("scope-assets-list");
  const pagesUl = document.getElementById("scope-pages-list");
  if (!assetsUl || !pagesUl) return;
  const q = filter.trim().toLowerCase();
  assetsUl.innerHTML = "";
  pagesUl.innerHTML = "";
  try {
    const [assets, pages] = await Promise.all([
      api("/api/library/assets?page=1&size=80"),
      api("/api/pages?page=1&size=80"),
    ]);
    for (const a of assets.items || []) {
      const label = `${a.filename || a.rel_path}${a.wiki_page ? " → " + pathBasename(a.wiki_page) : ""}`;
      if (q && !label.toLowerCase().includes(q) && !(a.rel_path || "").toLowerCase().includes(q)) continue;
      const li = document.createElement("li");
      const labelEl = document.createElement("label");
      labelEl.className = "scope-item";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.dataset.path = a.rel_path;
      cb.checked = scopeDraft.has(a.rel_path);
      cb.addEventListener("change", () => {
        if (cb.checked) scopeDraft.add(a.rel_path);
        else scopeDraft.delete(a.rel_path);
      });
      const textSpan = document.createElement("span");
      textSpan.className = "scope-item-text";
      textSpan.textContent = label;
      textSpan.title = label;
      labelEl.append(cb, textSpan);
      li.appendChild(labelEl);
      assetsUl.appendChild(li);
    }
    for (const p of pages.items || []) {
      const label = p.title || p.rel_path;
      if (q && !label.toLowerCase().includes(q) && !(p.rel_path || "").toLowerCase().includes(q)) continue;
      const li = document.createElement("li");
      const labelEl = document.createElement("label");
      labelEl.className = "scope-item";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.dataset.path = p.rel_path;
      cb.checked = scopeDraft.has(p.rel_path);
      cb.addEventListener("change", () => {
        if (cb.checked) scopeDraft.add(p.rel_path);
        else scopeDraft.delete(p.rel_path);
      });
      const line = p.rel_path && p.rel_path !== label ? `${label} · ${p.rel_path}` : label;
      const textSpan = document.createElement("span");
      textSpan.className = "scope-item-text";
      textSpan.textContent = line;
      textSpan.title = line;
      labelEl.append(cb, textSpan);
      li.appendChild(labelEl);
      pagesUl.appendChild(li);
    }
  } catch (e) {
    assetsUl.innerHTML = `<li class="error">${escHtml(String(e))}</li>`;
  }
}

function openScopeModal() {
  scopeDraft = new Set(materialScopePaths);
  document.getElementById("scope-search").value = "";
  scopeModal?.classList.remove("hidden");
  loadScopeOptions();
}

function closeScopeModal() {
  scopeModal?.classList.add("hidden");
}

document.getElementById("ask-scope-enabled")?.addEventListener("change", refreshScopeSummary);
document.getElementById("btn-ask-scope")?.addEventListener("click", openScopeModal);
document.getElementById("btn-scope-cancel")?.addEventListener("click", closeScopeModal);
document.getElementById("btn-scope-clear")?.addEventListener("click", () => {
  scopeDraft.clear();
  loadScopeOptions(document.getElementById("scope-search")?.value || "");
});
scopeModal?.querySelectorAll("[data-close-scope]").forEach((el) => el.addEventListener("click", closeScopeModal));
document.getElementById("scope-search")?.addEventListener("input", (e) => loadScopeOptions(e.target.value));
document.getElementById("btn-scope-apply")?.addEventListener("click", () => {
  materialScopePaths = [...scopeDraft];
  if (materialScopePaths.length) {
    document.getElementById("ask-scope-enabled").checked = true;
  }
  refreshScopeSummary();
  closeScopeModal();
});

document.getElementById("ask-output")?.addEventListener("click", (e) => {
  const btn = e.target.closest(".cite-open");
  if (!btn) return;
  e.preventDefault();
  const path = btn.dataset.path;
  const page = parseInt(btn.dataset.page || btn.dataset.slide || "0", 10) || 0;
  openCiteSource(path, page);
});

document.getElementById("produce-podcast-dock")?.addEventListener("click", (e) => {
  const dl = e.target.closest(".btn-podcast-download-full");
  if (!dl) return;
  e.preventDefault();
  downloadPodcastFile(dl.dataset.path, dl.dataset.filename || "podcast.mp3").catch((err) => {
    uiError(err);
  });
});

document.getElementById("produce-confirm-panel")?.addEventListener("click", (e) => {
  if (!e.target.closest(".produce-confirm-all")) return;
  const panel = document.getElementById("produce-confirm-panel");
  const bar = panel?.querySelector(".produce-confirm-bar");
  const docKey = bar?.dataset.docKey;
  if (!docKey || !panel) return;
  const state = {};
  panel.querySelectorAll(".produce-confirm-check").forEach((c) => {
    c.checked = true;
    state[c.dataset.confirmId] = true;
    c.closest(".produce-confirm-item")?.classList.add("produce-confirm-done");
  });
  saveProduceConfirmState(docKey, state);
  updateProduceConfirmToolbar(panel);
});

document.getElementById("produce-confirm-panel")?.addEventListener("change", (e) => {
  const cb = e.target.closest(".produce-confirm-check");
  if (!cb) return;
  const panel = document.getElementById("produce-confirm-panel");
  const bar = panel?.querySelector(".produce-confirm-bar");
  const docKey = bar?.dataset.docKey;
  if (!docKey || !panel) return;
  const state = loadProduceConfirmState(docKey);
  state[cb.dataset.confirmId] = cb.checked;
  cb.closest(".produce-confirm-item")?.classList.toggle("produce-confirm-done", cb.checked);
  saveProduceConfirmState(docKey, state);
  updateProduceConfirmToolbar(panel);
});

document.getElementById("produce-output")?.addEventListener("click", (e) => {
  const cite = e.target.closest(".cite-open");
  if (!cite) return;
  e.preventDefault();
  openCiteSource(cite.dataset.path, parseInt(cite.dataset.page || cite.dataset.slide || "0", 10) || 0);
});

refreshScopeSummary();

const outputRulesModal = document.getElementById("output-rules-modal");

function openOutputRulesModal() {
  const qInput = document.getElementById("output-rules-question");
  const body = document.getElementById("output-rules-body");
  if (qInput) qInput.value = lastAskQuestion;
  if (body) {
    body.value = "";
    body.focus();
  }
  outputRulesModal?.classList.remove("hidden");
}

function closeOutputRulesModal() {
  outputRulesModal?.classList.add("hidden");
}

document.getElementById("btn-ask-write-rule")?.addEventListener("click", openOutputRulesModal);
document.getElementById("btn-output-rules-cancel")?.addEventListener("click", closeOutputRulesModal);
outputRulesModal?.querySelectorAll("[data-close-output-rules]").forEach((el) => {
  el.addEventListener("click", closeOutputRulesModal);
});
document.getElementById("btn-output-rules-save")?.addEventListener("click", async () => {
  const rule = document.getElementById("output-rules-body")?.value.trim();
  const question = document.getElementById("output-rules-question")?.value.trim() || lastAskQuestion;
  if (!rule) return uiInfo("请填写要追加的规则");
  const btn = document.getElementById("btn-output-rules-save");
  if (btn) btn.disabled = true;
  try {
    const r = await api("/api/output-rules", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rule, question }),
    });
    closeOutputRulesModal();
    const hint = document.getElementById("ask-feedback-hint");
    if (hint) {
      hint.textContent = `已写入输出规则（共 ${r.rules_count ?? "?"} 条）`;
    }
    setStatus("已追加输出规则");
  } catch (e) {
    uiError(e);
  } finally {
    if (btn) btn.disabled = false;
  }
});

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if (document.body.classList.contains("onboarding-active")) return;
  if (!textImportModal.classList.contains("hidden")) closeTextImportModal();
  else if (!personaModal?.classList.contains("hidden")) closePersonaModal();
  else if (!settingsModal?.classList.contains("hidden")) closeSettingsModal();
  else if (!scopeModal?.classList.contains("hidden")) closeScopeModal();
  else if (!outputRulesModal?.classList.contains("hidden")) closeOutputRulesModal();
  else if (!aboutModal.classList.contains("hidden")) closeAbout();
});

initMemoDatePicker();
initRichEditors();
loadFolders().then(refreshAllFolderChips).catch(() => {});

document.querySelectorAll(".manage-tab").forEach((btn) => {
  btn.addEventListener("click", () => setManageView(btn.dataset.manageView));
  btn.addEventListener("keydown", (e) => {
    const tabs = [...document.querySelectorAll(".manage-tab")];
    const i = tabs.indexOf(btn);
    if (e.key === "ArrowRight" && i < tabs.length - 1) {
      tabs[i + 1].focus();
      setManageView(tabs[i + 1].dataset.manageView);
    } else if (e.key === "ArrowLeft" && i > 0) {
      tabs[i - 1].focus();
      setManageView(tabs[i - 1].dataset.manageView);
    }
  });
});

document.getElementById("maintenance-select-all")?.addEventListener("change", (e) => {
  const on = e.target.checked;
  document.querySelectorAll("#maintenance-draft-list .draft-select").forEach((cb) => {
    cb.checked = on;
  });
  syncMaintenanceSelectAll();
});
document.getElementById("btn-maintenance-refine-selected")?.addEventListener("click", () => {
  void refineDraftPaths(getSelectedDraftPaths());
});
document.getElementById("btn-maintenance-refine-all")?.addEventListener("click", () => {
  void refineAllDrafts();
});
