# 易知「推演」2.1.0 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按 Task 逐步实施。  
> **前置方案：** [`2026-07-13-yizhi-predict-from-future.md`](2026-07-13-yizhi-predict-from-future.md)（产品决策已锁定）

**Goal:** 新增「推演」Tab：自然语言输入 → 本地 RAG 检索 → 子图关系图 + 文字报告 + 图谱解读 → **默认保存为笔记**；版本 **2.1.0**。

**Architecture:** 后端 `lib/deduce_graph.py` 从 RAG 命中页 + wiki `links` 构建子图 JSON；`lib/deduce.py` 两阶段 LLM（报告 + 图谱解读）+ `save_page` 入库；前端 SSE 流式展示左图右文布局；D3 力导向（`d3` 加入 electron 依赖并 sync 到 vendor）。**不**引入 Zep/OASIS。

**Tech Stack:** Python 3.11+、`lib/rag_agent.search_enhanced`、`lib/llm._chat_stream`、`FastAPI SSE、Electron renderer、D3 v7。

---

## 文件结构（新建 / 修改）

| 文件 | 职责 |
|------|------|
| `lib/deduce_graph.py` | **新建** — 子图 nodes/edges 构建 |
| `lib/deduce.py` | **新建** — 推演主流程 + `deduce_stream()` |
| `lib/prompts.py` | **修改** — `system_for_deduce()`、报告/图谱解读模板 |
| `backend/server.py` | **修改** — `DeduceBody`、`POST /api/deduce/stream` |
| `electron/renderer/index.html` | **修改** — Tab + `#panel-deduce` 布局 |
| `electron/renderer/app.js` | **修改** — `runDeduce()`、SSE、保存反馈 |
| `electron/renderer/deduce-graph.js` | **新建** — D3 力导向渲染 |
| `electron/renderer/styles.css` | **修改** — `.deduce-layout` 等 |
| `electron/package.json` | **修改** — `version: 2.1.0`，依赖 `d3` |
| `electron/scripts/sync-d3.mjs` | **新建** — vendor 复制 d3.min.js |
| `tests/test_deduce_graph.py` | **新建** — 子图构建单元测试 |
| `docs/更新记录.md` | **修改** — 发版条目 |
| `electron/renderer/onboarding.js` | **修改**（可选 Task） — 增加「推演」一步 |

---

## SSE 事件协议

```json
{ "type": "status", "text": "正在检索知识库…" }
{ "type": "graph", "graph": { "nodes": [...], "edges": [...] } }
{ "type": "token", "text": "…", "section": "report" | "graph_commentary" }
{ "type": "done", "title": "…", "wiki_page": "notes/….md", "sources": [...], "content_html": "…", "graph": {…} }
{ "type": "error", "message": "…" }
```

**graph 节点示例：**

```json
{
  "id": "concepts/foo.md",
  "title": "Foo",
  "page_type": "concept",
  "seed": true,
  "score": 0.82
}
```

---

## Task 1: 子图构建 `lib/deduce_graph.py`

**Files:**
- Create: `Myknowledge/lib/deduce_graph.py`
- Test: `Myknowledge/tests/test_deduce_graph.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_deduce_graph.py
from pathlib import Path
from lib.deduce_graph import build_deduce_subgraph
from lib.rag import RagChunk

def test_build_subgraph_from_seeds(tmp_path, monkeypatch):
    # 在 tmp_path 下建 concepts/a.md links -> concepts/b.md
    ...
    chunks = [RagChunk(chunk_id="1", rel_path="concepts/a.md", title="A", text="t", score=1.0, ...)]
    g = build_deduce_subgraph(chunks, root=tmp_path, max_nodes=20)
    assert len(g["nodes"]) >= 2
    assert any(e["source"] == "concepts/a.md" for e in g["edges"])
```

- [ ] **Step 2: 运行测试确认 FAIL**

Run: `cd E:\app\Myknowledge && python -m pytest tests/test_deduce_graph.py -v`  
Expected: FAIL `ModuleNotFoundError: lib.deduce_graph`

- [ ] **Step 3: 实现 `build_deduce_subgraph`**

