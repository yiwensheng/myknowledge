# 易知「推演」功能方案（借鉴 MiroFish / future 项目）

> **For agentic workers:** 本文档为**产品与技术方案**（Phase 0）。**产品决策已锁定（2026-07-13）**；实现见 `2026-07-13-yizhi-deduce-implement.md`。

**Goal:** 在易知主菜单增加 **「推演」** Tab，用户输入**自然语言**推演需求，系统**仅基于本地知识库、素材、RAG 与 SQLite** 输出：**关系图 UI + 文字报告 + 对关系图的解读**；结果**默认保存为笔记**（`notes/`）。版本 **2.1.0**。

**Architecture:** 复用易知现有 `search_enhanced` + 事实约束 LLM 管线，新增「预测专用 ReACT 工具集」（本地 RAG / 图谱扩展 / 统计 / 历史问答），可选轻量图谱可视化；与 MiroFish 的 Zep Cloud + OASIS 完全解耦，全部本地、无第三方图谱 SaaS。

**Tech Stack:** Electron renderer、`backend/server.py`（FastAPI）、`lib/rag*.py`、`lib/llm.py`、`.rag/embeddings.db`、`.memory/memory.db`；参考 MiroFish 的 `report_agent.py` / `zep_tools.py` **设计模式**（非复制代码）。

---

## 一、结论摘要（给决策者）

| 问题 | 结论 |
|------|------|
| `e:\app\future` 是什么？ | **MiroFish**：LLM + **Zep Cloud 知识图谱** + **OASIS 多智能体社媒仿真** → 预测报告。面向舆情/政策/小说结局等「群体涌现」场景。 |
| 能否整体搬进易知？ | **不能、也不应**。依赖 Zep API、OASIS/CAMEL 仿真栈、AGPL-3.0 许可、极高 token 成本；与易知「本地优先、有据问答」定位冲突。 |
| 能否借鉴？ | **能**。借鉴：**分步检索 + ReACT 报告 Agent**、**多视角子问题分解**、**分章节 Markdown 输出**、**D3 图谱 UI 思路**（数据源改为易知 wiki links）。 |
| 易知「预测」应是什么？ | **个人知识库内的情景推演 / 趋势归纳**：输入关键词 → 本地 RAG 拉证据 → LLM 在证据约束下给出「可能走向 + 依据 + 不确定性 + 缺口」，**禁止**无依据臆测。 |
| 是否要做知识图谱？ | **v1 不必新建图数据库**。易知已有 `rag_graph.py`（wiki `links` 多跳扩展）+ `index/knowledge-map.md`（Mermaid）。v2 可考虑实体视图。 |

**推荐决策：** ✅ **已批准** —「推演 v1 = 本地 RAG + 子图关系图 + 分节报告 + 图谱解读 + 默认入库」；**不做** OASIS 仿真；MiroFish 仅作架构参考（AGPL，不拷贝代码）。

### 已锁定产品决策（2026-07-13）

| # | 项 | 决定 |
|---|-----|------|
| 1 | Tab 名称 | **推演** |
| 2 | 结果持久化 | **默认保存为笔记**（`type: note`，可带 `deduce: true` frontmatter） |
| 3 | 输入 | **自然语言**（内部可抽关键词/子问题，用户无需填表格式） |
| 4 | 输出 | **关系图 UI + 文字报告 + 对关系图的解读**（三者同屏，v1 一并交付） |
| 5 | 版本 | **2.1.0** |

## 二、`future`（MiroFish）项目分析

### 2.1 定位与流水线

```
种子文件(PDF/MD/TXT) + 自然语言需求
    → LLM 生成本体(schema)
    → Zep Cloud 建图 + 文本 episode 注入
    → LLM 生成 OASIS Agent 人设 + 仿真配置
    → 多智能体在 Twitter/Reddit 模拟器中交互 N 轮
    → ReportAgent(ReACT) 调用 GraphRAG 工具写 Markdown 报告
```

**关键文件（`e:\app\future`）：**

