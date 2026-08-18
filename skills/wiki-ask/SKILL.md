---
name: wiki-ask
description: 基于知识库 RAG 提问，只许使用库内片段作答。
myknowledge:
  action: ask
  triggers:
    - 知识库提问
    - ask
---

# 知识库提问（wiki-ask）

```powershell
yws skill run wiki-ask --question "你的问题"
# 或
yws ask "你的问题"
```

支持连续对话与有依据自动归档（见操作手册 §5.5）。

## 参数

| 参数 | 说明 |
|------|------|
| `question` | 问题文本 |