```python
# lib/deduce_graph.py 核心逻辑
def build_deduce_subgraph(chunks, *, root=None, max_nodes=24, max_hops=1) -> dict:
    """Return {nodes: [{id,title,page_type,seed,score}], edges: [{source,target,label?}]}."""
    # 1. seed_paths = unique rel_path from chunks, mark seed + max score
    # 2. expand_with_links(chunks) 复用 rag_graph
    # 3. list_pages + resolve_link 建边（参考 scripts/update_index.resolve_link）
    # 4. 截断 max_nodes，优先保留 seed 与高 score 节点
```

- [ ] **Step 4: 测试 PASS**

- [ ] **Step 5: Commit** `feat(deduce): add wiki-link subgraph builder`

---

## Task 2: 推演核心 `lib/deduce.py`

**Files:**
- Create: `Myknowledge/lib/deduce.py`
- Modify: `Myknowledge/lib/prompts.py`

- [ ] **Step 1: 在 `prompts.py` 增加 system 与输出骨架**

```python
DEDUCE_REPORT_SECTIONS = """
## 已知事实
（仅引用检索片段，逐条标注来源路径）

## 可能走向
（2–4 条；每条标注依据强度：强/中/弱；无依据不写）

## 关键不确定因素

## 知识库缺口
"""

DEDUCE_GRAPH_SECTION = """
## 关系图解读
（针对本次子图：核心节点、关键连边、与推演主题的关联；无 knot 须说明「子图较 sparse」）
"""

def system_for_deduce() -> str:
    # 拼接 OBJECTIVE_ANALYSIS_RULES + FACT_RULES（从 llm 或 prompts 引入）
    ...
```

- [ ] **Step 2: 实现 `deduce_stream(query, scope_paths=None, top_k=None)`**

流程：

1. `yield status` 检索中  
2. `search_enhanced(query, ...)` — 无结果则 `yield error` + 仍保存空报告笔记（说明缺口）  
3. `build_deduce_subgraph(chunks)` → `yield graph`  
4. LLM 流式 section=`report`（temperature ≤ 0.35）  
5. LLM 流式 section=`graph_commentary`（注入 graph JSON 摘要 + 报告摘要）  
6. 合并 Markdown → `save_page(type="note", tags=["推演"], meta deduce=true, links=子图节点 titles)`  
7. `schedule` 或调用 `sync_all` 刷新 RAG（与 produce 一致）  
8. `yield done` 含 `wiki_page`、`content_html`、`graph`

参考：`lib/llm.py` 的 `produce_stream`、`_finalize_produce_result` 中 `save_page` 段落。

- [ ] **Step 3: 手动冒烟**

Run backend 后：

```powershell
curl -N -X POST http://127.0.0.1:18765/api/deduce/stream `
  -H "Content-Type: application/json" `
  -d '{"query":"基于库内资料，台风相关可能怎样发展"}'
```

Expected: SSE 含 `graph`、`token`、`done.wiki_page`

- [ ] **Step 4: Commit** `feat(deduce): streaming deduce pipeline with auto-save`

---

## Task 3: API `backend/server.py`

**Files:**
- Modify: `Myknowledge/backend/server.py`

- [ ] **Step 1: 增加 Pydantic body**

```python
class DeduceBody(BaseModel):
    query: str
    scope_paths: list[str] | None = None
    top_k: int = 0
```

- [ ] **Step 2: 注册路由**（仿 `api_produce_stream`）

```python
@app.post("/api/deduce/stream")
def api_deduce_stream(body: DeduceBody):
    def event_gen():
        from lib.deduce import deduce_stream
        for ev in deduce_stream(body.query, scope_paths=body.scope_paths or None, top_k=body.top_k or None):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
    return StreamingResponse(event_gen(), media_type="text/event-stream", headers={...})
```

- [ ] **Step 3: Commit** `feat(api): POST /api/deduce/stream`

---

## Task 4: 前端 Tab 与布局

**Files:**
- Modify: `electron/renderer/index.html`, `app.js`, `styles.css`

- [ ] **Step 1: `index.html` 在「查询」后插入 Tab**

```html
<button class="tab" role="tab" data-tab="deduce" aria-controls="panel-deduce">推演</button>
```