| 模块 | 路径 | 作用 |
|------|------|------|
| 图谱 API | `backend/app/api/graph.py` | 本体、建图、任务进度 |
| 建图 | `backend/app/services/graph_builder.py` | Zep episode 批量注入 |
| GraphRAG 工具 | `backend/app/services/zep_tools.py` | QuickSearch / Panorama / InsightForge |
| 报告 Agent | `backend/app/services/report_agent.py` | ReACT 分章报告 |
| 仿真 | `backend/app/services/simulation_*.py` | OASIS 子进程 |
| 前端图谱 | `frontend/src/components/GraphPanel.vue` | D3 力导向图 |

### 2.2 「预测」的真实含义

MiroFish 的「预测」**不是** ML 时间序列或分类模型，而是：

> **用多智能体社会仿真涌现行为 + LLM 综合仿真轨迹写报告**

对个人知识库产品而言，这一定义过重、成本高、且难以保证「只许用库内事实」（仿真会**生成**新内容）。

### 2.3 外部依赖（易知需规避）

| 依赖 | 说明 |
|------|------|
| `ZEP_API_KEY` | 托管知识图谱 + GraphRAG |
| LLM API | 本体/人设/仿真每一步都调用 |
| `camel-oasis` | 社媒仿真引擎 |
| AGPL-3.0 | 直接合并代码有开源义务 |

---

## 三、易知现状与可复用能力

### 3.1 已有数据与检索（无需重复建设）

| 资产 | 位置 | 预测中的用途 |
|------|------|--------------|
| RAG 分块索引 | `.rag/chunks.json` + `embeddings.db` | 主证据检索 |
| 混合检索 | `lib/rag.py`（FTS5 + 向量 + RRF） | 关键词/语义召回 |
| 增强检索 | `lib/rag_agent.py` `search_enhanced` | 多轮 query 改写 |
| 链接图扩展 | `lib/rag_graph.py` | 沿 `links` 多跳补上下文 |
| Wiki 类型 | concept / entity / source / comparison / note | 定向检索、权重 |
| 原始素材 | `assets/` + `.extracted/` | 文件级证据 |
| 外联目录 | `linked-dirs` + `@external:` 前缀 | 只读本地文件夹证据 |
| DocuBrowser | `.docubrowser/` | PDF 等深度片段 |
| 对话记忆 | `.memory/memory.db` | 历史问答上下文（可选） |
| 静态知识图 | `index/knowledge-map.md` | 轻量关系概览 |

### 3.2 尚无、需新建

- 「预测」Tab UI 与 API
- 预测专用 system prompt（遵守 `llm-objective-analysis` 客观、不夸大）
- ReACT 工具封装（**全部调用本地 lib**，无 HTTP 外网检索）
- 预测结果持久化策略（可选存为 `notes/` 或 `archive/`）
- 预测历史列表（可复用 `/api/memory` 或新表）

### 3.3 与「提问」「写文章」的边界

| 功能 | 提问 | 写文章 | **预测（建议）** |
|------|------|--------|------------------|
| 用户输入 | 自然语言问题 | 主题 + 体例 | **关键词/主题 + 预测意图**（如「未来 3 个月趋势」） |
| 输出 | 直接回答 | 成稿 | **情景/趋势 + 依据引用 + 置信度 + 知识缺口** |
| 时间维度 | 弱 | 弱 | **强**（显式要求时间线与假设） |
| 结构 | 问答 | 文章结构 | **报告结构**（类似 MiroFish 分节，但更短更克制） |

---

## 四、易知「预测」产品定义（v1）

### 4.1 用户故事

1. 用户在「预测」Tab 输入：**关键词**（必填，如「台风路径」「某政策」）+ **预测说明**（选填，如「基于我库内资料，未来两周可能怎样」）。
2. 可选：**限定资料范围**（复用提问页 `scope_paths` 组件逻辑）。
3. 系统**仅**从本地 wiki、assets、RAG、外联、DocuBrowser、memory 取证据；**不**访问互联网、**不**调用 Zep、**不**运行 OASIS。
4. 输出 **预测报告**（Markdown/HTML 渲染）：
   - **已知事实**（引用库内片段）
   - **可能走向**（2–4 条，每条标注依据强度：强/中/弱/无依据则不写）
   - **关键不确定因素**
   - **库内缺口**（还缺什么资料才能预测更准）
