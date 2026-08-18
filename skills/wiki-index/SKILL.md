---
name: wiki-index
description: 重建知识库索引与 RAG 向量。手改 wiki 或外联目录变更后执行。
myknowledge:
  action: index
  triggers:
    - 重建索引
    - 刷新 RAG
    - index
---

# 重建索引（wiki-index）

```powershell
yws skill run wiki-index
# 或
yws index
```

适用于：手改 Markdown、配置 `MYKNOWLEDGE_EXTRA_DIRS` 后、批量导入后需强制刷新 RAG。
