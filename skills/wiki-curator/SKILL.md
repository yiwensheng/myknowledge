---
name: wiki-curator
description: 易知 知识库总控：列出所有可执行 Skill 与工作流入口。
myknowledge:
  action: menu
  triggers:
    - wiki-curator
    - 知识库管理
---

# Wiki Curator 总控

易知 自我进化知识库的管理入口。具体工作流已拆分为独立 Skill：

| Skill | 口令 | 作用 |
|-------|------|------|
| wiki-ingest | 整理知识库 | inbox → wiki |
| wiki-index | 重建索引 | 刷新 RAG |
| wiki-review | 知识库回顾 | 体检报告 |
| wiki-url | 存入 wiki + URL | 网页入库 |
| wiki-ask | （提问） | RAG 问答 |

## 环境

- `WIKI_ROOT` / `MYKNOWLEDGE_ROOT`：默认 `e:\app\Myknowledge`
- CLI：`yws` · GUI：`启动易知.bat`

## 列出全部 Skill

```powershell
yws skill list
yws skill run wiki-curator
```

## 在 Cursor 中使用

将本仓库 `skills/` 目录加入 Cursor Skills，或设置：

```ini
MYKNOWLEDGE_SKILLS_DIRS=%USERPROFILE%\.cursor\skills
```

## 添加自定义 Skill

1. 在 `skills/你的技能名/SKILL.md` 新建文件（见 `skills/README.md`）
2. `yws skill list` 验证
3. 可选：添加 `scripts/run.py` 作为自定义执行器
