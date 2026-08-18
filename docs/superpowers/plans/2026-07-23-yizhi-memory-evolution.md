# 易知 · 记忆进化与启动续航 Implementation Plan

> **For agentic workers:** 按 Task 顺序实施；用户要求自动推进、不中途确认。不主动 git commit。

**Goal:** P0→P2：规则 CRUD/开关、续航（提问条+冷启动弹窗）、会话摘要、记忆面板、相关问答引用、进化快照。

**Architecture:** 强化 `output_rules` + `memory_db` + 前端提问/设置；数据落盘 wiki/`.memory`/`prompts`。

**Tech Stack:** FastAPI、SQLite、Electron renderer（HTML/CSS/JS）

**Spec:** `docs/superpowers/specs/2026-07-23-yizhi-memory-evolution-design.md`

---

### Task 1: P0 规则条目化 + 注入过滤

- [x] 扩展 `lib/output_rules.py`：parse/list/migrate ids、enabled、format 仅 enabled
- [x] API：GET 带 `rules[]`；PATCH/DELETE `/api/output-rules/{id}`
- [x] 审计 `rule_*` 写入 memory_db

### Task 2: P0 continuity + evolution

- [x] `memory_audit` 表；`evolution.json` 聚合
- [x] `GET /api/memory/continuity`、`GET /api/memory/evolution`

### Task 3: P0 UI 续航丙 + 规则管理

- [x] 提问页顶部续航条；冷启动弹窗（今日不再显示）
- [x] 「记忆与进化」面板规则开关/删

### Task 4: P1 会话摘要 + 面板 API

- [x] sessions 表扩展 summary/title；注入摘要+近 N 轮
- [x] PATCH/DELETE session；summarize 端点
- [x] week_delta；记忆与进化面板 UI

### Task 5: P2 相关问答引用

- [x] search_related_qa 带回 id；响应 related_qa；答案脚注 UI
- [x] 召回打分小改进（问题命中加权）

### Task 6: 更新记录

- [x] `docs/更新记录.md`；规格状态改为已实施
