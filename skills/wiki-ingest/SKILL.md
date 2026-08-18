---
name: wiki-ingest
description: 整理 inbox 内待处理文件，提取文本、写入 wiki 并重建 RAG。用户说「整理知识库」「整理 inbox」时使用。
myknowledge:
  action: ingest
  triggers:
    - 整理知识库
    - 整理 inbox
    - ingest
---

# 整理知识库（wiki-ingest）

将 `inbox/` 中的 pdf、docx、md 等文件自动分类入库。

## 执行

```powershell
yws skill run wiki-ingest
# 或
yws ingest
```

## 步骤

1. 扫描 `inbox/` 下所有支持格式文件
2. 提取正文，原文件存入 `assets/`
3. 在 `sources/` 等目录生成 Markdown 条目
4. 重建 `index/` 与 `.rag/`

## 前置条件

- 文件已复制到 `inbox/`（见操作手册 §3）
