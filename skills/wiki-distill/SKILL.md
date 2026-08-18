---
name: wiki-distill
description: 蒸馏本次产出：预览确认后写入 distill/memory、skills，可选 principle，并刷新检索。
myknowledge:
  action: distill
  triggers:
    - 蒸馏本次产出
    - 自我蒸馏
    - distill
---

# 蒸馏本次产出（wiki-distill）

把一次工作成品或主题摘要压成可复用资产：

1. **Memory**：原始要点与约束  
2. **Skills**：1 条不变范式  
3. **Principle**：0～1 条决策原则  

目录：`distill/memory|skills|principle|meta`（启动时自动建骨架）。

## 参数

| 参数 | 说明 |
|------|------|
| `topic` | 主题，或粘贴本次 PRD/汇报/笔记正文 |
| （正文末行） | 单独一行写 `确认入库` 才会真正写入；否则仅预览 |
| `confirm` / `commit` | 可选，`1`/`true` 等同于确认入库 |

## 流程

1. 先运行一次（只填正文）→ 得到预览 Markdown。  
2. 核对后，在正文末尾另起一行写 `确认入库` 再运行 → 入库并刷新检索。  

提问页会显示本次回答引用的 Skills / Principle 路径。

## CLI

```powershell
yws skill run wiki-distill --topic "本次列表迭代：…踩坑与结论"
# 确认后：
yws skill run wiki-distill --topic "…`n确认入库"
```