5. 用户可「保存为笔记」进入 `notes/` 或导出。

### 4.2 非目标（v1 明确不做）

- 多智能体社媒仿真（MiroFish 核心）
- 依赖 Zep / 外部 Graph SaaS
- 无依据的「安慰式」预测或排名夸大（遵守全局 LLM 客观规则）
- 自动修改知识库内容（只读推理；保存需用户确认）

### 4.3 成功标准（验收）

- [ ] 空库或无关关键词时，明确提示「库内无足够依据」，**不**编造
- [ ] 报告中的事实性陈述均可追溯到 RAG 返回的 `rel_path` / 片段
- [ ] 全程无新增外网请求（除已有 LLM/Embedding API）
- [ ] 与「提问」共用 RAG 索引，预测后不要求全量 reindex
- [ ] 安装版 `%LOCALAPPDATA%\Yizhi` 路径下行为与开发版一致

---

## 五、推荐技术方案

### 5.1 总体架构

```
┌──────────────── Electron ─────────────────┐
│  Tab「预测」                               │
│  关键词 + 说明 + [限定范围] + [开始预测]   │
│  ← SSE 流式报告 / 进度（检索中/撰写中）      │
└───────────────────┬───────────────────────┘
                    │ POST /api/predict/stream
┌───────────────────▼───────────────────────┐
│  lib/predict.py (新)                       │
│  PredictAgent (ReACT, 参考 report_agent)   │
│    tools:                                  │
│      - search_kb(query) → search_enhanced  │
│      - search_by_type(type, query)         │
│      - expand_links(seed_chunks)           │
│      - stats_snapshot() → /api/stats 逻辑  │
│      - memory_recent(topic) → memory.db    │
│    → 分节生成 + OBJECTIVE_ANALYSIS_RULES   │
└───────────────────┬───────────────────────┘
                    │ 只读
┌───────────────────▼───────────────────────┐
│  .rag/  wiki/  assets/  .memory/  .docubrowser/ │
└───────────────────────────────────────────┘
```

### 5.2 从 MiroFish **借鉴的设计**（自行实现）

| MiroFish 概念 | 易知等价实现 |
|---------------|--------------|
| `InsightForge`（子问题分解 + 多路检索） | `search_enhanced` 多 query + 按关键词人工拆 2–3 个子问题（LLM planner 一步） |
| `ReportAgent` 分章 ReACT | `PredictAgent` 固定 4 节模板（事实/走向/不确定/缺口） |
| `GraphPanel` D3 | **v2**：用 wiki `links` 生成 nodes/edges JSON；v1 可省略 |
| `TaskManager` 长任务进度 | 复用现有 `YizhiJobs` / SSE 进度事件 |
| `TextProcessor` 分块 | 已有 `rag_chunk.py`，不重复 |

### 5.3 从 MiroFish **不移植**

- `graph_builder.py` / Zep ontology
- `simulation_*` / OASIS / `run_parallel_simulation.py`
- `oasis_profile_generator.py` 社媒人设
- `zep_graph_memory_updater.py`

### 5.4 API 草案（实现阶段用）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/predict/stream` | SSE：`phase=retrieve\|write\|done`，正文增量 |
| POST | `/api/predict` | 同步版（测试/CLI） |
| GET | `/api/predict/history` | 可选：最近 N 次预测摘要 |

**请求体示例：**

```json
{
  "keywords": "巴威 台风",
  "intent": "基于库内笔记与资料，推断未来一周可能影响",
  "scope_paths": [],
  "horizon": "7d"
}
```

### 5.5 Prompt 原则（须与 `lib/llm.py` 常量对齐）

