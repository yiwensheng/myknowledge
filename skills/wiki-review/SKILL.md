---
name: wiki-review
description: 知识库体检：汇总草稿、孤岛、断链与统计。用户说「知识库回顾」时使用。
myknowledge:
  action: review
  triggers:
    - 知识库回顾
    - 知识库体检
    - review
---

# 知识库回顾（wiki-review）

读取 `index/open-questions.md`、`stats.md`、`recent.md` 并输出回顾摘要。

## 执行

```powershell
yws skill run wiki-review
```

GUI：Skills Tab → wiki-review → 执行

## 建议后续

- 优先处理 `status: draft` 条目
- 补全 `links` 消除孤岛
- 修复断链
