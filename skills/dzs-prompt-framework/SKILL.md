---
name: dzs-prompt-framework
description: >-
  DZS 万能提示词工程框架（易知内置）：提问 / 写文章 / 推演时注入五阶段自适应认知循环与三维压力测试。
  设置可关；随安装包分发，不依赖 Cursor。
myknowledge:
  triggers:
    - DZS
    - 万能提示词
    - 认知催化
    - 压力测试
  enabled: true
---

# DZS 提示词框架（易知内置）

> **自动生效**：设置「写作风格学习 → DZS 认知催化」开启时（默认开），**提问 / 写文章 / 推演** 的 system 会注入 `yizhi-rules.md`。  
> **可关**：`MYKNOWLEDGE_DZS=0`。  
> **随安装包分发**：`skills/dzs-prompt-framework/`，不依赖 `~/.cursor/skills`。  
> 上游思路：头条 DZS 元框架；Cursor 全局 Skill `dzs-prompt-framework`（须显式）；本目录为易知单次流式适配版。

## 与其它注入的关系

| 模块 | 范围 | 管什么 |
|------|------|--------|
| **DZS**（本 Skill） | 提问 + 写文章 + 推演 | 自适应深度、静默压力测试、催化结构 |
| **human-writing** | 写文章/改稿 | 材料关、硬禁辞章 |
| **no-ai-slop** | 写文章/改稿 | 禁用套话与伪洞察措辞 |

写文章时三者可同时生效；DZS **不得**突破「只许用检索片段」。

## 细则

见同目录 `yizhi-rules.md`（与注入同源）。
