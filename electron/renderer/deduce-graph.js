/** Force-directed graph for deduce (推演) panel. Requires global d3 from vendor/d3/d3.min.js */
(function () {
  let simulation = null;
  let resizeObserver = null;
  let resizeTimer = null;
  let windowResizeHandler = null;
  /** @type {{ container, graph, onNodeClick, onReady, key, width, height, svg, zoom, g, fitted } | null} */
  let lastRender = null;

  function stopSimulation() {
    if (simulation) {
      simulation.stop();
      simulation = null;
    }
  }

  function disconnectResize() {
    if (resizeObserver) {
      resizeObserver.disconnect();
      resizeObserver = null;
    }
    if (resizeTimer) {
      clearTimeout(resizeTimer);
      resizeTimer = null;
    }
    if (windowResizeHandler) {
      window.removeEventListener("resize", windowResizeHandler);
      windowResizeHandler = null;
    }
  }

  function graphKey(graph) {
    const nodes = (graph && graph.nodes) || [];
    const edges = (graph && graph.edges) || [];
    return JSON.stringify({
      n: nodes.map((x) => x.id).sort(),
      e: edges.map((x) => `${x.source}|${x.target}|${x.label || ""}`).sort(),
    });
  }

  function measure(container) {
    const rect = container.getBoundingClientRect();
    return {
      width: Math.max(Math.floor(rect.width) || 0, 0),
      height: Math.max(Math.floor(rect.height) || 0, 0),
    };
  }

  function nodeRadius(d) {
    return d && d.seed ? 10 : 7;
  }

  function linkEndpoints(d) {
    const sx = d.source.x;
    const sy = d.source.y;
    const tx = d.target.x;
    const ty = d.target.y;
    const dx = tx - sx;
    const dy = ty - sy;
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
    const sr = nodeRadius(d.source);
    const tr = nodeRadius(d.target);
    const arrowPad = 14;
    return {
      x1: sx + (dx / dist) * (sr + 2),
      y1: sy + (dy / dist) * (sr + 2),
      x2: tx - (dx / dist) * (tr + arrowPad),
      y2: ty - (dy / dist) * (tr + arrowPad),
      mx: sx + dx * 0.5,
      my: sy + dy * 0.5,
    };
  }

  function truncateLabel(text, maxLen) {
    const s = String(text || "");
    return s.length > maxLen ? `${s.slice(0, maxLen - 1)}…` : s;
  }

  function fitGraphToView(svg, zoom, g, width, height, padding) {
    const pad = padding == null ? 36 : padding;
    try {
      const bounds = g.node().getBBox();
      if (!bounds.width || !bounds.height) return false;
      const scale = Math.min(
        3,
        0.9 / Math.max((bounds.width + pad * 2) / width, (bounds.height + pad * 2) / height)
      );
      const midX = bounds.x + bounds.width / 2;
      const midY = bounds.y + bounds.height / 2;
      const transform = d3.zoomIdentity
        .translate(width / 2, height / 2)
        .scale(scale)
        .translate(-midX, -midY);
      svg.call(zoom.transform, transform);
      return true;
    } catch {
      return false;
    }
  }

  function initNodePositions(nodes, width, height) {
    const n = nodes.length;
    const r = Math.min(width, height) * 0.32;
    nodes.forEach((node, i) => {
      const angle = (i / Math.max(n, 1)) * Math.PI * 2;
      node.x = width / 2 + r * Math.cos(angle);
      node.y = height / 2 + r * Math.sin(angle);
    });
  }

  function inlineSvgStyles(svg) {
    svg.querySelectorAll("circle").forEach((el) => {
      const fill = el.getAttribute("fill") || "";
      if (fill.includes("accent") || fill.includes("2563eb")) el.setAttribute("fill", "#2563eb");
      else if (fill.includes("var(")) el.setAttribute("fill", "#64748b");
    });
    svg.querySelectorAll("text").forEach((el) => {
      if ((el.getAttribute("fill") || "").includes("var(")) el.setAttribute("fill", "#0f172a");
    });
    svg.querySelectorAll("line.link-arrow").forEach((el) => {
      el.setAttribute("stroke", "#94a3b8");
    });
    svg.querySelectorAll("marker path").forEach((el) => {
      el.setAttribute("fill", "#94a3b8");
    });
    svg.querySelectorAll(".link-label").forEach((el) => {
      el.setAttribute("fill", "#475569");
    });
  }

  function resizeInPlace() {
    if (!lastRender || !lastRender.svg || !lastRender.g) return;
    const { width, height } = measure(lastRender.container);
    if (width < 80 || height < 80) return;
    if (
      Math.abs(width - lastRender.width) < 2 &&
      Math.abs(height - lastRender.height) < 2
    ) {
      return;
    }
    lastRender.width = width;
    lastRender.height = height;
    lastRender.svg.attr("width", width).attr("height", height);
    if (simulation) {
      simulation.force("center", d3.forceCenter(width / 2, height / 2));
      simulation.alpha(0.12).restart();
    }
    fitGraphToView(lastRender.svg, lastRender.zoom, lastRender.g, width, height);
  }

  function scheduleResizeCheck() {
    if (resizeTimer) clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(() => {
      resizeTimer = null;
      resizeInPlace();
    }, 120);
  }

  function attachResizeObserver(container) {
    if (typeof ResizeObserver !== "undefined") {
      if (!resizeObserver) {
        resizeObserver = new ResizeObserver(scheduleResizeCheck);
      }
      resizeObserver.disconnect();
      resizeObserver.observe(container);
      const wrap = container.closest(".deduce-result-graph-wrap");
      if (wrap && wrap !== container) {
        resizeObserver.observe(wrap);
      }
    }
    if (!windowResizeHandler) {
      windowResizeHandler = () => scheduleResizeCheck();
      window.addEventListener("resize", windowResizeHandler);
    }
  }

  function render(container, graph, onNodeClick, onReady) {
    if (!container) return;

    const key = graphKey(graph || {});
    const nodes = (graph && graph.nodes) || [];
    const edges = (graph && graph.edges) || [];

    if (
      lastRender &&
      lastRender.container === container &&
      lastRender.key === key &&
      container.querySelector("svg")
    ) {
      resizeInPlace();
      if (typeof onReady === "function") onReady();
      return;
    }

    disconnectResize();
    stopSimulation();
    lastRender = null;
    container.innerHTML = "";

    if (!nodes.length) {
      container.innerHTML = '<p class="hint deduce-graph-empty">暂无关联节点，请先导入资料并建立链接。</p>';
      if (typeof onReady === "function") onReady();
      return;
    }
    if (typeof d3 === "undefined") {
      container.innerHTML = '<p class="hint deduce-graph-empty">关系图组件未加载。</p>';
      if (typeof onReady === "function") onReady();
      return;
    }

    let { width, height } = measure(container);
    if (width < 80 || height < 80) {
      window.requestAnimationFrame(() => render(container, graph, onNodeClick, onReady));
      return;
    }

    const svg = d3
      .select(container)
      .append("svg")
      .attr("width", width)
      .attr("height", height)
      .attr("role", "img")
      .attr("aria-label", "推演关系图");

    const g = svg.append("g");
    const zoom = d3.zoom().scaleExtent([0.15, 4]).on("zoom", (ev) => {
      g.attr("transform", ev.transform);
    });
    svg.call(zoom);

    svg
      .append("defs")
      .append("marker")
      .attr("id", "deduce-arrow")
      .attr("viewBox", "0 -4 8 8")
      .attr("refX", 8)
      .attr("refY", 0)
      .attr("markerWidth", 7)
      .attr("markerHeight", 7)
      .attr("orient", "auto")
      .append("path")
      .attr("d", "M0,-4L8,0L0,4")
      .attr("fill", "#94a3b8");

    const nodeById = new Map(nodes.map((n) => [n.id, { ...n }]));
    const links = edges
      .map((e) => ({
        source: nodeById.get(e.source) || e.source,
        target: nodeById.get(e.target) || e.target,
        label: e.label || "",
        source_type: e.source_type || "wiki",
        strength: e.strength || "中",
      }))
      .filter((l) => l.source && l.target);
    const simNodes = [...nodeById.values()];
    initNodePositions(simNodes, width, height);

    const link = g
      .append("g")
      .attr("class", "deduce-links")
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("class", "link-arrow")
      .attr("stroke", (d) => (d.source_type === "inferred" ? "#2563eb" : "#94a3b8"))
      .attr("stroke-opacity", (d) => (d.strength === "弱" ? 0.55 : 0.9))
      .attr("stroke-width", (d) => (d.strength === "强" ? 2.2 : 1.5))
      .attr("stroke-dasharray", (d) => (d.source_type === "wiki" ? "4 3" : null))
      .attr("marker-end", "url(#deduce-arrow)");

    const linkLabel = g
      .append("g")
      .attr("class", "deduce-link-labels")
      .selectAll("text")
      .data(links.filter((l) => l.label))
      .join("text")
      .attr("class", "link-label")
      .attr("text-anchor", "middle")
      .attr("font-size", "10px")
      .attr("fill", "#475569")
      .attr("pointer-events", "none")
      .text((d) => truncateLabel(d.label, 10));

    const node = g
      .append("g")
      .selectAll("g")
      .data(simNodes)
      .join("g")
      .attr("cursor", "pointer")
      .attr("transform", (d) => `translate(${d.x},${d.y})`)
      .call(
        d3
          .drag()
          .on("start", (ev, d) => {
            if (!ev.active) simulation.alphaTarget(0.25).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on("drag", (ev, d) => {
            d.fx = ev.x;
            d.fy = ev.y;
          })
          .on("end", (ev, d) => {
            if (!ev.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          })
      );

    node
      .append("circle")
      .attr("r", (d) => (d.seed ? 10 : 7))
      .attr("fill", (d) => (d.seed ? "#2563eb" : "#64748b"));

    node
      .append("text")
      .text((d) => truncateLabel(d.title || d.id, 18))
      .attr("x", 12)
      .attr("y", 4)
      .attr("font-size", "11px")
      .attr("fill", "#0f172a");

    node.on("click", (ev, d) => {
      ev.stopPropagation();
      if (typeof onNodeClick === "function") onNodeClick(d.id);
    });

    lastRender = {
      container,
      graph,
      onNodeClick,
      onReady,
      key,
      width,
      height,
      svg,
      zoom,
      g,
      fitted: false,
    };

    let readyCalled = false;
    const callReady = () => {
      if (readyCalled) return;
      readyCalled = true;
      if (typeof onReady === "function") onReady();
    };

    simulation = d3
      .forceSimulation(simNodes)
      .force(
        "link",
        d3
          .forceLink(links)
          .id((d) => d.id)
          .distance(96)
      )
      .force("charge", d3.forceManyBody().strength(-300))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide().radius((d) => (d.seed ? 22 : 16)))
      .alpha(0.85)
      .alphaDecay(0.06)
      .velocityDecay(0.45)
      .on("tick", () => {
        link.each(function (d) {
          const p = linkEndpoints(d);
          d3.select(this)
            .attr("x1", p.x1)
            .attr("y1", p.y1)
            .attr("x2", p.x2)
            .attr("y2", p.y2);
        });
        linkLabel
          .attr("x", (d) => linkEndpoints(d).mx)
          .attr("y", (d) => linkEndpoints(d).my - 4);
        node.attr("transform", (d) => `translate(${d.x},${d.y})`);
      })
      .on("end", () => {
        if (lastRender && !lastRender.fitted) {
          lastRender.fitted = fitGraphToView(svg, zoom, g, width, height);
        }
        stopSimulation();
        callReady();
      });

    window.setTimeout(() => {
      if (lastRender && !lastRender.fitted) {
        lastRender.fitted = fitGraphToView(svg, zoom, g, width, height);
        stopSimulation();
      }
      callReady();
    }, 1200);

    attachResizeObserver(container);
  }

  function relayout() {
    if (!lastRender) return;
    scheduleResizeCheck();
    if (!lastRender.svg && lastRender.graph) {
      render(lastRender.container, lastRender.graph, lastRender.onNodeClick, lastRender.onReady);
    }
  }

  function exportPng(container) {
    return new Promise((resolve) => {
      const svg = container && container.querySelector("svg");
      if (!svg) {
        resolve(null);
        return;
      }
      const inner = svg.querySelector("g");
      if (!inner) {
        resolve(null);
        return;
      }
      try {
        const bbox = inner.getBBox();
        const pad = 48;
        const vbX = bbox.x - pad;
        const vbY = bbox.y - pad;
        const vbW = Math.max(bbox.width + pad * 2, 80);
        const vbH = Math.max(bbox.height + pad * 2, 80);
        const clone = svg.cloneNode(true);
        clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
        clone.setAttribute("viewBox", `${vbX} ${vbY} ${vbW} ${vbH}`);
        const outW = Math.min(1400, Math.max(640, Math.round(vbW)));
        const outH = Math.round(outW * (vbH / vbW));
        clone.setAttribute("width", String(outW));
        clone.setAttribute("height", String(outH));
        inlineSvgStyles(clone);
        const xml = new XMLSerializer().serializeToString(clone);
        const blob = new Blob([xml], { type: "image/svg+xml;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const img = new Image();
        img.onload = () => {
          const canvas = document.createElement("canvas");
          canvas.width = outW;
          canvas.height = outH;
          const ctx = canvas.getContext("2d");
          ctx.fillStyle = "#f8fafc";
          ctx.fillRect(0, 0, outW, outH);
          ctx.drawImage(img, 0, 0, outW, outH);
          URL.revokeObjectURL(url);
          const dataUrl = canvas.toDataURL("image/png");
          resolve(dataUrl.split(",")[1] || null);
        };
        img.onerror = () => {
          URL.revokeObjectURL(url);
          resolve(null);
        };
        img.src = url;
      } catch {
        resolve(null);
      }
    });
  }

  function stop() {
    stopSimulation();
    disconnectResize();
    lastRender = null;
  }

  window.DeduceGraph = { render, relayout, exportPng, stop };
})();
