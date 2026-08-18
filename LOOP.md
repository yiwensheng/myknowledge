# LOOP — Myknowledge 知识进化循环

> 基于 [Loop Engineering](https://github.com/cobusgreyling/loop-engineering) 适配。

## Pattern

**knowledge-evolution** — 发现 inbox/草稿/RAG 缺口 → 更新 STATE → 按级别自动 ingest/index。

## Levels

| Level | 行为 | 命令 |
|-------|------|------|
| L1 | 仅 triage + 写 STATE.md | `yws loop run --level 1` |
| L2 | L1 + 自动 ingest/index | `yws loop run --level 2` |
| L3 | L2 + 对 purpose 开放问题尝试 produce（需 LLM） | `yws loop run --level 3` |

## Human Gates（硬停止）

- L3 produce 仅写 **draft**，不自动 refined
- 不删除 wiki 条目
- 不 force URL 重新抓取
- `MYKNOWLEDGE_LOOP_WEEK_ONE=1` 时强制 L1（第一周仅报告）

## Schedule

```powershell
yws loop watch --interval 3600   # 每小时
# 或 Cursor Automation 每日运行: yws loop run
```

## Audit（可选）

```bash
npx @cobusgreyling/loop-audit . --suggest
```

需本目录存在 `STATE.md`、`LOOP.md`、`skills/`。
