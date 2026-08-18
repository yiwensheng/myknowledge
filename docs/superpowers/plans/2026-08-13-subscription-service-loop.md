# 订阅服务闭环 Implementation Plan

> **For agentic workers:** Execute P0→P1→P2 per `docs/superpowers/specs/2026-08-13-subscription-service-loop-design.md`（含教师六步、OPC、职场修订）。

**Goal:** 试用形成服务闭环，到期看见资产，场景模板可确认入库。

**Architecture:** `lib/service_loop.py` 管进度/资产/模板；`llm.probe` 测 Key；前端任务条+周历+模板面板；授权 overlay 展示资产。

**Tech Stack:** FastAPI、现有 Electron renderer、wiki `.config/service-loop.json`

---

### Task 1: Backend core + probe + tests (P0/P1 data)
### Task 2: API routes
### Task 3: UI bar + settings probe (P0)
### Task 4: Weeks + license assets (P1)
### Task 5: Templates UI ×5 (P2)
### Task 6: wiki_reset + 更新记录
