---
name: wiki-pdf-llm-parse
description: ParseBench 风格多模态 PDF 版面解析：HTML 表、合并单元格、跨页合表；写预览不自动入库。
myknowledge:
  action: pdf-llm-parse
  triggers:
    - LLM版面解析
    - 视觉解析PDF
    - pdf-llm-parse
---

# LLM 版面解析（wiki-pdf-llm-parse）

本地化自 ParseBench / 头条文「用对 prompt 做文档解析」思路（不捆绑 gaik、不调用 LlamaParse）：

1. 整页截图 → 多模态 LLM  
2. 输出带 `data-bbox` / `data-label` 的 div  
3. **表格用 HTML**（`colspan`/`rowspan`），不用扁平 Markdown  
4. 可选跨页合表；清洗后写入 `notes/parse-preview/` 供肉眼验收  

## 参数

| 参数 | 说明 |
|------|------|
| `topic` | PDF 路径（相对知识库根或绝对路径）；空=inbox 首个 PDF |
| 正文含 `保留坐标` | 预览保留 bbox div |
| 正文含 `不合表` | 关闭跨页合表提示 |

## 环境变量（可选，导入链路）

| 变量 | 默认 | 说明 |
|------|------|------|
| `MYKNOWLEDGE_PDF_LLM_PARSE` | `0` | `1` 时导入弱文本 PDF 可改走视觉解析 |
| `MYKNOWLEDGE_PDF_LLM_PARSE_FORCE` | `0` | `1` 时强制视觉解析（很贵） |
| `MYKNOWLEDGE_PDF_LLM_PARSE_MAX_PAGES` | `8` | 最多页数 |
| `MYKNOWLEDGE_PDF_LLM_PARSE_DPI` | `140` | 渲染 DPI |

需模型支持 `image_url`。日常复杂单份用本工作流即可，不必开导入增强。

## CLI

```powershell
yws skill run wiki-pdf-llm-parse --topic "inbox/订单.pdf"
```
