/** 易知新手指引：高亮目标 + 浮动说明，首次进入自动播放。 */
(function () {
  // v5：Win64 安装说明 + 蒸馏预览确认；已完成 v4 的用户升级后再看一遍
  const STORAGE_KEY = "myk-onboarding-v6";

  const STEPS = [
    {
      id: "welcome",
      targets: [".tabs"],
      tooltipAnchor: ".tabs",
      title: "欢迎使用易知 3.0",
      text:
        "易知是本地优先的个人知识库：资料进库 → 有据问答 → 优质内容回写，库会越用越厚。3.0 起可用顶栏「本周服务进度」与「场景模板」形成服务闭环。回答只依据你导入的资料与笔记，没有依据不会乱编。当前安装包仅支持 Windows 64 位（x64）。",
    },
    {
      id: "platform",
      targets: [".tabs"],
      tooltipAnchor: ".tabs",
      title: "系统要求",
      text:
        "请确认本机为 Windows 64 位。安装包为 exe（官网下载多为 zip，需先解压）。若 SmartScreen 拦截，选「更多信息 → 仍要运行」；安装时请完成 VC++ 运行库步骤，否则可能无法启动。",
    },
    {
      id: "path",
      targets: [".tabs"],
      tooltipAnchor: ".tabs",
      title: "推荐使用线路",
      text:
        "① 导入资料（文件 / 网页 / B 站字幕 / 外联目录）或写笔记；②「提问」验证检索；③「写文章」产出定稿或播客音频；④ 需要时用「推演」「记忆与进化」。资料夹可把库分成工作/学习等范围。",
    },
    {
      id: "distill",
      tab: "manage",
      targets: ['.tab[data-tab="manage"]', "#workflow-grid"],
      tooltipAnchor: "#workflow-grid",
      title: "自我蒸馏",
      text:
        "知识库下会自动建 distill/ 四层。工作流「蒸馏本次产出」默认先预览；确认无误后在参数末行写「确认入库」再跑一次。提问页会显示引用的技能与原则；写文章也会优先贴合。",
    },
    {
      id: "manage",
      tab: "manage",
      targets: ['.tab[data-tab="manage"]', "#manage-view-import"],
      tooltipAnchor: "#manage-view-import",
      title: "第一步：导入资料",
      text:
        "上传 PDF/Office/音视频，粘贴文本，或「保存网页」（含 bilibili / b23 字幕入库）。「外联目录」只读索引本地文件夹，不必复制原文件。导入后记得看「待整理」与资料夹归属。",
    },
    {
      id: "list",
      tab: "list",
      targets: ['.tab[data-tab="list"]', "#memo-editor-host"],
      tooltipAnchor: "#memo-editor-host",
      title: "第二步：记笔记",
      text:
        "「时间线」用富文本记闪念（标题、列表、图片、#标签）；「编辑器」管理结构化笔记。没有现成文档时，从这里开始同样有效，并可归入资料夹。",
    },
    {
      id: "ask",
      tab: "ask",
      targets: ['.tab[data-tab="ask"]', "#ask-input"],
      tooltipAnchor: "#ask-input",
      title: "第三步：提问",
      text:
        "有资料后再提问。回答只引库内片段并带出处；可勾选「限定资料范围」按资料夹/文件收窄。答得好可自动归档，纠错可写入输出规则。",
    },
    {
      id: "continuity",
      tab: "ask",
      targets: ["#ask-continuity-bar"],
      tooltipAnchor: "#ask-continuity-bar",
      title: "续航与今日知签",
      text:
        "提问页上方可「继续上次」或「新开对话」。开启后还会看到「今日知签 / 库运势」（基于近几日真实使用统计的趣味宜忌），完整签册在「记忆与进化」里。",
    },
    {
      id: "query",
      tab: "query",
      targets: ['.tab[data-tab="query"]', "#query-input"],
      tooltipAnchor: "#query-input",
      title: "查询",
      text:
        "按关键词或语义搜索知识库。勾选「按意思找」走向量检索，适合记不清确切用词、只记得大概意思的场景。",
    },
    {
      id: "deduce",
      tab: "deduce",
      targets: ['.tab[data-tab="deduce"]', "#deduce-input"],
      tooltipAnchor: "#deduce-input",
      title: "推演",
      text:
        "基于本地库推可能走向：已知事实、可能走向、关键不确定因素、库内缺口，并配关系图。不是占卜，结论须能落到证据上；结果可下载保存。",
    },
    {
      id: "produce",
      tab: "produce",
      targets: ['.tab[data-tab="produce"]', "#produce-input"],
      tooltipAnchor: "#produce-input",
      title: "写文章与播客",
      text:
        "选体例生成草稿后可直接改、或填改稿要求让 AI 改；满意再「确认定稿」入库。播客对话稿可「合成播客音频」（双音色 TTS，合并完整文件，页内可播放下载）。页面整页滚动，编辑器随正文增高。",
    },
    {
      id: "memory",
      tab: "memory",
      targets: ['.tab[data-tab="memory"]', "#panel-memory"],
      tooltipAnchor: "#panel-memory",
      title: "记忆与进化",
      text:
        "跟踪规则、会话与审计；优质问答归档后库会变厚。「矛盾检测」对照核心假设扫描互相矛盾的表述并生成对照稿（不自动改笔记）。知签签册也在此查看。",
    },
    {
      id: "library",
      tab: "library",
      targets: ['.tab[data-tab="library"]', "#library-search"],
      tooltipAnchor: "#library-search",
      title: "资料库",
      text:
        "浏览已导入的原始文件与检索片段，可预览、下载、溯源。写作与问答引用的片段都能在这里找到对应来源。",
    },
    {
      id: "history",
      tab: "history",
      targets: ['.tab[data-tab="history"]', "#history-list"],
      tooltipAnchor: "#history-list",
      title: "历史",
      text:
        "查看以前的问答记录，选中后可「继续此会话」，回到提问页接着聊，上下文会保留。",
    },
    {
      id: "persona",
      targets: ["#btn-persona"],
      title: "人设",
      text:
        "自定义 AI 的角色、读者、语气与领域偏好。启用后提问与写文章会按人设表达，但仍须遵守「只许用库内事实」的硬性约束。",
    },
    {
      id: "settings",
      targets: ["#btn-settings"],
      title: "设置",
      text:
        "配置大模型、Embedding、TTS 音色、资料夹、外联目录自动刷新等。安装版大模型通常已预配置；资料夹可在此增删改。",
    },
    {
      id: "feedback",
      targets: ["#btn-feedback"],
      title: "意见反馈",
      text:
        "顶栏「反馈」可提交问题描述（支持富文本）。遇到异常时也可在「关于」里查看版本、检查更新与重新打开本指引。",
    },
    {
      id: "theme",
      targets: [".theme-switch", "#btn-about"],
      tooltipAnchor: ".theme-switch",
      title: "主题与关于",
      text:
        "可切换浅色/深色主题。点击「关于」查看版本与授权；可检查更新、打开购买说明 / 常见问题 / 更新记录，或重新播放新手指引。",
    },
    {
      id: "done",
      tab: "manage",
      targets: ['.tab[data-tab="manage"]', "#manage-view-import"],
      tooltipAnchor: "#manage-view-import",
      title: "开始第一步",
      text:
        "现在去「导入资料」上传一份 PDF（或保存一个网页），再到「提问」试一个问题；有积累后试试「写文章」或「推演」。祝你用得愉快！",
    },
  ];

  let root = null;
  let highlightEl = null;
  let tooltipEl = null;
  let stepIndex = 0;
  let active = false;
  let repositionTimer = null;

  function isDone() {
    return localStorage.getItem(STORAGE_KEY) === "1";
  }

  function markDone() {
    localStorage.setItem(STORAGE_KEY, "1");
  }

  function resetDone() {
    localStorage.removeItem(STORAGE_KEY);
  }

  function ensureDom() {
    if (root) return;
    root = document.createElement("div");
    root.id = "onboarding-root";
    root.className = "onboarding-root hidden";
    root.setAttribute("role", "dialog");
    root.setAttribute("aria-modal", "true");
    root.setAttribute("aria-labelledby", "onboarding-title");
    root.innerHTML =
      '<div class="onboarding-backdrop"></div>' +
      '<div class="onboarding-highlight" aria-hidden="true"></div>' +
      '<div class="onboarding-tooltip">' +
      '  <div class="onboarding-progress-track" aria-hidden="true">' +
      '    <span class="onboarding-progress-fill" id="onboarding-progress-fill"></span>' +
      "  </div>" +
      '  <div class="onboarding-tooltip-inner">' +
      '    <div class="onboarding-tooltip-head">' +
      '      <p class="onboarding-kicker" id="onboarding-kicker"></p>' +
      '      <button type="button" class="onboarding-close" data-onboarding-close aria-label="关闭">关闭</button>' +
      "    </div>" +
      '    <h2 class="onboarding-title" id="onboarding-title"></h2>' +
      '    <p class="onboarding-text" id="onboarding-text"></p>' +
      '    <div class="onboarding-actions">' +
      '      <button type="button" class="onboarding-skip" data-onboarding-skip>跳过</button>' +
      '      <span class="onboarding-progress" id="onboarding-progress"></span>' +
      '      <div class="onboarding-nav">' +
      '        <button type="button" class="onboarding-prev" data-onboarding-prev>上一步</button>' +
      '        <button type="button" class="primary onboarding-next" data-onboarding-next>下一步</button>' +
      "      </div>" +
      "    </div>" +
      "  </div>" +
      "</div>";
    document.body.appendChild(root);
    highlightEl = root.querySelector(".onboarding-highlight");
    tooltipEl = root.querySelector(".onboarding-tooltip");

    root.querySelector("[data-onboarding-next]")?.addEventListener("click", nextStep);
    root.querySelector("[data-onboarding-prev]")?.addEventListener("click", prevStep);
    root.querySelectorAll("[data-onboarding-skip]").forEach((el) => {
      el.addEventListener("click", finishTour);
    });
    root.querySelector("[data-onboarding-close]")?.addEventListener("click", finishTour);
  }

  function queryTargets(selectors) {
    if (!selectors?.length) return [];
    return selectors.map((sel) => document.querySelector(sel)).filter(Boolean);
  }

  function unionRect(nodes) {
    if (!nodes.length) return null;
    let top = Infinity;
    let left = Infinity;
    let right = -Infinity;
    let bottom = -Infinity;
    for (const node of nodes) {
      const r = node.getBoundingClientRect();
      if (r.width <= 0 && r.height <= 0) continue;
      top = Math.min(top, r.top);
      left = Math.min(left, r.left);
      right = Math.max(right, r.right);
      bottom = Math.max(bottom, r.bottom);
    }
    if (!Number.isFinite(top)) return null;
    const pad = 4;
    return {
      top: Math.max(0, top - pad),
      left: Math.max(0, left - pad),
      width: Math.min(window.innerWidth, right - left + pad * 2),
      height: Math.min(window.innerHeight, bottom - top + pad * 2),
    };
  }

  function applyHighlight(rect) {
    const backdrop = root.querySelector(".onboarding-backdrop");
    if (!rect) {
      highlightEl.classList.add("hidden");
      if (backdrop) backdrop.classList.remove("hidden");
      return;
    }
    highlightEl.classList.remove("hidden");
    if (backdrop) backdrop.classList.add("hidden");
    highlightEl.style.top = `${rect.top}px`;
    highlightEl.style.left = `${rect.left}px`;
    highlightEl.style.width = `${rect.width}px`;
    highlightEl.style.height = `${rect.height}px`;
    highlightEl.classList.remove("onboarding-highlight-enter");
    void highlightEl.offsetWidth;
    highlightEl.classList.add("onboarding-highlight-enter");
  }

  function measureTooltip() {
    return {
      width: tooltipEl.offsetWidth,
      height: tooltipEl.offsetHeight,
    };
  }

  function applyTooltipPosition(top, left) {
    tooltipEl.style.top = `${top}px`;
    tooltipEl.style.left = `${left}px`;
    tooltipEl.style.right = "auto";
    tooltipEl.style.bottom = "auto";
    tooltipEl.classList.remove("onboarding-tooltip-enter");
    void tooltipEl.offsetWidth;
    tooltipEl.classList.add("onboarding-tooltip-enter");
  }

  /** 操作提示层固定于窗口中心偏右下，不随高亮目标移动。 */
  function placeTooltip() {
    const pad = 24;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const { width: tipW, height: tipH } = measureTooltip();
    const left = clamp(vw * 0.58 - tipW / 2, pad, vw - tipW - pad);
    const top = clamp(vh * 0.62 - tipH / 2, pad, vh - tipH - pad);
    applyTooltipPosition(top, left);
  }

  function clamp(v, min, max) {
    return Math.min(max, Math.max(min, v));
  }

  function switchTabIfNeeded(tab) {
    if (!tab) return;
    if (typeof window.switchTab === "function") {
      window.switchTab(tab);
      return;
    }
    document.querySelectorAll(".tab").forEach((t) => {
      t.classList.toggle("active", t.dataset.tab === tab);
    });
    document.querySelectorAll(".panel").forEach((p) => {
      p.classList.toggle("active", p.id === `panel-${tab}`);
    });
  }

  function renderStep() {
    const step = STEPS[stepIndex];
    if (!step) return;

    switchTabIfNeeded(step.tab);

    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        const nodes = queryTargets(step.targets);
        const rect = nodes.length ? unionRect(nodes) : null;
        applyHighlight(rect);

        const kicker = root.querySelector("#onboarding-kicker");
        const title = root.querySelector("#onboarding-title");
        const text = root.querySelector("#onboarding-text");
        const progress = document.getElementById("onboarding-progress");
        const progressFill = document.getElementById("onboarding-progress-fill");
        const prevBtn = root.querySelector("[data-onboarding-prev]");
        const nextBtn = root.querySelector("[data-onboarding-next]");

        if (kicker) {
          kicker.textContent = step.id === "welcome" ? "新手指引" : `第 ${stepIndex + 1} / ${STEPS.length} 步`;
        }
        if (title) title.textContent = step.title;
        if (text) text.textContent = step.text;
        if (progress) progress.textContent = `${stepIndex + 1} / ${STEPS.length}`;
        if (progressFill) {
          progressFill.style.width = `${((stepIndex + 1) / STEPS.length) * 100}%`;
        }
        if (prevBtn) prevBtn.disabled = stepIndex === 0;
        if (nextBtn) {
          nextBtn.textContent = stepIndex >= STEPS.length - 1 ? "开始导入" : "下一步";
        }

        placeTooltip();
        window.requestAnimationFrame(() => placeTooltip());
      });
    });
  }

  function scheduleReposition() {
    if (!active) return;
    if (repositionTimer) window.clearTimeout(repositionTimer);
    repositionTimer = window.setTimeout(() => renderStep(), 80);
  }

  function bindViewport() {
    window.addEventListener("resize", scheduleReposition);
    window.addEventListener("scroll", scheduleReposition, true);
  }

  function unbindViewport() {
    window.removeEventListener("resize", scheduleReposition);
    window.removeEventListener("scroll", scheduleReposition, true);
    if (repositionTimer) {
      window.clearTimeout(repositionTimer);
      repositionTimer = null;
    }
  }

  function startTour(options = {}) {
    if (active) return;
    if (document.getElementById("license-overlay") && !document.getElementById("license-overlay").classList.contains("hidden")) {
      return;
    }
    ensureDom();
    active = true;
    stepIndex = 0;
    root.classList.remove("hidden");
    document.body.classList.add("onboarding-active");
    bindViewport();
    renderStep();
    if (options.force) resetDone();
  }

  function finishTour() {
    if (!active) return;
    active = false;
    markDone();
    unbindViewport();
    root?.classList.add("hidden");
    document.body.classList.remove("onboarding-active");
    applyHighlight(null);
    root?.querySelector(".onboarding-backdrop")?.classList.remove("hidden");
    if (typeof window.switchTab === "function") window.switchTab("manage");
  }

  function nextStep() {
    if (stepIndex >= STEPS.length - 1) {
      finishTour();
      return;
    }
    stepIndex += 1;
    renderStep();
  }

  function prevStep() {
    if (stepIndex <= 0) return;
    stepIndex -= 1;
    renderStep();
  }

  function maybeAutoStart() {
    if (isDone()) return;
    window.setTimeout(() => startTour(), 400);
  }

  window.YizhiOnboarding = {
    start: startTour,
    restart: () => {
      resetDone();
      startTour({ force: true });
    },
    maybeAutoStart,
    isDone,
  };

  document.addEventListener("keydown", (e) => {
    if (!active || e.key !== "Escape") return;
    e.stopPropagation();
    finishTour();
  });
})();
