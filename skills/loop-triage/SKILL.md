---
name: loop-triage
description: Loop Engineering 知识库 triage：扫描 inbox/草稿/RAG 缺口，更新 STATE.md。用户说「运行循环」「知识库 triage」时使用。
myknowledge:
  action: loop
  triggers:
    - 运行循环
    - 知识库 triage
    - loop triage
---

# Loop Triage — 易知

基于 [Loop Engineering](https://github.com/cobusgreyling/loop-engineering) 的 **knowledge-evolution** 模式。

## 执行

```powershell
yws loop run --level 1    # 第一周：仅报告
yws loop run --level 2    # 自动 ingest + index
yws loop status
```

## 产出

- 更新根目录 `STATE.md`（High Priority / Watch List / Metrics）
- 追加 `.loop/loop-run-log.jsonl`

## Week One 规则

默认 `MYKNOWLEDGE_LOOP_WEEK_ONE=1` 强制 L1（只报告不自动改库）。信任循环后设 `MYKNOWLEDGE_LOOP_WEEK_ONE=0`。
