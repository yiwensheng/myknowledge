# 自我蒸馏（Self-Distill）设计

**日期**：2026-08-09  
**状态**：已批准（用户确认英文路径 `distill/…` + 方案 1+2）

## 目标

为每个易知用户提供本地「自我蒸馏」骨架与闭环：原始经验入 Memory，提炼 Skills / Principle，Meta 约束更新规则；提问与写文章时自动注入 Skills + Principle。

## 目录

```
{wiki_root}/distill/
  memory/
  skills/
  principle/
  meta/          # 含 蒸馏规则.md
```

- 幂等：`ensure_distill_skeleton()` 只补缺，不覆盖已有用户文件。
- `distill` 纳入 `CONTENT_DIRS` / `WATCH_DIRS`，参与 list_pages 与 RAG。

## 工作流

- Skill：`wiki-distill`，参数 `topic`（主题或粘贴正文）。
- 写入：`memory/` 摘要、`skills/` 一条、`principle/` 零或一条；然后增量/延迟刷新 RAG。

## 注入

- ask / produce 组装 prompt 时检索 `distill/skills`、`distill/principle`（少量），拼「个人技能与原则」块；空则跳过。
- Memory 不强制注入。

## 非目标

全自动后台蒸馏、行业硬编码模板、云端记忆。
