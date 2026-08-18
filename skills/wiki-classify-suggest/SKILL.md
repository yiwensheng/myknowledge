---
name: wiki-classify-suggest
description: 扫描 inbox/ 待处理文件，给出五类业务目录归属建议；不移动、不改写原文件。用户说「分类建议」「资料怎么归类」时使用。
myknowledge:
  action: classify-suggest
  triggers:
    - 分类建议
    - 资料归类
    - classify
---

# 资料分类建议（wiki-classify-suggest）

读取 `inbox/` 中待处理文件的文件名与正文摘录，按五类业务目录给出**归属建议**：

- 企业基础
- 产品服务
- 客户问题
- 案例资料
- 输出规则

## 执行

```powershell
yws skill run wiki-classify-suggest
```

或在 GUI「导入资料 → 工作流 → 资料分类建议」运行。

## 注意

- **不会**移动、删除或改写任何文件
- 确认建议后再运行「整理待处理文件」入库
- 可通过 `.env` 的 `MYKNOWLEDGE_CLASSIFY_MAX_FILES` 调整单次分析文件数
