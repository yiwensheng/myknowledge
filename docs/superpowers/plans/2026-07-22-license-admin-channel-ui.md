# 授权服运营台 + 渠道落库 Implementation Plan

> **For agentic workers:** Implement task-by-task. Steps use checkbox syntax.

**Goal:** 共用授权服落渠道码，并提供 `/admin/ui` Web 运营台（总/分产品营收 + 渠道对账 + 运维）。

**Architecture:** SQLite 增量列/表；扩展 admin JSON API；单页 HTML/JS 调 API。

**Tech Stack:** FastAPI、SQLite、原生 HTML/CSS/JS（无新前端工程）

---

### Task 1: DB + create-order 渠道

- [ ] `orders.channel_code`；表 `promoters`
- [ ] `create_order(..., channel_code=)`
- [ ] `CreateOrderBody.channel_code`；`_order_response` 带回

### Task 2: Admin API

- [ ] `GET /admin/orders` 筛选分页
- [ ] `GET /admin/channels` 汇总（含分成）
- [ ] `GET/POST/PUT /admin/promoters`
- [ ] `GET /admin/stats` 增加按 `product` 拆分（或 query `product=`）

### Task 3: Web UI

- [ ] `app/static/admin/index.html`（+ 内联 CSS/JS）
- [ ] 挂载 `/admin/ui`
- [ ] 预置推广人：张文波 / 胡家兵（upsert）

### Task 4: 文档

- [ ] 更新 `license-server/README.md` 入口与字段说明
