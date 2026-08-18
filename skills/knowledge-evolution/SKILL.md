---
name: knowledge-evolution
description: 完整知识进化循环（triage → ingest → index → 可选 produce）。使知识库越跑越厚。
myknowledge:
  action: loop-l3
  triggers:
    - 知识进化
    - 进化循环
    - knowledge evolution
---

# Knowledge Evolution Loop

易知 专属的 Loop Engineering 实现。

## Levels

| Level | 行为 |
|-------|------|
| L1 | 发现工作项，写 `STATE.md` |
| L2 | + 自动 `ingest` / `index` |
| L3 | + 对 `purpose.md` 开放问题 `produce --wiki` |

## 命令

```powershell
yws loop run
yws loop run --level 2
yws loop watch --interval 3600
```

## 与 Loop Engineering 生态

- `STATE.md` / `LOOP.md` 在 wiki 根目录（兼容 `loop-audit`）
- Skill 在 `skills/loop-triage/`、`skills/knowledge-evolution/`
- 可选审计：`npx @cobusgreyling/loop-audit . --suggest`
