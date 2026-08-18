# Cursor Skills 全览

> 扫描时间：2026-07-08  
> 范围：个人全局 Skills、项目 Skills（`e:\app`）、Cursor 内置 Skills  
> 用途：快速查名称、类别、能力与调用方式

---

## 一、Skills 从哪里来

| 作用域 | 路径 | 说明 |
|--------|------|------|
| **个人全局** | `%USERPROFILE%\.cursor\skills\` | 任意项目、任意目录的 Agent 对话均可被 Agent 自动匹配 |
| **项目级** | `e:\app\.cursor\skills\` | 仅在本 workspace（`e:\app`）内优先可用 |
| **项目 .agents** | `e:\app\.agents\skills\` | Caveman 官方安装器写入；与全局 Caveman **内容重复**，可视为项目副本 |
| **Cursor 内置** | `%USERPROFILE%\.cursor\skills-cursor\` | Cursor 官方自带；部分带 `disable-model-invocation`（仅用户显式触发） |

### 通用调用方式

1. **自动匹配**：在 Agent 对话里描述需求，Agent 根据各 Skill 的 `description` 自动 Read 并遵循（Superpowers 要求「有 1% 可能适用就必须读 Skill」）。
2. **显式点名**：在 prompt 里写 `使用 xxx-skill` 或 `@skill-name`（部分内置 Skill 支持 `/slash` 命令）。
3. **新开对话**：起号、Caveman 等长流程 Skill 建议新开 Agent 会话，上下文更干净。

---

## 二、按类别索引

| 类别 | 数量 | 典型场景 |
|------|------|----------|
| [开发工作流 Superpowers](#三开发工作流-superpowers) | 14 | 计划、TDD、调试、Code Review、Git worktree |
| [Spec Kit 规格驱动](#四spec-kit-规格驱动) | 6 | constitution → specify → plan → tasks → implement |
| [内容运营 / 起号](#五内容运营--起号) | 4 | 公众号、小红书、抖音、X 冷启动 |
| [Token 效率 Caveman](#六token-效率-caveman) | 7 | 精简回答、commit、review、压缩记忆文件 |
| [前端 / UI 设计](#七前端--ui-设计) | 2 | 落地页、反模板化 UI、设计系统检索 |
| [知识库](#八知识库) | 1 | 个人 Markdown Wiki 整理与入库 |
| [工程工具](#九工程工具) | 2 | 新项目脚手架、PyInstaller 排错 |
| [Cursor 内置](#十cursor-内置-skills-cursor) | 19 | Review、Canvas、Hook、SDK、自动化等 |

---

## 三、开发工作流 Superpowers

**路径：** `%USERPROFILE%\.cursor\skills\`  
**属性：** 个人全局 · 工作流方法论 · 多数为英文 Skill  
**来源：** [obra/superpowers](https://github.com/obra/superpowers) 系

| 名称 | 属性 | 能力 | 如何调用 | 示例 |
|------|------|------|----------|------|
| `using-superpowers` | 全局 · 元 Skill | 规定何时必须读取并遵循其他 Skill；优先级：用户指令 > Skill > 默认系统提示 | 每个 Agent 会话开始时 Agent 应自动遵循 | （无需手动调用，Agent 内部路由） |
| `brainstorming` | 全局 · 创意前置 | 做任何新功能/改行为前先澄清意图、需求与设计方案 | 创建功能、改行为、greenfield 前 | 「我想给智伴加一个导出 PDF 功能，先帮我想方案」 |
| `writing-plans` | 全局 · 计划 | 有多步任务/规格时，先写可执行实现计划再写代码 | 有 spec 或需求清单、跨文件任务 | 「按 spec 写一份实现计划，落盘到 docs/plans/」 |
| `executing-plans` | 全局 · 执行 | 在**独立会话**中按计划执行，带检查点 | 已有 written plan，另开会话执行 | 「按 plan.md 执行，每完成一段停下来 review」 |
| `subagent-driven-development` | 全局 · 执行 | **当前会话**内用子 Agent 分任务执行计划 | 计划任务可并行、会话内执行 | 「用子 Agent 按 tasks 逐条实现」 |
| `test-driven-development` | 全局 · 质量 | 先写失败测试，再写最少实现，再重构 | 任何功能/bugfix 实现前 | 「给这个 API 先写 pytest，再实现」 |
| `systematic-debugging` | 全局 · 调试 | 遇 bug/测试失败时系统化排查，先证据后修复 | 报错、异常行为、CI 红 | 「登录 500，先帮我定位根因再改代码」 |
| `verification-before-completion` | 全局 · 验收 | 声称「完成/通过」前必须跑验证命令并贴输出 | commit/PR 前、任务收尾 | 「改完了，跑 ruff 和单测确认后再说完成」 |
| `requesting-code-review` | 全局 · Review | 大功能完成或合并前发起结构化 Code Review | 功能完成、合并前 | 「按 requesting-code-review 审查这次 diff」 |
| `receiving-code-review` | 全局 · Review | 收到 Review 意见时先验证再改，不盲从 | PR 评论、Review 反馈 | 「这条 Review 说要用 Redis，帮我评估是否采纳」 |
| `dispatching-parallel-agents` | 全局 · 并行 | 2+ 独立任务无依赖时并行派子 Agent | 多模块互不阻塞 | 「前端改 Chat、后端改 API，并行做」 |
| `using-git-worktrees` | 全局 · 隔离 | 用 git worktree 或等效方式隔离功能开发 | 开新功能、执行计划前 | 「用 worktree 开分支做 OpenMAIC 对齐」 |
| `finishing-a-development-branch` | 全局 · 收尾 | 实现完成且测试通过后，引导 merge/PR/清理选项 | 分支开发结束 | 「功能做完了，帮我选 merge 还是开 PR」 |
| `writing-skills` | 全局 · 元 Skill | 编写、修改、验证新 Skill 的规范与流程 | 新建/改 Skill | 「帮我写一个 Cursor Skill 管数据库迁移」 |

---

## 四、Spec Kit 规格驱动

**路径：** `e:\app\.cursor\skills\`  
**属性：** 项目级 · 依赖子项目内 `.specify/` 目录  
**工作流：** constitution → specify → clarify → plan → tasks → implement

| 名称 | 属性 | 能力 | 如何调用 | 示例 |
|------|------|------|----------|------|
| `speckit-constitution` | 项目 · Spec | 创建/更新 `.specify/memory/constitution.md` 项目宪法 | 子项目初始化 Spec Kit 后 | 「为 Exam 子项目写 constitution」 |
| `speckit-specify` | 项目 · Spec | 从自然语言生成功能规格到 `specs/<feature>/` | 新功能、要先写 spec | 「specify：学生成绩导出 Excel」 |
| `speckit-clarify` | 项目 · Spec | 计划前澄清 spec 中模糊点 | specify 之后、plan 之前 | 「clarify 刚才的 spec 里权限边界」 |
| `speckit-plan` | 项目 · Spec | 从 spec 生成技术实现计划 | 有 spec、要写 plan | 「根据 spec 写技术 plan」 |
| `speckit-tasks` | 项目 · Spec | 把 plan 拆成可执行 `tasks.md` | 有 plan、要任务清单 | 「把 plan 拆成 tasks.md」 |
| `speckit-implement` | 项目 · Spec | 按 `tasks.md` 执行实现 | 有 tasks、开始编码 | 「implement tasks.md 第 1–3 项」 |

> **注意：** 仅在当前 workspace 子目录存在 `.specify/` 或 `specs/` 时完整生效；见 `e:\app\.cursor\rules\sdd-trigger.mdc`。

---

## 五、内容运营 / 起号

**路径：** `%USERPROFILE%\.cursor\skills\`  
**属性：** 个人全局 · 中文 · 合规起号方法论（**非**平台 API 对接）  
**来源：** [chenjin-cmd/agent-skills-launch-pack_](https://github.com/chenjin-cmd/agent-skills-launch-pack_)

| 名称 | 属性 | 能力 | 如何调用 | 示例 |
|------|------|------|----------|------|
| `wechat-account-launch-expert` | 全局 · 公众号 | 定位、对标、选题库、文章简报、30 天日历、周复盘 | 公众号起号、流量主、对标账号 | 「用 wechat-account-launch-expert 做高中家长赛道 30 天计划」 |
| `xiaohongshu-account-launch-expert` | 全局 · 小红书 | 账号定位、笔记简报、内容日历、转化、复盘 | 小红书起号、笔记选题 | 「小红书职场赛道，每周 3 篇，出内容日历」 |
| `douyin-account-launch-expert` | 全局 · 抖音 | 冷启动、3 秒钩子、9 条视频实验、合集、复盘 | 抖音新号、低播放 | 「抖音知识号 9 条视频实验方案」 |
| `x-twitter-cold-start-expert` | 全局 · X/Twitter | 中文 X 冷启动、回复区曝光、Thread、7 天计划 | X 起号、500 粉内增长 | 「X 个人 IP 冷启动 7 天执行表」 |

**边界：** 不能自动发帖、读后台、抓朋友圈；产出需人工复制到平台后台。

---

## 六、Token 效率 Caveman

**路径：** 全局 `%USERPROFILE%\.cursor\skills\` + 项目副本 `e:\app\.agents\skills\`  
**属性：** 个人全局 · 输出 Token 压缩 · 代码/报错原文不动  
**来源：** [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman)

| 名称 | 属性 | 能力 | 如何调用 | 示例 |
|------|------|------|----------|------|
| `caveman` | 全局 | 精简自然语言回答；档位 lite/full/ultra/wenyan-* | `caveman mode` / `less tokens` / `/caveman full` | 「caveman mode，帮我看这段 React 重渲染」 |
| `caveman-commit` | 全局 | 极简 Conventional Commits 提交信息 | `写 commit` / `/caveman-commit` | 「给 staged 变更写 commit message」 |
| `caveman-review` | 全局 | 一行式 PR Review：`位置: 问题. 修复.` | `review this PR` / `/caveman-review` | 「caveman review 这个 diff」 |
| `caveman-compress` | 全局 | 压缩 CLAUDE.md 等记忆文件省输入 Token | `/caveman-compress 路径` | 「compress memory file CLAUDE.md」 |
| `caveman-help` | 全局 · 一次性 | 显示 Caveman 命令速查卡 | `/caveman-help` | 「caveman help」 |
| `caveman-stats` | 全局 | 会话 Token 用量与估算节省 | `/caveman-stats` | 「/caveman-stats」 |
| `cavecrew` | 全局 | 派压缩输出的 investigator/builder/reviewer 子 Agent | `use cavecrew` / `delegate to subagent` | 「用 cavecrew investigator 找 auth 中间件在哪」 |

**关闭 Caveman：** `normal mode` / `stop caveman`

---

## 七、前端 / UI 设计

| 名称 | 属性 | 路径 | 能力 | 如何调用 | 示例 |
|------|------|------|------|----------|------|
| `design-taste-frontend` | 全局 · 反模板 | `%USERPROFILE%\.cursor\skills\` | 落地页/作品集/改版；审计优先；避免 AI  slop 审美 | 做 landing、portfolio、redesign | 「用 design-taste-frontend 重做产品首页，不要模板感」 |
| `ui-ux-pro-max` | 全局 · 设计库 | `%USERPROFILE%\.cursor\skills\` | 67 风格、96 色板、字体配对、UX 准则；可检索推荐 | 做 Web/Mobile UI、选配色/字体/组件 | 「ui-ux-pro-max：SaaS 仪表盘深色主题配色」 |

> `ui-ux-pro-max` 的 `SKILL.md` 无 YAML frontmatter，以目录名识别；依赖 Python 运行内置检索脚本。

---

## 八、知识库

| 名称 | 属性 | 路径 | 能力 | 如何调用 | 示例 |
|------|------|------|------|----------|------|
| `wiki-curator` | 全局 · **`disable-model-invocation: true`** | `%USERPROFILE%\.cursor\skills\` | 个人 Markdown Wiki：入库、分类、交叉链接、六索引；默认根目录 `e:\app\Myknowledge` | **须用户显式触发**：`整理知识库` / `@wiki-curator` / `存入wiki` | 「@wiki-curator 把这篇 CLI 笔记入库并打标签」 |

---

## 九、工程工具

| 名称 | 属性 | 路径 | 能力 | 如何调用 | 示例 |
|------|------|------|------|----------|------|
| `project-scaffold` | 全局 · 中文 | `%USERPROFILE%\.cursor\skills\` | 前后端分离脚手架：认证、权限、API、状态管理 | 新建项目、初始化结构 | 「用 project-scaffold 搭一个 FastAPI + React 管理后台」 |
| `pyinstaller-troubleshooting` | 全局 · 中文 | `%USERPROFILE%\.cursor\skills\` | exe 缺模块、依赖错误、打包调试 | PyInstaller 打包失败 | 「打包后 exe 报 No module named xxx」 |

---

## 十、Cursor 内置（skills-cursor）

**路径：** `%USERPROFILE%\.cursor\skills-cursor\`  
**属性：** Cursor 官方 · 部分仅 `/slash` 或显式触发

| 名称 | 属性 | 能力 | 如何调用 | 示例 |
|------|------|------|----------|------|
| `review-bugbot` | 内置 | 启动 Bugbot 子 Agent 审查代码变更 | `/review-bugbot` 或明确要求 Bugbot review | 「/review-bugbot 审查未提交变更」 |
| `review-security` | 内置 | 启动 Security Review 子 Agent | 明确要求 security review | 「security review 这次 diff」 |
| `review` | 内置 · `disable-model-invocation` | 让用户选择 Bugbot 或 Security Review | `/review` | 「/review」 |
| `canvas` | 内置 | 生成可交互 React Canvas（图表、审计、时间线等） | 产出适合可视化时 Agent 自动使用 | 「把这次 billing 调查做成 canvas」 |
| `create-skill` | 内置 | 编写 Cursor Agent Skill 的规范与模板 | 创建/修改 Skill | 「帮我写一个 Skill 管 SQL 迁移」 |
| `create-rule` | 内置 | 创建 `.cursor/rules/`、`RULE.md`、`AGENTS.md` | 建规则、编码规范 | 「为 XDFAI 加一条数据库 DDL 规则」 |
| `create-hook` | 内置 | 创建 `hooks.json` 与 Hook 脚本 | 自动化 Agent 事件 | 「写一个 hook 在提交前跑 lint」 |
| `create-subagent` | 内置 · `disable-model-invocation` | 创建自定义 subagent 定义 | 建专用子 Agent | 「创建一个 code-reviewer subagent」 |
| `migrate-to-skills` | 内置 · `disable-model-invocation` | 把 rules/commands 迁移为 Skill 格式 | 迁移 .mdc / slash commands | 「把 .cursor/rules/foo.mdc 迁成 Skill」 |
| `automate` | 内置 · `environments: local` | 创建 Cursor Automations | 建自动化工作流 | 「创建一个每天跑测试的 automation」 |
| `sdk` | 内置 | Cursor SDK（`@cursor/sdk` / `cursor-sdk`）集成指南 | 提到 Agent.create、CI 调 Agent 等 | 「用 cursor-sdk 在 GitHub Action 里跑 Agent」 |
| `babysit` | 内置 | PR 评论 triage、冲突、CI 循环修复至可合并 | PR 卡住、CI 红 | 「babysit 这个 PR 直到 CI 绿」 |
| `split-to-prs` | 内置 | 把大改动拆成多个小 PR | 变更太大难 review | 「把当前分支拆成 3 个小 PR」 |
| `loop` | 内置 · cloud 禁用 | 定时重复执行 prompt/skill | `/loop 5m /foo` | 「/loop 10m 检查 CI 状态」 |
| `shell` | 内置 · `disable-model-invocation` | 将 `/shell` 后文本作为 shell 命令执行 | `/shell git status` | 「/shell npm test」 |
| `statusline` | 内置 | 配置 CLI 自定义 status line | 提到 statusline | 「自定义 CLI 底部状态栏」 |
| `update-cursor-settings` | 内置 | 修改 `settings.json` | 改主题、字体、format on save | 「把 Cursor 字体改成 14px」 |
| `update-cli-config` | 内置 | 修改 `~/.cursor/cli-config.json` | CLI 权限、vim 模式、sandbox | 「CLI 改成 auto-approve 读文件」 |
| `onboard` | 内置 · `disable-model-invocation` | Cursor 新手引导与首目标路由 | `/onboard` | 「/onboard」 |

---

## 十一、重复与优先级说明

| 情况 | 说明 |
|------|------|
| `e:\app\.agents\skills\caveman*` | 与全局 Caveman 7 件套**内容相同**；官方 `npx skills add` 安装时写入项目目录 |
| 全局 vs 项目同名 Skill | 当前 **无** 全局与 `e:\app\.cursor\skills` 重名；Spec Kit 仅项目级 |
| `wiki-curator` | 设 `disable-model-invocation: true`，Agent **不会**自动调用，须用户点名 |
| Superpowers | Agent 应在任务可能匹配时**主动 Read**，不必等用户 @ |

---

## 十二、推荐组合速查

| 场景 | 推荐 Skill 链 |
|------|----------------|
| 新功能（大） | `brainstorming` → `writing-plans` → `test-driven-development` → `verification-before-completion` |
| Spec Kit 项目 | `speckit-specify` → `speckit-clarify` → `speckit-plan` → `speckit-tasks` → `speckit-implement` |
| 公众号起号 | `wechat-account-launch-expert` → 人工后台发布 → 一周后同 Skill 周复盘 |
| 省 Token 写代码 | `caveman` + 需要时代 `cavecrew` 委派子任务 |
| 做 landing 页 | `design-taste-frontend` + 可选 `ui-ux-pro-max` 查配色 |
| 整理笔记 | `@wiki-curator` + `e:\app\Myknowledge` |
| 合并前把关 | `verification-before-completion` → `review-bugbot` 或 `review-security` |

---

## 十三、维护命令

```powershell
# 列出个人全局 Skills
dir $env:USERPROFILE\.cursor\skills

# 列出项目 Skills
dir e:\app\.cursor\skills

# 重新安装 Caveman（仅 Cursor）
npx -y github:JuliusBrussee/caveman -- --only cursor --non-interactive

# 重新安装起号四件套（复制到全局）
Copy-Item -Recurse -Force "e:\app\vendor\agent-skills-launch-pack_\skills\*" "$env:USERPROFILE\.cursor\skills\"
```

---

## 附录：统计

| 作用域 | Skill 数（去重） |
|--------|------------------|
| 个人全局 `%USERPROFILE%\.cursor\skills\` | **30** |
| 项目 `e:\app\.cursor\skills\` | **7**（6 Spec Kit + 1 ui-ux 副本见全局） |
| 项目 `e:\app\.agents\skills\` | **7**（Caveman 副本，与全局重复） |
| Cursor 内置 `skills-cursor\` | **19** |
| **合计（按名称去重）** | **约 56** |

*ui-ux-pro-max 在全局与项目各有一份时，计为 1 个 Skill。*
