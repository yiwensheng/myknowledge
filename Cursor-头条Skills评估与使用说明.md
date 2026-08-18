# 今日头条 Skill 评估与 Cursor 全局安装说明

> 评估日期：2026-07-30（持续追加头条篇）  
> 安装位置：`%USERPROFILE%\.cursor\skills\`（Cursor 个人全局）  
> 源码缓存：`e:\app\vendor\mattpocock-skills\`、`e:\app\vendor\khazix-skills\`、`e:\app\vendor\Flow2Spec\`、`e:\app\vendor\no-ai-slop\`、`e:\app\vendor\last30days-skill\`、`e:\app\vendor\human-writing\`、`e:\app\vendor\loopx\`、`e:\app\vendor\graph-engineering\`、`e:\app\vendor\dzs-prompt-framework\`、`e:\app\vendor\basb-writing\`、`e:\app\vendor\Humanizer-zh\`、`e:\app\vendor\shuorenhua\`、`e:\app\vendor\de-ai-prompt-enhancer\`

---

## 一、结论总表

| 文章 | 上游 | 对 Cursor 是否有用 | 本次处理 |
|------|------|-------------------|----------|
| [Matt Pocock Skills](https://www.toutiao.com/article/7667757237913272874/) | [mattpocock/skills](https://github.com/mattpocock/skills) | **有用**（工程纪律，防 AI 乱修乱堆） | **已安装 21 个**到全局（跳过 `ask-matt`） |
| [Leader 目标任务书](https://www.toutiao.com/w/1871919789605964/) | [KKKKhazix/khazix-skills/leader](https://github.com/KKKKhazix/khazix-skills/tree/main/leader) | **有用**（长任务防目标漂移） | **已安装 `leader`**（含 references） |
| [Create Context Graph](https://www.toutiao.com/article/7646244937129804324/) | 文中描述 ≠ 真实 npm 包 | **按文安装无用** | **未安装**（见第三节） |
| [MiMo / Memora / Flow2Spec 记忆](https://www.toutiao.com/article/7662547329391526419/) | 见下节 | **部分有用**（Flow2Spec + 轻量便签） | **已装** `f2s-*`×20 + `agent-session-memory`；Memora / 整包 MiMo **未整装** |
| [no-ai-slop 去 AI 味](https://www.toutiao.com/article/7665765295822307892/) | [shenxianpeng/no-ai-slop](https://github.com/shenxianpeng/no-ai-slop) | **有用**（文案润色） | **已安装 `no-ai-slop`**（易知写文章亦默认注入） |
| [last30days 选题灵感](https://www.toutiao.com/w/1871788301735946/) | [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill) | **有用**（近 30 天多源社区讨论） | **已安装 `last30days`**（含本机三站扩展） |
| [活人感写作](https://www.toutiao.com/article/7670371926468084234/) | [KKKKhazix/human-writing](https://github.com/KKKKhazix/human-writing) | **有用**（义理·考据·辞章；材料门槛+去模型腔） | **已装全局 Skill + `human-writing.mdc`；已写入「我读史记」闭环** |
| [LoopX 长程控制平面](https://www.toutiao.com/article/7672039193704825386/) | [huangruiteng/loopx](https://github.com/huangruiteng/loopx) | **有用**（跨天目标/门禁/配额/证据；官方支持 Cursor） | **已装 CLI + Cursor Skills/MCP + `loopx.mdc`** |
| [Graph Engineering 智能体新范式](https://www.toutiao.com/article/7671966755032990260/) | **无上游仓库**（概念文） | **有用（决策框架）**；不提供可 pip/clone 的运行时 | **已本地化为全局 `graph-engineering`** |
| [Arise UI「偷偷用」](https://www.toutiao.com/article/7671845524336607784/) | [Amitgajare2/ariseui](https://github.com/Amitgajare2/ariseui)（shadcn registry） | **对 GUI 设计能力几乎无提高**；文是动效营销且安装写法错误 | **未装全局 Skill**（见第三节丙） |
| [用AI准确提取文档一切（ParseBench prompt）](https://www.toutiao.com/article/7672221541857378850/) | 文述 gaik MultimodalParser / LlamaIndex ParseBench 思路；**无必须 pip 的上游** | **对易知文档解析有用**（HTML 表、bbox 契约、跨页合表） | **已本地化进易知**：`lib/pdf_llm_parse.py` + 工作流「LLM 版面解析」（不装 gaik） |
| [DZS 万能提示词工程框架](https://www.toutiao.com/article/7672672682140123675/) | **无仓库**（抖知书元提示词） | **部分有用**：深度分析/战略催化；默认接管编码会拖累 | **Cursor**：全局 `dzs-prompt-framework`（须显式；**我读史记 / Articles 热点写稿规则默认叠加**）；**易知**：提问/写文章/推演（`MYKNOWLEDGE_DZS`，默认开） |
| [Tiago Forte / BASB 写作与知识管理](https://www.toutiao.com/article/7672440685642990114/) | **无仓库**（方法综述） | **有用（写作复用）**；非编码工具 | **①** 两套写稿规则加「思想群岛」；**②** 易知写文章/蒸馏（`MYKNOWLEDGE_BASB`）；**③** Cursor 显式 `basb-writing` |
| [去 AI 味 10 Skills](https://www.toutiao.com/article/7673332939782029858/) | 见 §三己 | **部分有用**；十装会打架 | **只落互补三项**全局 + 写稿默认 + 易知增强包（见三己） |
| [Mnemosyne 改版 · 长记忆](https://www.toutiao.com/article/7672859422640603700/) | [zhangrui87022554/mnemosyne](https://github.com/zhangrui87022554/mnemosyne) | **对易知：理念有用，整包无用**；对 Cursor Agent 可另作本机 MCP 实验 | **不装进易知安装包**；原则吸收见规格 `docs/superpowers/specs/2026-08-12-memory-fact-versions-design.md` |

与已有 Skill 关系：

| 新装 | 已有近似 | 建议 |
|------|----------|------|
| `tdd`（Matt，强调垂直切片） | `test-driven-development`（Superpowers） | 两者可并存；写测试优先时任一点名；Matt 版更强调「一次一个红绿闭环」 |
| `diagnosing-bugs` | `systematic-debugging` | 硬 bug / 性能回归优先用 Matt；一般排查两者均可 |
| `code-review` | `requesting-code-review` / `caveman-review` | 实现收尾用 Matt `code-review`；要极简评论用 caveman-review |
| `caveman`（文中提及） | 已装 JuliusBrussee caveman | **未重复安装** |
| Create Context Graph | 本机已有 **CodeGraph MCP**（`user-codegraph`） | 继续用 CodeGraph，勿按头条文装错包 |
| `graph-engineering` | `dispatching-parallel-agents`、`leader`、`loopx`、Superpowers/SDD | **互补**：前者管「何时上图/门禁」；后几者是图的具体落点。简单活仍用单 Loop，勿为上图而上图 |
| `dzs-prompt-framework` | `grill-me`、`brainstorming`、`agent-session-memory` | **Cursor 编码须显式**；**我读史记 / Articles 热点**规则已默认叠加（静默）。易知提问/写文章/推演默认注入（`MYKNOWLEDGE_DZS`） |
| `basb-writing` | `dzs`、`human-writing`、`agent-session-memory`、易知 distill | **Cursor 须显式**。群岛/中间包/渐进摘要；写稿规则已内嵌群岛；易知 `MYKNOWLEDGE_BASB` |

---

## 二、已安装清单（Matt Pocock + Leader）

### 2.1 工程纪律（推荐日常）

| Skill | 调用方式 | 能力一句话 | 示例 Prompt |
|-------|----------|------------|-------------|
| `grill-me` | **须显式**（`disable-model-invocation`） | 死磕式追问，直到计划决策树每支清晰 | `使用 grill-me，把「智伴加 PDF 导出」问到能开工` |
| `grill-with-docs` | 显式或相关文档任务 | 同 grilling，并同步 CONTEXT.md / ADR | `grill-with-docs：讨论 RAG 架构并写 ADR` |
| `grilling` | 被 grill-me / grill-with-docs 调用 | grilling 循环本体 | 一般不必直接调 |
| `tdd` | 提「TDD / 红绿重构 / 先写测试」 | 垂直切片红→绿→重构 | `用 tdd 修这个 bug，一次只做一个用例` |
| `diagnosing-bugs` | 「diagnose / debug / 报错 / 变慢」 | 复现→最小化→假设→插桩→修复→回归 | `diagnosing-bugs：登录偶发 500` |
| `triage` | issue / 故障分类 | 状态机式给问题定类 | `triage 这批 GitHub issues` |
| `to-spec` | **须显式** | 把当前对话合成规格并落到 issue tracker | `to-spec：把刚才讨论写成 spec` |
| `to-tickets` | 计划/PRD → 可认领工单 | 拆成独立 ticket | `to-tickets：把 plan 拆成 issues` |
| `implement` | 按 spec/tickets 实现 | 驱动 tdd，收尾 code-review | `implement 按 tickets #12–14` |
| `prototype` | 一次性原型 | 终端 app 或多 UI 变体 | `prototype：三种设置页布局` |
| `improve-codebase-architecture` | 架构深化 | 基于 ADR 找改进机会 | `improve-codebase-architecture 看 OpenMAIC 嵌入` |
| `codebase-design` | 设计代码结构 | 模块边界、依赖方向 | `codebase-design：招生模块边界` |
| `domain-modeling` | 领域建模 | 语言与模型对齐 | `domain-modeling：学情分析领域词` |
| `setup-matt-pocock-skills` | 首次进项目 | 初始化 issue tracker / 文档结构 | `setup-matt-pocock-skills 初始化本仓库` |
| `wayfinder` | **须显式**（大活） | 超大工作拆成决策票地图，一次解一票 | `wayfinder：整仓换 Tauri 壳怎么走` |
| `research` | 调研选型 | 有结论的调研 | `research：Electron vs Tauri 对本项目` |
| `resolving-merge-conflicts` | 合并冲突 | 冲突解决流程 | `resolving-merge-conflicts` |
| `code-review` | 实现后审查 | 合并前审查 | `code-review 这次 diff` |

