---
name: wiki-parse-check
description: 解析质量抽检：对 inbox 或指定路径做提取+分块抽检，输出人类可读报告。
myknowledge:
  action: parse-check
  triggers:
    - 解析质量抽检
    - 解析抽检
    - parse-check
---

# 解析质量抽检（wiki-parse-check）

导入前拿「恶心样本」看提取结果是否人类可读。

## 参数

| 参数 | 说明 |
|------|------|
| `topic` | 可选：文件/目录路径；空则抽检 inbox/ |

## CLI

```powershell
yws skill run wiki-parse-check
yws skill run wiki-parse-check --topic "inbox/sample.pdf"
```
