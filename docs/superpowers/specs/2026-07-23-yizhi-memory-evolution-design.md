# 易知 · 记忆进化与启动续航 — 设计规格

**日期**：2026-07-23  
**状态**：已通过并实施（P0–P2 主干）  
**产品**：易知（Myknowledge）  
**范围**：偏好/规则、会话摘要、相关问答召回、记忆治理审计、重启续航与「能进化」体感  

---

## 1. 背景与目标

用户确认：在易知**现有** `output-rules`、`.memory`、RAG/问答日志之上加强，不引入 Persome / Mem0 等外挂「个人模型」。

### 目标

1. **A 偏好/规则**：条目可增删改、可开关，提问与写文章仅注入启用中的规则。  
2. **B 会话摘要**：长对话压缩早先轮次，注入「摘要 + 最近 N 轮原文」。  
3. **C 相关问答**：改进召回，并在结果中可审计地展示引用了哪些历史问答。  
4. **D 可删可审计**：记忆面板统一管理规则/会话/问答/摘要；操作可追溯。  
5. **E 不迷路 + 进化感**（用户补充）：下次启动能接着干；能看见规则、归档、purpose 等在变厚。

### 非目标（本期不做）

- OS 级活动采集、屏幕录制、跨设备云同步个人模型。  
- 用「记忆」覆盖「只许用检索片段」的事实约束。  
- 默认强制全量向量记忆（P2 可作可选增强）。

---

## 2. 原则

1. **落盘即持久**：状态在 wiki / `.memory` / `prompts/`，进程重启不丢。  
2. **可查可改可删**：每条记忆对象有 id；删除与开关立即影响下次注入。  
3. **事实优先**：规则与摘要不得要求编造检索中不存在的事实（沿用现有 prompt 约束）。  
4. **渐进交付**：P0 → P1 → P2，每期可独立验收。  
5. **外科手术改动**：复用 `lib/memory.py`、`lib/memory_db.py`、`lib/output_rules.py`、设置页「对话与记忆」、提问页会话控件。

---

## 3. 现状基线（相关文件）

| 能力 | 现状 | 缺口 |
|------|------|------|
| 规则 | `prompts/output-rules.md`；`POST /api/output-rules` 追加；纠错弹窗 | 无条目 CRUD/开关；难浏览 |
| 会话 | `session_id` + 最近 N 轮原文；`localStorage` 保 session | 无摘要；重启无「续航」引导 |
| 相关问答 | `search_related_qa` token 重叠；仅 grounded；扫近 500 条 | 召回弱；UI 不展示引用 |
| 历史 | `GET/PATCH/DELETE /api/memory/history/{id}` | 无整会话删；无统一记忆面板；无审计日志 |
| 目标 | `purpose.md` 写文章会注入摘要 | 提问续航未突出；无进化统计条 |

---

## 4. 数据模型

### 4.1 规则（仍以 Markdown 为源，结构化读写）

文件：`prompts/output-rules.md`（相对 wiki 或现有 `prompts_dir()`）。

每条规则块约定（兼容旧「### 时间戳（纠错）」格式，迁移时补 id）：

```markdown
### {id} · {yyyy-MM-dd HH:mm}（纠错|偏好） <!-- enabled: true -->
- **触发问题**：…
- **规则**：…
```

- `id`：稳定短 id（如 `r_` + 8 hex）。  
- `enabled: false` 时不注入。  
- API 解析/重写整文件；禁止半残写入（写临时文件再替换）。

### 4.2 会话与摘要（SQLite `memory.db`）

在现有 `sessions` / turns 存储上扩展（具体列名实现时可微调，须幂等迁移）：

| 字段/表 | 说明 |
|---------|------|
| `sessions.id` | 已有 session_id |
| `sessions.summary` | 文本；早先轮次的压缩摘要 |
| `sessions.summary_updated_at` | 北京时间墙钟字符串 |
| `sessions.title` | 可选；首问截断或用户改名 |
| turns | 保持现有结构 |

摘要生成触发：turns 对数超过 `MYKNOWLEDGE_MEMORY_TURNS` 且距上次摘要有新增早先轮次时（P1）。

### 4.3 问答日志

沿用 `qa_log`；召回结果至少带回 `id`，供 UI 引用。

### 4.4 审计

表 `memory_audit`（或 `.memory/audit.jsonl`，二选一，推荐 SQLite）：

| 列 | 说明 |
|----|------|
| `at` | 北京时间 |
| `action` | `rule_enable` / `rule_delete` / `qa_delete` / `session_delete` / `summary_clear` 等 |
| `object_type` | `rule` / `qa` / `session` / `summary` |
| `object_id` | 字符串 |
| `detail` | 可选短说明 |

### 4.5 进化快照（可重建）

路径：`.memory/evolution.json`（由 stats API 聚合写入，丢失可重建）：

```json
{
  "updated_at": "2026-07-23 07:26",
  "rules_enabled": 3,
  "rules_total": 5,
  "qa_log_entries": 120,
  "qa_archived_notes": 40,
  "sessions": 12,
  "purpose_excerpt": "……",
  "last_session_id": "…",
  "last_session_title": "…",
  "week_delta": {
    "rules_added": 2,
    "qa_added": 15,
    "archived_added": 4
  }
}
```

`week_delta` 可用审计 + qa_log.`at` 粗算；P0 可先做总量，P1 补周增量。

---

## 5. API（增量）

