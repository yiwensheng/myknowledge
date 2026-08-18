# 易知长记忆 · 事实版本链（最小设计）

> **日期**：2026-08-12  
> **来源灵感**：[头条 · Mnemosyne 改版](https://www.toutiao.com/article/7672859422640603700/)（SQLite + 时序 + 冲突策略）  
> **决策**：不引入 Mnemosyne / Mem0 / Neo4j；在现有 `.memory/memory.db` 上演进。  
> **状态**：设计已定；实现待排期（本文件为验收依据）。

---

## 1. 问题

当前易知记忆：

| 已有 | 缺口 |
|------|------|
| 会话 turns、问答日志（SQLite） | 无「同一事实被更新」的版本链 |
| distill Memory/Skills（Markdown） | 偏知识复用，不是可查询事实对象 |
| 资料夹 scope | 事实级未按 project/folder 隔离检索 |
| 相关问答关键词 | 无「某日之后发生了什么」时序查询 |

用户改偏好、改结论时，旧答仍在日志里，模型可能同时看到矛盾陈述且无「当前版」标记。

---

## 2. 非目标（明确不做）

- 不打包 Mnemosyne，不接其 MCP 进安装包  
- 不上 Neo4j / Graphiti  
- 写入时不做全库 LLM 冲突扫描（对齐文中 Mem0 v3：矛盾可并存，读时择优）  
- 第一期不做跨 Cursor/Codex 共享记忆（MCP 仅作远期可选，与产品解耦）

---

## 3. MVP 范围（一期）

在 `lib/memory_db.py` 增加表 `facts`（名称可微调），仅服务**易知应用内**：

### 3.1 数据模型

```text
facts
  id              TEXT PK          -- 事实族 ID（同一主题一条链共用）
  version         INTEGER NOT NULL -- 1,2,3…
  status          TEXT             -- current | superseded
  template_hash   TEXT             -- 规范化陈述指纹，加速「是否同一事实」
  statement       TEXT NOT NULL    -- 人可读事实句（短）
  folder_id       TEXT DEFAULT ''  -- 资料夹/项目隔离；空=全局
  confidence      REAL DEFAULT 1   -- 0~1，检索排序用
  valid_from      TEXT             -- 北京时间墙钟，事实生效
  valid_to        TEXT             -- 被取代时写入；current 可空
  source_qa_id    INTEGER          -- 可选，关联 qa_log
  source_session  TEXT
  created_at      TEXT
  superseded_by   TEXT             -- 指向同 id 的更高 version，或空
```

索引：`(status, folder_id)`、`template_hash`、`(valid_from)`、`(id, version)`。

### 3.2 API（库内函数，非 MCP）

| 函数 | 行为 |
|------|------|
| `retain_fact(statement, folder_id=…, …)` | 算 template_hash；若存在同 hash 的 current → 旧行 status=superseded，新 version+1 为 current |
| `recall_facts(query, folder_id=…, limit=…)` | 先 folder 过滤；关键词/简单打分；仅默认返回 `status=current`；可选 `include_history` |
| `fact_versions(fact_id)` | 返回该族全部版本时间线 |
| `facts_since(at, folder_id=…)` | `valid_from >= at` 的 current（及可选 superseded） |

写入策略：不扫全库语义冲突；用户或后续「从问答提炼」显式 retain；矛盾 hash 不同则并存，recall 按 `valid_from`、`confidence` 排序。

### 3.3 注入提问（最小）

`prepare_ask` / 续聊时：若开启 `MYKNOWLEDGE_FACT_MEMORY=1`（**默认关**，一期可先只落库+面板），取当前资料夹下 top-K current facts 拼进 prompt 短块「【已知偏好与事实】」。与 distill Skills 并列，事实块更短、更硬。

### 3.4 UI（一期可砍到只 API）

- 记忆与进化：只读列表「当前事实」+ 展开版本  
- 或设置里开关 + 无独立页（二期再做）

---

## 4. 二期（可选）

- 从高分问答 / 用户纠错自动候选 retain（仍要人确认，对齐蒸馏预览）  
- `timeline` 视图  
- 本机开发用 MCP 封装同一 `memory.db`（**不进用户安装包**）  
- 与 distill Memory 页双向链接（事实 ↔ 笔记）

---

## 5. 验收标准（一期实现时）

1. 同一 `template_hash` 两次 retain → 仅一条 current，旧版可 `fact_versions` 查出  
2. 不同 folder_id 的事实互不出现在对方 `recall_facts` 默认结果  
3. `MYKNOWLEDGE_FACT_MEMORY=0` 时行为与现网一致  
4. 不新增 pip 依赖；仍为标准库 sqlite3  
5. 单测覆盖 retain 取代链、folder 隔离、facts_since  

---

## 6. 与现有模块边界

| 模块 | 关系 |
|------|------|
| `memory_db` sessions/qa_log | 保留；facts 为旁路表 |
| `distill/` | 继续管 Skills/Principle；facts 管短事实/偏好，不替代蒸馏 |
| `output_rules` | 规则仍独立；重要规则可 retain 一条事实摘要（人工） |
| 资料夹 | `folder_id` 与提问 scope 对齐 |

---

## 7. 排期建议

有用户明确「偏好改了但 AI 还记旧的」痛点时再开工一期；当前仅文档与评估落盘，避免过早堆表。