- 注入 `OBJECTIVE_ANALYSIS_RULES` / `FACT_RULES`
- 每条「可能走向」必须带 `【依据：文件名或笔记标题】` 或标注「库内无直接依据，以下为弱推断」
- 禁止虚构库内不存在的考试、分数、事件
- 温度建议 ≤ 0.4（与成长档案一致）

### 5.6 前端集成点

| 文件 | 改动类型 |
|------|----------|
| `electron/renderer/index.html` | 新增 Tab + `#panel-predict` |
| `electron/renderer/app.js` | `switchTab('predict')`、SSE 消费、保存笔记 |
| `electron/renderer/styles.css` | 复用 `#ask-output` / produce 样式 |
| `electron/renderer/onboarding.js` | 后续增加一步介绍「预测」（非 v1 阻塞） |

**Tab 位置建议：** 放在 **「查询」与「笔记」之间** 或 **「写文章」右侧**——与「分析推理」邻近；具体可 A/B 选一个。

---

## 六、分阶段路线图

### Phase 0 — 方案评审（当前）

- [x] 分析 MiroFish 与易知差距
- [x] 定义 v1 范围与非目标
- [ ] **产品确认**：预测输出模板、Tab 文案、是否与「写文章」合并

### Phase 1 — 预测 MVP（建议版本 **2.1.0**）

- 后端 `lib/predict.py` + `/api/predict/stream`
- 前端「预测」Tab（关键词 + 流式报告 + 保存为笔记）
- 测试：空库 / 有关键词无命中 / 正常命中 / scope 限定
- 更新 `docs/更新记录.md`

### Phase 2 — 体验增强（2.2.x）

- 预测历史列表
- 侧边「依据片段」可点击跳转资料库/预览
- 复用「限定资料范围」UI 组件（与提问一致）

### Phase 3 — 轻量图谱（可选，借鉴 GraphPanel）

- `GET /api/graph/wiki-links` 从 wiki frontmatter 生成 nodes/edges
- Electron 内嵌 D3 或 Mermaid 只读视图，高亮预测引用的节点
- **仍不引入** Zep/Neo4j

### Phase 4 — 高级（慎选）

- 多 Agent 辩论（2–3 个**只读**视角 prompt，非 OASIS 仿真）
- 与「工作流」集成：`predict-and-archive` 一键预测并入库

---

## 七、风险与成本

| 风险 | 缓解 |
|------|------|
| LLM 幻觉预测 | 硬性格式：无依据不得写「可能走向」；检索结果为空则短路 |
| 与「提问」功能重叠 | UI 与 prompt 强调**时间维 + 多情景 + 缺口分析** |
| AGPL 误用 future 代码 | 仅参考架构；实现写在 `lib/predict.py`，不 copy-paste |
| Token 成本 | v1 限制：子问题 ≤3、RAG top ≤8、报告 ≤1500 字；无仿真轮次 |
| 安装包体积 | 不引入 OASIS/CAMEL/Zep 依赖 |

---

## 八、产品决策（已锁定）

见上文 **「已锁定产品决策」** 表。实现细节以 `2026-07-13-yizhi-deduce-implement.md` 为准。

---

## 九、实现计划

**文档：** [`2026-07-13-yizhi-deduce-implement.md`](2026-07-13-yizhi-deduce-implement.md)（Task 级步骤、测试、发版 2.1.0）

---

## 十、参考路径索引

| 项目 | 路径 |
|------|------|
| MiroFish 根目录 | `e:\app\future` |
| MiroFish README | `e:\app\future\README.md` |
| 易知 RAG | `e:\app\Myknowledge\lib\rag.py` |
| 易知图扩展 | `e:\app\Myknowledge\lib\rag_graph.py` |
| 易知 LLM 规则 | `e:\app\Myknowledge\lib\llm.py` |
| 易知 UI | `e:\app\Myknowledge\electron\renderer\index.html` |
| 客观分析全局规则 | `e:\app\.cursor\rules\llm-objective-analysis.mdc` |

---

**Plan complete.** 实现计划：`docs/superpowers/plans/2026-07-13-yizhi-deduce-implement.md`