### 规则

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/output-rules` | 扩展：返回 `rules: [{id, enabled, text, question, at}]` + raw |
| POST | `/api/output-rules` | 保持追加；响应含新 `id` |
| PATCH | `/api/output-rules/{id}` | 改正文 / `enabled` |
| DELETE | `/api/output-rules/{id}` | 删除条目 |

### 记忆与续航

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/memory/continuity` | 续航卡片数据：last session、purpose 摘录、规则数、进化 stats |
| PATCH | `/api/memory/session/{id}` | 改 title / summary（人工编辑） |
| DELETE | `/api/memory/session/{id}` | 删会话 turns + 可选级联提示 |
| POST | `/api/memory/session/{id}/summarize` | 强制重摘要（P1） |
| GET | `/api/memory/audit` | 分页审计（D） |
| GET | `/api/memory/evolution` | 读快照；可 `?refresh=1` 重算 |

提问/写文章请求体：相关问答引用列表可在响应 `meta.related_qa` 中返回（C），前端渲染。

---

## 6. 注入逻辑（提问）

组装顺序（示意）：

1. System：人设 + 事实约束 + **启用中的** output-rules  
2. User 侧上下文：  
   - （可选）purpose 短摘录（续航/进化一致时可轻量注入，避免与写文章重复过长）  
   - **会话摘要**（若有）  
   - **最近 N 轮**原文  
   - RAG 片段  
   - **相关历史问答**（带 id）  

写文章：继续注入启用规则；相关问答行为与现 `search_related_qa` 对齐并返回引用 meta。

---

## 7. UI

### 7.1 续航 — 方案丙（已确认）

**甲：提问页顶部常驻条（可折叠）**

- 展示：上次会话标题/摘要一行、purpose 一行、启用规则数、本周进化数字（有则显示）。  
- 操作：「继续上次」「新开对话」。  
- 折叠状态可记 `localStorage`。

**乙：冷启动弹窗（每天最多一次，可关）**

- 触发：Electron 主窗口首次 ready 且当日未选「今日不再显示」（键如 `myk-continuity-dismiss-date=yyyy-MM-dd`）。  
- 内容同续航要点 + 「继续」/「新开」/「今日不再显示」。  
- 「继续」跳转提问页并保持 session；「新开」调现有新会话 API。

### 7.2 规则管理

- 设置 →「对话与记忆」：规则列表（开关、编辑、删除）。  
- 保留提问纠错「追加规则」入口。

### 7.3 记忆与进化面板（D）

- 入口：管理页或设置旁「记忆与进化」。  
- 分栏：规则 / 会话 / 问答历史 / 审计。  
- 进化条：总量 + 近 7 日增量（文案示例：「近 7 日：+2 条规则 · +15 次问答 · +4 篇归档」）。

### 7.4 相关问答展示（C）

- 答案区脚注或折叠：「参考历史问答」列表（问题截断 + 时间）；点击可打开历史详情（复用现有历史 UI）。

---

## 8. 分期与验收

### P0 — 规则治理 + 续航不迷路

- [ ] 规则条目解析、PATCH/DELETE、enabled 注入过滤  
- [ ] `GET /api/memory/continuity` + evolution 基础字段  
- [ ] 提问页顶部续航条 + 冷启动弹窗（丙）  
- [ ] 规则删改写审计（至少 rule_*）  
- [ ] 重启后：点「继续」能带着原 session 追问；关掉的规则不再出现在 prompt  

### P1 — 会话摘要 + 记忆面板

- [ ] 超限自动/半自动摘要；注入摘要+近 N 轮  
- [ ] 记忆面板：会话列表、改摘要、删会话、问答删（复用 API）  
- [ ] week_delta 进化统计  

### P2 — 相关问答加强

- [ ] 召回改进（FTS 或更好打分；可选向量）  
- [ ] 响应 `related_qa` + UI 引用列表  
- [ ] 可选：从「上次摘要」一键收入 purpose / 规则（增强进化闭环）

---

## 9. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 旧 output-rules 无 id | 首次 GET/迁移时为无 id 块补 id 并回写 |
| 摘要幻觉 | 摘要 prompt 要求只压缩对话已有内容；标注「会话摘要非知识库事实」 |
| 冷启动打扰 | 「今日不再显示」+ 顶部条可折叠 |
| 注入过长 | 摘要上限字数 + 规则条数上限（可配置，默认如启用最多 20 条） |

---

## 10. 测试要点

- 单元：规则解析/开关过滤；摘要拼接顺序；continuity 无会话时的空态。  
- 手工：杀进程再开 → 冷启动弹窗 → 继续追问上下文仍在；关规则后新提问 system 无该条；删问答后召回不再命中。  

---

## 11. 决策记录

| 项 | 决定 |
|----|------|
| 架构路径 | 现有栈强化（路径 3），不接 Persome |
| 分期 | P0 → P1 → P2 |
| 续航 UI | **丙**：提问页顶部 + 冷启动每日一次 |

---

## 12. 审阅清单（self-review）

- [x] 无 TBD 占位实现细节（列名允许实现微调）  
- [x] 与「事实优先」无矛盾  
- [x] 范围含 A–E，非目标已列  
- [x] 用户确认项（路径 3、方案丙）已写入决策表  

---

**下一步**：用户审阅本文件；通过后编写 `docs/superpowers/plans/2026-07-23-yizhi-memory-evolution.md` 实施计划（先 P0）。
