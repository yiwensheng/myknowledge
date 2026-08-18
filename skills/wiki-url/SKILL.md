---
name: wiki-url
description: 抓取网页 URL 并本地化入库。用户说「存入 wiki」且提供 URL 时使用。
myknowledge:
  action: url
  triggers:
    - 存入 wiki
    - 存入wiki
    - URL 入库
---

# URL 入库（wiki-url）

## 执行

```powershell
yws skill run wiki-url --url "https://example.com/article"
# 或
yws url "https://example.com/article"
```

## 参数

| 参数 | 说明 |
|------|------|
| `url` | 网页地址（必填） |
| `force` | 强制重新抓取（可选） |

## 流程

抓取 → `assets/documents/urls/` → `sources/` 条目 → RAG 重建
