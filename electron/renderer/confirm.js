/** Non-blocking confirm dialog (replaces window.confirm for desktop UX). */
(function () {
  let modal;
  let msgEl;
  let resolver = null;

  function ensureDom() {
    if (modal) return;
    modal = document.getElementById("confirm-modal");
    msgEl = document.getElementById("confirm-modal-message");
    document.getElementById("confirm-modal-ok")?.addEventListener("click", () => finish(true));
    document.getElementById("confirm-modal-cancel")?.addEventListener("click", () => finish(false));
    modal?.querySelector("[data-close-confirm]")?.addEventListener("click", () => finish(false));
  }

  function finish(ok) {
    modal?.classList.add("hidden");
    if (resolver) {
      const r = resolver;
      resolver = null;
      r(ok);
    }
  }

  function ask(message, { title = "请确认" } = {}) {
    ensureDom();
    if (!modal || !msgEl) return Promise.resolve(window.confirm(message));
    if (resolver) finish(false);
    const titleEl = document.getElementById("confirm-modal-title");
    if (titleEl) titleEl.textContent = title;
    msgEl.textContent = message;
    modal.classList.remove("hidden");
    const okBtn = document.getElementById("confirm-modal-ok");
    okBtn?.focus();
    return new Promise((resolve) => {
      resolver = resolve;
    });
  }

  document.addEventListener("keydown", (e) => {
    if (!modal || modal.classList.contains("hidden") || !resolver) return;
    if (e.key === "Escape") {
      e.preventDefault();
      finish(false);
    } else if (e.key === "Enter") {
      e.preventDefault();
      finish(true);
    }
  });

  window.YizhiConfirm = { ask };
})();
