# 易知 Skills

本目录存放 **易知 可发现、可执行** 的 Skill，格式与 [Cursor Agent Skills](https://cursor.com/docs) 兼容。

**写文章自动注入（安装版自带，不依赖 Cursor）：**

| 目录 | 环境变量 | 作用 |
|------|----------|------|
| `no-ai-slop/` | `MYKNOWLEDGE_NO_AI_SLOP`（默认开） | 去套话、伪洞察 |
| `human-writing/` | `MYKNOWLEDGE_HUMAN_WRITING`（默认开） | 材料关、硬禁辞章、活人感推进 |

二者通过 `lib/no_ai_slop.py` / `lib/human_writing.py` 注入「写文章 / 改稿」system 提示；规则正文见各自 `produce-rules.md`。

## 目录结构

```
skills/
├── README.md           # 本说明
├── wiki-ingest/
│   └── SKILL.md          # 必填
├── my-custom/
│   ├── SKILL.md
│   └── scripts/
│       └── run.py        # 可选自定义执行器
```

## SKILL.md 模板

```markdown
---
name: my-custom
description: 一句话说明何时使用（会显示在 skill list 与 GUI）
myknowledge:
  action: ingest          # 内置动作，见下表
  triggers:
    - 用户口令一
    - 用户口令二
  enabled: true
---

# 技能标题

（给 AI 或用户阅读的操作说明）
```

### 内置 action

| action | 等价命令 | 参数 |
|--------|----------|------|
| `ingest` | `yws ingest` | — |
| `index` | `yws index` | — |
| `review` | 知识库回顾 | — |
| `url` | `yws url` | `url` |
| `ask` | `yws ask` | `question` |
| `produce` | `yws produce --wiki` | `topic` |
| `leader` | 生成目标任务书（Goal Brief） | `topic` / `text` / `idea` |
| `menu` | 列出子技能 | — |
| `script` | 运行 `scripts/run.py` | 任意 key=value |

无 `action` 且无 `scripts/run.py` 的 Skill 仅作为**说明文档**（可被 Cursor Agent 读取）。

## 发现路径

1. `Myknowledge/skills/`（本项目，默认）
2. `{WIKI_ROOT}/skills/`（若与项目目录不同）
3. `MYKNOWLEDGE_SKILLS_DIRS`（`.env` 额外目录，分号分隔）
4. `~/.cursor/skills/`（默认扫描，设 `MYKNOWLEDGE_INCLUDE_CURSOR_SKILLS=0` 可关闭）
5. `~/.agents/skills/`（设 `MYKNOWLEDGE_INCLUDE_AGENTS_SKILLS=1` 开启）

## CLI

```powershell
yws skill list
yws skill show wiki-ingest
yws skill run wiki-ingest
yws skill run wiki-url --url "https://..."
yws skill run leader --topic "一句话想法"
yws skill match "整理知识库"
```

## GUI

「工作流」Tab：内置「生成目标任务书」等卡片，输入参数后一键执行。

## 内置 Skill

| Skill | 说明 | CLI / GUI |
|-------|------|-----------|
| `leader` | 长任务「目标任务书」：焊死 Why/Done/Proof/Anti，防目标漂移 | `yws skill run leader --topic "…"`；GUI「生成目标任务书」 |
| `no-ai-slop` | 去 AI 味措辞约束 | **写文章默认自动注入**（设置可关）；对话润色见 Skill 正文 |

## 与 Cursor 协同

- **项目内 Skill**：放在本 `skills/` 目录，提交 Git 即可团队共享
- **个人 Skill**：放在 `~/.cursor/skills/`，在 `.env` 中已默认纳入扫描
- 在 Cursor 对话中说触发口令（如「整理知识库」「写任务书」「去 AI 味」），Agent 可 `yws skill match` 找到对应 Skill
- 打开易知仓库时，`.cursor/skills/leader/`、`.cursor/skills/no-ai-slop/` 也会被 Cursor 作为**项目级** Skill 加载

## 自定义 scripts/run.py

```python
#!/usr/bin/env python3
import os, sys
print("hello from custom skill", sys.argv[1:])
raise SystemExit(0)
```

Skill 的 `myknowledge.action` 设为 `script`（或存在 `scripts/run.py` 时自动识别）。