```html
<section id="panel-deduce" class="panel">
  <p class="hint">基于本地知识库推演可能走向；结论须有依据，结果默认保存为笔记。</p>
  <div class="row">
    <textarea id="deduce-input" rows="3" placeholder="用自然语言描述推演问题…"></textarea>
    <button id="btn-deduce" class="primary" type="button">开始推演</button>
  </div>
  <div class="deduce-layout">
    <div id="deduce-graph-host" class="deduce-graph-host"></div>
    <div id="deduce-output" class="deduce-output answer-html"></div>
  </div>
  <p id="deduce-saved-hint" class="hint hidden"></p>
</section>
```

- [ ] **Step 2: `app.js` — `runDeduce()`**

- `fetch` + `ReadableStream` 解析 SSE（复用 ask/produce 解析函数若有）  
- `type===graph` → `DeduceGraph.render(host, ev.graph)`  
- `type===token` → 追加到 `#deduce-output`（区分 section 可加小标题）  
- `type===done` → 显示「已保存至 notes/…」链接，`switchTab` 可选  

- [ ] **Step 3: `styles.css`**

```css
.deduce-layout { display: grid; grid-template-columns: minmax(280px, 38%) 1fr; gap: 12px; min-height: 360px; }
.deduce-graph-host { border: 1px solid var(--border); border-radius: 8px; min-height: 320px; }
```

- [ ] **Step 4: Commit** `feat(ui): deduce tab layout and SSE consumer`

---

## Task 5: D3 关系图 `deduce-graph.js`

**Files:**
- Create: `electron/renderer/deduce-graph.js`
- Create: `electron/scripts/sync-d3.mjs`
- Modify: `electron/package.json`, `index.html` script 标签

- [ ] **Step 1: 添加依赖并 sync**

```json
// electron/package.json dependencies
"d3": "^7.9.0"
```

`sync-d3.mjs` 复制 `node_modules/d3/dist/d3.min.js` → `renderer/vendor/d3/d3.min.js`

- [ ] **Step 2: 实现 `window.DeduceGraph.render(container, graph)`**

- 力导向仿真（`d3.forceSimulation` + `forceLink` + `forceManyBody`）  
- seed 节点高亮（`seed: true` 更大半径 / accent 色）  
- 点击节点：`shell.openPath` 或跳转资料库预览（复用现有 open asset API）  
- 借鉴 MiroFish `GraphPanel.vue` **思路**，**不复制** Vue/SVG 代码  

- [ ] **Step 3: 空图状态** — 显示「暂无关联节点，请先导入资料」

- [ ] **Step 4: Commit** `feat(ui): d3 force graph for deduce`

---

## Task 6: 版本 2.1.0 与文档

**Files:**
- Modify: `electron/package.json` → `"version": "2.1.0"`
- Modify: `docs/更新记录.md`
- Modify: `docs/commercial/构建安装包.md`（可选一句 2.1.0 新功能）

- [ ] **Step 1: bump version**

- [ ] **Step 2: 更新记录顶部追加 compact 条目**

- [ ] **Step 3: 构建安装包**（2.0.1 先发则 2.1.0 另发；按产品节奏）

```powershell
cd E:\app\Myknowledge
# 改 electron/package.json 已 2.1.0
.\scripts\build-installer.ps1 -LicenseServer "..." -JwtSecret "..."
```

- [ ] **Step 4: Commit** `chore: release 2.1.0 deduce feature`

---

## Task 7: 验收清单（必须全部通过）

- [ ] 空库 / 无命中：报告说明「库内依据不足」，**不编造**；仍生成笔记  
- [ ] 有命中：左侧子图 ≥1 节点，seed 高亮；右侧含「报告 + 关系图解读」  
- [ ] 笔记默认出现在 `notes/`，frontmatter 含 `deduce: true`、tags 含 `推演`  
- [ ] 全程无 Zep/OASIS/外网检索（仅既有 LLM/Embedding）  
- [ ] 安装版 `%LOCALAPPDATA%\Yizhi` 路径正常  
- [ ] `docs/更新记录.md` 已写 compact 条目  

---

## 执行选项

**Plan saved to:** `docs/superpowers/plans/2026-07-13-yizhi-deduce-implement.md`

1. **Subagent-Driven（推荐）** — 每 Task 派生子 agent + 审查  
2. **Inline Execution** — 本会话按 Task 1→7 连续编码  

回复 **「开始实现」** 并选择 1 或 2，即进入编码（此前仍不改代码）。
