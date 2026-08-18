/** Global toast notifications + task history for 易知 */
(function () {
  const MAX_HISTORY = 8;
  const history = [];

  function stackEl() {
    return document.getElementById("toast-stack");
  }

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = String(s ?? "");
    return d.innerHTML;
  }

  function addHistory(entry) {
    history.unshift(entry);
    if (history.length > MAX_HISTORY) history.pop();
    document.dispatchEvent(new CustomEvent("yizhi-task-history", { detail: history.slice() }));
  }

  function show(message, kind = "info", durationMs = 4500) {
    const stack = stackEl();
    if (!stack || !message) return;
    const el = document.createElement("div");
    el.className = `toast toast-${kind}`;
    el.setAttribute("role", "status");
    el.innerHTML = `<span class="toast-text">${esc(message)}</span>`;
    stack.appendChild(el);
    requestAnimationFrame(() => el.classList.add("toast-visible"));
    const remove = () => {
      el.classList.remove("toast-visible");
      window.setTimeout(() => el.remove(), 280);
    };
    window.setTimeout(remove, durationMs);
    addHistory({ message, kind, at: new Date().toISOString() });
  }

  window.YizhiToast = {
    show,
    success: (msg, ms) => show(msg, "success", ms),
    error: (msg, ms) => show(msg, "error", ms ?? 7000),
    info: (msg, ms) => show(msg, "info", ms),
    getHistory: () => history.slice(),
  };
})();
