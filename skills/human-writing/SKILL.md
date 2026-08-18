---
name: human-writing
description: >-
  活人感写作：写文章时自动注入材料关与硬禁辞章；保证安装版用户无需 Cursor 也能生效。
  用户说「活人感」「言之有据」「少点 AI 腔」时可对照本 Skill。
myknowledge:
  triggers:
    - 活人感
    - 言之有据
    - human-writing
    - 少点 AI 腔
  enabled: true
---

# 活人感写作（易知内置）

> **自动生效**：设置「写作风格学习 → 写文章活人感约束」开启时（默认开），「写文章 / 改稿」的 system 会注入 `produce-rules.md`。  
> **可关**：设置里关闭 `MYKNOWLEDGE_HUMAN_WRITING`。  
> **随安装包分发**：本目录在 `skills/human-writing/`，构建保留 `skills/`，**不依赖**用户本机 Cursor / `~/.cursor/skills`。  
> 上游思路：Cursor Skill `human-writing`（蒸馏为 produce 可用规则，非完整多步 Agent 工作流）。

## 与 no-ai-slop 分工

| 模块 | 管什么 |
|------|--------|
| **human-writing**（本 Skill） | 材料够不够、硬禁冒号/破折号/翻案句、段落是否推进 |
| **no-ai-slop** | 禁用黑话、伪洞察、吹捧、总结腔等措辞 |

写文章时两者默认**同时**注入。

## 完整细则

见同目录 `produce-rules.md`（与写文章注入同源）。