### 2.2 生产力

| Skill | 调用方式 | 能力 | 示例 |
|-------|----------|------|------|
| `handoff` | **须显式** | 压缩当前对话为交接文档，给下一 Agent | `handoff：下一会话继续做 PDF 导出` |
| `teach` | 教学讲解 | 教概念/流程 | `teach：给同事讲垂直切片 TDD` |
| `writing-great-skills` | 写 Skill | 规范写新 Skill | `writing-great-skills：写一个迁移 Skill` |

### 2.3 Leader（长任务目标焊死）

| Skill | 调用方式 | 能力 | 示例 |
|-------|----------|------|------|
| `leader` | 「写目标任务书 / brief 给 agent / 让 agent 自己跑」 | 调研→≤5 问→产出 ≤4000 字可执行目标任务书（Why/Done/Proof/Anti/Bounds/Trade…） | `用 leader：给 agent 写「瘦身安装包」任务书，要防删测试` |

**适用：** 多步骤、有验收、人暂时不盯的长任务（重构、调研报告、竞品分析）。  
**不适用：** 三步以内短活、纯闲聊、完全无终点的开放创作。

交付物通常是一段可直接粘给「执行型 Agent」的任务书；验收由你（或管理型会话）对照命令与「暗卷」抽查。

---

## 三、Create Context Graph：为何不装

