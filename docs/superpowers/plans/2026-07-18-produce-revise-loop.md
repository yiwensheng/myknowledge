# 写文章草稿改稿闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 「写文章」生成后进入可编辑草稿；支持手改与 LLM 改稿（可选重 RAG）；仅「确认定稿」写入知识库。

**Architecture:** 后端新增 `produce_revise` / `finalize_produce`；前端写文章面板挂 Toast UI，状态机 `idle|streaming|draft|finalized`；默认 `save_to_wiki=false`。

**Tech Stack:** FastAPI、`lib/llm.py`、Electron renderer、`YizhiRichEditor`（Toast UI）

**Spec:** `docs/superpowers/specs/2026-07-18-produce-revise-loop-design.md`

---

## File map

| File | Responsibility |
|------|----------------|
| `lib/llm.py` | `produce_revise` / `produce_revise_stream`；finalize 助手或独立函数 |
| `backend/server.py` | `ProduceReviseBody`、`ProduceFinalizeBody`；`/api/produce/revise`、`/stream`、`/finalize` |
| `electron/renderer/index.html` | 去掉自动保存勾选；加改稿工具条与编辑器宿主机 |
| `electron/renderer/app.js` | 状态机、挂载编辑器、改稿/定稿、覆盖确认 |
| `tests/test_produce_revise.py` | 改稿 prompt / finalize 不调 LLM 的单元测 |
| `docs/更新记录.md` | 条目 |

---

### Task 1: 后端 revise + finalize（TDD）

- [x] **Step 1:** 新增 `tests/test_produce_revise.py`
- [x] **Step 2:** `lib/llm.py` 实现 revise / finalize
- [x] **Step 3:** `server.py` 路由
- [x] **Step 4:** `pytest tests/test_produce_revise.py -q` 通过

### Task 2: 前端 UI 骨架

- [x] **Step 1:** `index.html` 改稿工具条与编辑器宿主
- [x] **Step 2:** CSS

### Task 3: 前端状态机与 API 接线

- [x] **Step 1–5:** `app.js` 状态机、流式生成/改稿、定稿、Word 同步

### Task 4: 文档与冒烟

- [x] **Step 1:** `docs/更新记录.md`
- [ ] **Step 2:** 手工冒烟（用户侧）

**Commits:** 仅在用户要求时提交（本仓库惯例）。