头条文宣称：`pip/npm install create-context-graph` → Tree-sitter 扫仓库 → JSON/Markdown/MCP 给 Agent 查调用链，并给出「省 70% token」等数字。

本机核实：

- npm 上确有 [`create-context-graph`](https://www.npmjs.com/package/create-context-graph)，但是 **Neo4j Labs 的领域知识图谱脚手架 CLI**（接 Neo4j / LangGraph 等），**不是**文中那种「扫 Python/TS 生成代码上下文图谱」工具。
- 文中的 API / `.context-graph.yaml` / `create-context-graph analyze` 等与真实包能力**对不上**，文章很可能是 AI 拼凑或张冠李戴。

**你这边已有更贴切的能力：** Cursor MCP **`user-codegraph`**（`codegraph_context` / `codegraph_search` / `codegraph_trace`）。查符号与调用链优先用它；若 MCP 报错，先修连接，而不是按头条文安装错误包。

若真要 Neo4j 领域图谱脚手架，那是另一条线，与「Cursor 全局 Skill」无关，需单独决策。

---

## 三丙、Arise UI：为何不装成「GUI 设计」全局 Skill

原文：[今日头条 · 7671845524336607784](https://www.toutiao.com/article/7671845524336607784/)  
宣称：`import { MagneticDock } from "arise-ui"` 即可磁吸 Dock / OTP / 弹簧动效，「几分钟让产品更高级」。

### 核实

| 说法 | 事实 |
|------|------|
| npm `arise-ui` | 包存在，但是 **Vite React 模板脚手架**（readme 即 Create React+Vite），**不是**动画组件库。按文 `npm i arise-ui` **会装错**。 |
| 真实上游 | [Amitgajare2/ariseui](https://github.com/Amitgajare2/ariseui)：**shadcn 风格 registry**，按件拷源码进项目，例如 `npx shadcn add amitgajare2/ariseui/magnetic-dock`（须已有 `components.json` / Tailwind）。 |
| 能力边界 | ~十余个 **可选动效组件**（Magnetic Dock、OTP、Scroll Progress、Flickering Grid 等），**不教**版式、字体、层级、信息架构，也不替代现有 UI 库。 |

### 对 Cursor「GUI 设计」是否有提高

**基本没有。** 设计判断仍应靠本机已有：

- `design-taste-frontend` / `ui-ux-pro-max`
- workspace `design-md/<范式>/DESIGN.md`
- 前端硬规则（首屏构图、少卡片、克制动效、反紫渐变等）

把 Arise 装成「全局设计 Skill」容易诱导 Agent **处处磁吸/闪烁网格**，与上述纪律冲突，反而降质感。

### 若某 React+shadcn 项目真要某一件

在**该业务仓**按需拉取，不要全局默认注入：

```powershell
# 示例：只要磁吸 Dock（项目须已 init shadcn）
npx shadcn@latest add amitgajare2/ariseui/magnetic-dock
```

并遵守：`prefers-reduced-motion`、后台/表单页少炫技、动效服务任务不喧宾夺主。

---

## 三己、去 AI 味「10 Skills」：为何不全装

原文：[今日头条 · 7673332939782029858](https://www.toutiao.com/article/7673332939782029858/)（文首声明内容由 AI 生成）。

### 逐项判定

| # | 文中名称 | 上游/事实 | 本机处理 |
|---|----------|-----------|----------|
| 1 | humanizer | [blader/humanizer](https://github.com/blader/humanizer) 英文 | **不单装**；中文用 Humanizer-zh |
| 2 | Humanizer-zh | [op7418/Humanizer-zh](https://github.com/op7418/Humanizer-zh) | **已装全局** `humanizer-zh`；写稿默认叠加 |
| 3 | stop-slop | [hardikpandya/stop-slop](https://github.com/hardikpandya/stop-slop) | **不单装**；要点已并入 Humanizer-zh / no-ai-slop |
| 4 | taste-skill | 表述含糊，无可靠写作仓 | **不装**（勿与 `design-taste-frontend` 混淆） |
| 5 | ai-flavor-remover | 与上多重叠 | **不装** |
| 6 | shuorenhua | [MrGeDiao/shuorenhua](https://github.com/MrGeDiao/shuorenhua) | **已装全局**（含 `references/`）；写稿默认叠加 |
| 7 | nuwa-skill | 风格学习 | **不装**；易知已有写作风格学习 |
| 8 | writing-agent | 全流程写作 | **不装**；已有 wewrite / 账号闭环 |
| 9 | chatgpt-comparison-detection | 质检 | **不装**；用 `no-ai-slop` 检测模式 |
| 10 | De-AI-Prompt-Enhancer | [oubigfa/…-SKILL](https://github.com/oubigfa/de-ai-prompt-enhancer-writer-booster-skill) 之 `de-AI-writing` | **已装全局** `de-ai-writing`；易知蒸馏为默认注入 |

### 落地

- Cursor：`%USERPROFILE%\.cursor\skills\{humanizer-zh,shuorenhua,de-ai-writing}\`
- 我读史记 / Articles：规则默认叠加（**无需点名**）；史记侧 shuorenhua **不削成长句口语**
- 易知：`MYKNOWLEDGE_DE_AI_WRITING`（默认开）注入 `skills/de-ai-writing/produce-rules.md`，与 no-ai-slop / human-writing 叠加
- vendor：`e:\app\vendor\Humanizer-zh\`、`shuorenhua\`、`de-ai-prompt-enhancer\`

---

## 三乙、Agent 记忆篇（MiMo / Memora / Flow2Spec）

原文：[今日头条 · 7662547329391526419](https://www.toutiao.com/article/7662547329391526419/)  
主题：给 Agent 装「记忆」——综述三套方案，**不是**单一 Skill 安装包。

| 方案 | 上游 | 评估 | 本机处理 |
|------|------|------|----------|
| **Flow2Spec** | [Lands-1203/Flow2Spec](https://github.com/Lands-1203/Flow2Spec) | **最贴合 Cursor**：项目级 `.Knowledge/` + `f2s-*` Skills | **已复制 20 个 `f2s-*` 到全局**；源码 `e:\app\vendor\Flow2Spec\` |
| **MiMo Code** | [XiaomiMiMo/MiMo-Code](https://github.com/XiaomiMiMo/MiMo-Code) | 完整终端 Agent，非 Cursor Skill 包 | **提炼**为全局 Skill `agent-session-memory`（MEMORY / checkpoint / progress） |
| **Memora** | [microsoft/Memora](https://github.com/microsoft/Memora) | 研究向检索/记忆框架 | **未整包装成 Skill**（可另接 MCP/服务，勿当「一条命令 Skill」） |

### 怎么用：轻量记忆（立刻可用）

任意仓库：

```text
使用 agent-session-memory：为本项目建 MEMORY.md / checkpoint.md / progress.md
```

或：`写检查点` / `更新项目记忆` / `续上上次会话`。  
与已有 `handoff` 互补：handoff 交接对话；本 Skill 固化跨会话便签文件。

### 怎么用：Flow2Spec（要可路由知识库时）

1. **在目标业务仓库初始化**（仅装全局 Skills 不够，还要项目骨架）：

```powershell
cd <你的业务仓库根>
npx @double-codeing/flow2spec@latest init
```

会写入 `.Knowledge/`、`flow2spec.config.json`，并同步规则/Skills（若已全局有 `f2s-*`，仍以项目内为准）。

2. **常用触发**：

| Skill | 用途 | 示例 |
|-------|------|------|
| `f2s-req-clarify` | 需求澄清到无歧义 | `f2s-req-clarify：评价模板批量重评分` |
| `f2s-req-tech` | 出可落地技术方案 → `req-docs/` | `f2s-req-tech` |
| `f2s-kb-feat` | 新能力 + 同步知识库 | `f2s-kb-feat：加导出 PDF` |
| `f2s-kb-fix` | 修 bug + 更正 topic | `f2s-kb-fix：登录偶发 500` |
| `f2s-git-commit` | 提交前检查 topic 覆盖 | `f2s-git-commit` |
| `f2s-kb-add` / `f2s-doc-final` | 文档入知识库 | `f2s-kb-add：把现有模块写进 Knowledge` |

3. **选型建议**：日常防失忆 → `agent-session-memory`；大仓、硬约束多、要「只读 300 行」→ Flow2Spec；符号调用链 → 继续用 **CodeGraph MCP**（不是 Memora）。

### 三乙附、Mnemosyne 改版（2026-08-12）

原文：[今日头条 · 7672859422640603700](https://www.toutiao.com/article/7672859422640603700/)  
主题：SQLite+WAL、事实版本链、时序推理、MCP 多工具共享、多项目隔离。

| 判断 | 说明 |
|------|------|
| **易知产品** | 已有 `.memory/memory.db` + distill；**不** vendor Mnemosyne，避免两套记忆模型 |
| **可吸收** | 事实 `current/superseded` 版本链、写入不扫库冲突、按 folder/project 隔离、时序 `since` 查询 |
| **Cursor** | 若要给编码 Agent 用，本机单独跑 MCP，与易知安装包解耦 |
| **落地** | 最小设计已写：`docs/superpowers/specs/2026-08-12-memory-fact-versions-design.md`（有痛点再实现一期） |

### 更新 Flow2Spec Skills

```powershell
git -C e:\app\vendor\Flow2Spec pull
Copy-Item -Recurse -Force e:\app\vendor\Flow2Spec\.cursor\skills\* $env:USERPROFILE\.cursor\skills\
```

---

## 三丙、last30days（近 30 天社区选题）

原文：[今日头条 · w/1871788301735946](https://www.toutiao.com/w/1871788301735946/)  
上游：[mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill)

**能力：** 并行检索 Reddit / X / YouTube / TikTok / HN / Polymarket / GitHub / Web，以及**本机扩展**的今日头条 / 微博 / 彭博（`site:` 站点检索），按互动量打分，合成 brief。

**本机：** 已复制到 `%USERPROFILE%\.cursor\skills\last30days\`（含 `scripts/` 引擎）；vendor：`e:\app\vendor\last30days-skill\`。扩展说明见 Skill 内 `LOCAL_EXTENSIONS.md`。

### 用法（Cursor Agent）

```text
使用 last30days：AI 视频工具
```

或：`/last30days nvidia earnings reaction`、`last30days 用户吐槽 Cursor 哪里烦`  
仅彭博：`last30days Cursor --search bloomberg`；仅微博：`--search 微博`

**零配置即可用：** Reddit、HN、Polymarket、GitHub，以及本机扩展的 **Toutiao / Weibo / Bloomberg**（走 web/keyless `site:`，覆盖面弱于原生源）。  
**可选解锁更多源：** 首次按 Skill 内 setup / doctor；可配 `SCRAPECREATORS_API_KEY`、X 的 `AUTH_TOKEN`/`CT0` 等（见上游 README）。  
**关掉三站扩展：** `EXCLUDE_SOURCES=toutiao,weibo,bloomberg`

**依赖：** 本机 Python 3.12+（Skill 会自检；有 `uv` 时可自动装解释器）、Node（部分源）。引擎入口：`skills/last30days/scripts/last30days.py`。

**健康检查：**

```text
使用 last30days doctor
```

（或按 SKILL 内 `--diagnose` / doctor 流程）

### 更新

```powershell
git -C e:\app\vendor\last30days-skill pull
# 注意：上游 pull 后须确认 LOCAL_EXTENSIONS.md / site_sources.py 仍在，再覆盖全局
Remove-Item -Recurse -Force $env:USERPROFILE\.cursor\skills\last30days
Copy-Item -Recurse -Force e:\app\vendor\last30days-skill\skills\last30days $env:USERPROFILE\.cursor\skills\last30days
# 或官方：npx skills add mvanhorn/last30days-skill -g（会丢掉本机三站扩展）
```

---

## 三丁、LoopX（长程 Agent 控制平面）

原文：[今日头条 · 7672039193704825386](https://www.toutiao.com/article/7672039193704825386/)  
上游：[huangruiteng/loopx](https://github.com/huangruiteng/loopx)

**能力：** 不替代 Cursor，给长任务加「控制平面」——目标、待办认领、人工门禁、证据、配额、交接；状态在项目 `.loopx/`。

**本机已装：**

- CLI：`loopx`（`pip install -e e:\app\vendor\loopx`）
- Cursor Skills：`loopx`、`loopx-project`、`loopx-pr-*`、`loop-global-*` 等
- MCP：`mcp.json` → `loopx`（首次在 Cursor 设置里启用/批准）
- 规则：`%USERPROFILE%\.cursor\rules\loopx.mdc`

### 用法

```text
把当前项目接到 LoopX，并用 loopx 启动目标：……
```

或在业务仓：

```powershell
loopx doctor
cd <业务仓库>
loopx connect
loopx start-goal --guided --project . --goal-text "……"
loopx status
loopx quota should-run
```

更新：

```powershell
git -C e:\app\vendor\loopx pull
pip install -e e:\app\vendor\loopx
loopx slash-commands --install --surface cursor
```

---

## 四、推荐工作流（组合用法）

### 小功能 / Bug

```text
1. grill-me 或 brainstorming（对齐要什么）
2. tdd 或 test-driven-development（垂直切片实现）
3. diagnosing-bugs（若跑不通）
4. verification-before-completion / code-review
```

### 大功能 / 跨模块

```text
1. grill-with-docs 或 wayfinder（大地图）
2. to-spec → to-tickets
3. implement（按 ticket，内嵌 tdd）
4. handoff（会话太长时交接下一轮）
```

### 丢给「无人值守」执行 Agent

```text
1. 使用 leader，把需求焊成目标任务书
2. 新开 Agent，粘贴任务书执行（勿中途改目标）
3. 回来后让同一会话（管理者角色）按书验收
```

### 省 Token 写代码

```text
caveman mode + 需要时 leader/grill-me（目标清晰后精简执行）
```

### 防失忆 / 长会话

```text
短：agent-session-memory（写检查点 / MEMORY.md）
长仓：flow2spec init → f2s-kb-feat / f2s-kb-fix
跨天工程目标：LoopX（connect → start-goal → quota should-run）
交接：handoff + 指出记忆/LoopX 状态路径
```

### 跨天长任务（LoopX）

```text
1. 业务仓根：loopx connect（或让 Agent「把本项目接到 LoopX」）
2. 使用 loopx / loopx-project：启动目标文案
3. 每轮切片前 quota should-run；门禁处停问人
4. 结束 refresh-state；勿提交 .loopx/
```

### 复杂编排 / 要不要上「图」（Graph Engineering）

```text
使用 graph-engineering：先判定 Loop / Subagent / 动态 Multi-Agent / 显式 Graph
→ 显式图时写出节点、成功/失败边、状态存放处、门禁
→ 硬约束接 loopx gates / 人工确认 / SDD；并行探查接 Task
```

### 深度分析催化（DZS，须点名）

```text
使用 dzs-prompt-framework：激活后直接说任务
→ 战略/深度分析走深度档；写邮件等走标准档；查事实走快速档
→ 改代码别用 DZS，改用 leader / grill-me / implement
```

「我读史记」「Articles 热点」写稿：**无需点名**，规则已默认静默跑 DZS（材料关之后、动笔之前）；并须完成**思想群岛**（5～8 条）。

### BASB / 第二大脑写作（须点名，或写稿规则已内嵌）

```text
使用 basb-writing：围绕主题做群岛成文 / 中间包拆分
→ 易知写文章默认 MYKNOWLEDGE_BASB；蒸馏 Meta 对齐渐进摘要
```

### 去 AI 味文案

```text
使用 no-ai-slop + 粘贴草稿
```

### 选题 / 近 30 天舆论

```text
使用 last30days：<话题或人名>
→ 再写稿时可用 no-ai-slop / 易知「写文章」
```

---

## 五、显式触发对照（须你开口的）

下列 Skill 带 `disable-model-invocation: true`，Agent **不会**自己选用，必须点名：

- `grill-me`
- `to-spec`
- `wayfinder`
- `handoff`
- `dzs-prompt-framework`
- `basb-writing`
- （以及本机已有的 `wiki-curator` 等）

模型可自动匹配的示例：`tdd`、`diagnosing-bugs`、`leader`（描述命中时）、`implement`。

---

## 六、维护

```powershell
# 更新 Matt Skills（vendor 拉新再覆盖全局）
git -C e:\app\vendor\mattpocock-skills pull
Copy-Item -Recurse -Force e:\app\vendor\mattpocock-skills\skills\engineering\* $env:USERPROFILE\.cursor\skills\
Copy-Item -Recurse -Force e:\app\vendor\mattpocock-skills\skills\productivity\* $env:USERPROFILE\.cursor\skills\

# 更新 Leader
git -C e:\app\vendor\khazix-skills pull
Copy-Item -Recurse -Force e:\app\vendor\khazix-skills\leader $env:USERPROFILE\.cursor\skills\leader

# 官方安装器（可选，会交互选 Skill）
npx skills@latest add mattpocock/skills -a cursor
```

**注意：** 覆盖复制时不要误删本机已有的 `caveman*`、起号四件套、Superpowers 等非 Matt 目录。

---

## 七、首次试用（10 分钟）

1. 新开 Cursor Agent。  
2. 发：`使用 grill-me，帮我打磨「给 CLI.md 加一节 yws watch 排错」`。  
3. 答完追问后发：`to-spec`。  
4. 另开一窗：`用 leader 把「修复 yws watch 批处理中文乱码」写成可执行任务书`。  
5. 需要精简输出时：`caveman mode`。

---

## 相关文件

| 用途 | 路径 |
|------|------|
| 全局 Skills | `%USERPROFILE%\.cursor\skills\` |
| Matt 源码 | `e:\app\vendor\mattpocock-skills\` |
| Leader 源码 | `e:\app\vendor\khazix-skills\leader\` |
| Flow2Spec 源码 | `e:\app\vendor\Flow2Spec\` |
| no-ai-slop | `e:\app\vendor\no-ai-slop\` |
| last30days | `e:\app\vendor\last30days-skill\` |
| human-writing | `e:\app\vendor\human-writing\` |
| LoopX | `e:\app\vendor\loopx\` |
| graph-engineering | `e:\app\vendor\graph-engineering\`（概念本地化，无上游 clone） |
| dzs-prompt-framework | `e:\app\vendor\dzs-prompt-framework\`（元提示词本地化，须显式） |
| basb-writing | `e:\app\vendor\basb-writing\`（BASB 方法本地化，须显式） |
| Skills 总览（更早整理） | `e:\app\Myknowledge\Cursor-Skills-全览.md` |
