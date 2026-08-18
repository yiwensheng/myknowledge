# 易知 命令行使用手册（yws）

本文档说明如何通过 **`yws.bat`** 在终端管理知识库。GUI 一键启动请用 [`启动易知.bat`](启动易知.bat) 或 [`启动Myknowledge.bat`](启动Myknowledge.bat)。

---

## 1. 环境与 PATH

### 1.1 前置条件

| 组件 | 要求 |
|------|------|
| Python | 3.10+，命令名 `python` |
| 依赖 | `pip install -r requirements.txt` |
| 知识库目录 | 默认 `e:\app\Myknowledge` |

### 1.2 配置 `.env`（LLM 提问 / 产出）

```powershell
cd e:\app\Myknowledge
copy .env.example .env
notepad .env
```

关键项：

```env
MYKNOWLEDGE_LLM_API_BASE=https://api.emmm204.site:4170/v1
MYKNOWLEDGE_LLM_API_KEY=你的密钥
MYKNOWLEDGE_LLM_MODEL=qwen3.6
MYKNOWLEDGE_LLM_TEMPERATURE_ASK=0.15
```

未配置 API Key 时：**查询 / 列表 / ingest** 仍可用；**ask / produce** 无法 LLM 合成。

### 1.3 加入 PATH（任意目录运行 yws）

**推荐（二选一）：**

**方式 A — 只加易知项目目录（标准做法）**

永久写入用户 PATH（PowerShell，**不会**像 `setx` 那样截断超长 PATH）：

```powershell
$dir = "e:\app\Myknowledge"
$userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($userPath -notlike "*$dir*") {
  [Environment]::SetEnvironmentVariable("PATH", "$userPath;$dir", "User")
}
```

**方式 B — 已把 `E:\app` 加入 PATH 时**

仓库根目录已有 **`e:\app\yws.bat`** 转发脚本，**无需再改 PATH**，新开终端后直接：

```powershell
yws list
```

**当前终端临时生效（改 PATH 后未重开窗口时）：**

```powershell
$env:PATH = "e:\app\Myknowledge;" + $env:PATH
# 或（方式 B）
$env:PATH = "e:\app;" + $env:PATH
```

**⚠ 常见踩坑**

| 问题 | 原因 | 处理 |
|------|------|------|
| 仍提示「不是内部或外部命令」 | 改 PATH 后**未关闭并重新打开** CMD / PowerShell | 关掉旧窗口，新开一个再试 |
| `setx PATH ...` 后其它命令也找不到 | `setx` 只写用户 PATH，且超过 ~1024 字符会**截断** | 用上面 `[Environment]::SetEnvironmentVariable` 重写；勿用 `setx PATH "%PATH%;..."` |
| 加了 `yws.bat` 文件路径 | PATH 只能加**目录**，不能加 `.bat` 文件 | 改为 `e:\app\Myknowledge` 或 `e:\app` |
| 本机路径不是 `e:\app` | 文档示例路径与安装位置不一致 | 把 `$dir` 换成你实际的易知（`Myknowledge`）文件夹 |

验证：

```powershell
where yws          # 应显示 ...\yws.bat
yws list
```

**不推荐：** `setx PATH "$env:PATH;e:\app\Myknowledge"`（易截断或写错作用域）。

### 1.4 不加入 PATH 的用法

在 `e:\app\Myknowledge` 目录下：

```powershell
.\yws.bat ask "你的问题"
```

或绝对路径：

```powershell
e:\app\Myknowledge\yws.bat list
```

---

## 2. 命令总览

| 命令 | 作用 |
|------|------|
| `yws init` | 初始化目录树、模板、索引 |
| `yws ask "问题"` | RAG 检索 + LLM 流式回答（HTML，终端去标签显示） |
| `yws query 关键词` | 关键词搜索 wiki 条目 |
| `yws query 关键词 --rag` | RAG 语义片段检索 |
| `yws produce "主题"` | 基于库内资料产出 Markdown |
| `yws produce "主题" --wiki` | 产出并写入 wiki（draft） |
| `yws list` | 列出知识条目 |
| `yws add --title "标题" ...` | 新增条目 |
| `yws delete concepts/xxx.md` | 删除条目 |
| `yws url "https://..."` | 抓取网页并本地化入库（sources + RAG） |
| `yws ingest` | 整理 inbox 内所有待处理文件 |
| `yws index` | 重建 wiki 索引 + RAG（含向量 embedding） |
| `yws rag status` | 查看 RAG 模式、片段数、向量库、AnythingLLM 外联 |
| `yws rag rebuild` | 仅重建 `.rag/`（chunks + embeddings.db） |
| `yws watch` | 后台监视 inbox/资产，自动 ingest |
| `yws gui` | 启动 Electron 图形界面 |
| `yws skill list` | 列出 Skills |
| `yws skill run <name>` | 执行 Skill 工作流 |
| `yws loop run` | Loop Engineering 知识进化循环 |
| `yws loop status` | 循环状态与待办 |

---

## 3. 初始化

```powershell
cd e:\app\Myknowledge
pip install -r requirements.txt
copy .env.example .env
yws init
```

`init` 会创建：

```
inbox/  concepts/  entities/  sources/  comparisons/
notes/  templates/  index/  archive/  output/  assets/
purpose.md  .rag/  .wiki-cache.json
```

---

## 4. 导入资料

### 4.1 支持格式

pdf · ppt · pptx · xls · xlsx · doc · docx · txt · md · png · jpg · mp3 · mp4

### 4.2 导入方式

**方式 A：拖放文件**

将文件复制到：

```
e:\app\Myknowledge\inbox\
```

然后：

```powershell
yws ingest
```

**方式 B：GUI 上传**

双击 `启动易知.bat` →「导入资料」Tab → 选择文件 → 上传并入库。

**方式 C：自动监视（无 GUI）**

```powershell
yws watch
```

保持窗口运行；新文件进入 `inbox/` 或 `assets/` 会自动提取并更新 RAG。

---

## 5. 提问（ask）

基于知识库 RAG 检索，**只许使用库内片段作答**，默认**流式输出**。

```powershell
yws ask "知识进化四闭环是什么"
```

### 参数

| 参数 | 说明 | 默认 |
|------|------|------|
| `question` | 问题文本 | （必填） |
| `--top N` | RAG 检索片段数 | 5 |
| `--no-stream` | 关闭流式，一次性输出 | 默认流式开启 |
| `--json` | 输出 JSON（含 `answer_html`） | 关闭 |
| `--session ID` | 指定连续对话会话 ID | CLI 自动维护 |
| `--new-session` | 开始新会话 | 关闭 |
| `--no-remember` | 不带上文（单次提问） | 关闭 |
| `--no-archive` | 有依据时不写入 `notes/qa/` | 关闭 |

### 示例

```powershell
# 流式打印（默认）
yws ask "易知支持哪些文件格式"

# JSON 给脚本消费
yws ask "四闭环" --json --no-stream

# 增加检索片段数
yws ask "自我进化知识库架构" --top 8

# 连续追问（默认记住 CLI 会话）
yws ask "第一个问题"
yws ask "展开刚才第二点"

# 新会话 / 不归档
yws ask "问题" --new-session --no-archive
```

### 无库内命中时

不会调用大模型乱答，直接返回：

> 知识库中暂无足够信息，无法基于库内事实回答该问题。

---

## 6. 查询（query）

### 6.1 关键词搜索（wiki 条目）

```powershell
yws query 四闭环
yws query 知识管理 --type concept
yws list --type source
```

`query` 与 `list` 区别：

- `query`：按**内容关键词**打分排序
- `list`：列出全部（可按 `--type` 过滤）

### 6.2 RAG 片段检索

```powershell
yws query RAG --rag
yws query "ingest 自动化" --rag --top 5
yws query 炼钢 --rag --json
```

| 参数 | 说明 |
|------|------|
| `--rag` | 启用 RAG 片段模式（否则为条目关键词模式） |
| `--type` | 过滤条目类型：concept / entity / source / comparison / note |
| `--top N` | 返回条数上限 |
| `--json` | JSON 输出 |

### 6.3 RAG 状态与混合检索

默认 **hybrid**：本地词频 + OpenAI 兼容 embedding（`.rag/embeddings.db`）。

```powershell
yws rag status
yws rag rebuild          # 等同 refresh，跳过 index/*.md 页面生成
```

`.env` 关键项见 `.env.example` 中 `MYKNOWLEDGE_RAG_MODE`、`MYKNOWLEDGE_EMBEDDING_*`、`MYKNOWLEDGE_ANYTHINGLLM_*`。

| 模式 | 说明 |
|------|------|
| `keyword` | 仅 TF 词频（旧行为） |
| `vector` | 仅向量相似度 |
| `hybrid` | 词频 + 向量加权（默认） |
| `external` | 仅 AnythingLLM vector-search |

`MYKNOWLEDGE_ANYTHINGLLM_AUGMENT=1`：hybrid 本地结果外再合并外联片段；`CHAT_FALLBACK=1`：本地无命中时走 workspace query chat。

---

## 7. 产出新知（produce）

根据库内 RAG 片段 + 本地大模型，生成结构化知识（Markdown）。

```powershell
yws produce "自我进化知识库的使用方法"
```

输出默认保存到 `output/主题-日期.md`。

### 参数

| 参数 | 说明 |
|------|------|
| `topic` | 写作主题 |
| `--wiki` | 产出后直接写入 wiki（`draft` 状态） |
| `--out 路径.md` | 指定输出文件 |
| `--top N` | RAG 参考片段数（默认 8） |
| `--json` | JSON 输出（含 `wiki_page` 若 `--wiki`） |

### 示例

```powershell
# 仅生成文件到 output/
yws produce "Markdown wiki 与 Notion 对比"

# 产出并入库
yws produce "知识进化四闭环" --wiki

# 指定路径
yws produce "测试" --out D:\temp\test.md
```

人设与产出结构见 `prompts/persona.md`、`prompts/produce.md`。

---

## 8. 条目管理（CRUD）

### 8.1 列表

```powershell
yws list
yws list --type concept
yws list --no-inbox
yws list --json
```

### 8.2 新增

```powershell
yws add --type note --title "会议记录" --body "# 会议\n\n要点..."
yws add --type concept --title "示例概念" --file D:\note.md --tag 知识管理 --status draft
```

| 参数 | 说明 |
|------|------|
| `--type` | concept / entity / source / comparison / note |
| `--title` | 标题（必填） |
| `--body` | 正文 Markdown |
| `--file` | 从文件读取正文 |
| `--tag` | 标签（可多次指定） |
| `--status` | draft / refined / archived |

### 8.3 删除

```powershell
yws delete notes/会议记录.md
```

路径为相对 wiki 根目录，可用 `yws list` 查看。

### 8.4 URL 入库

给定网页地址，自动抓取正文、保存本地化 Markdown 到 `assets/documents/urls/`，并写入 `sources/` 条目后重建 RAG。

```powershell
yws url "https://example.com/article"
yws url "https://example.com/article" --force   # 忽略去重，重新抓取
yws url "https://example.com/article" --json
```

抓取顺序：**baoyu-url-to-markdown**（需本机 `bun`）→ **Jina Reader** → 基础 HTML 提取。

同一 URL 默认只入库一次（记录在 wiki 根目录 `.wiki-cache.json`）。

GUI「更新」Tab 也提供 URL 输入框。

### 8.5 编辑

命令行无交互编辑器；请用：

- **GUI**「列表」Tab，或
- **Obsidian** 打开 `e:\app\Myknowledge` 直接改 `.md`

改完后执行：

```powershell
yws index
```

---

## 9. 索引与维护

```powershell
# 整理 inbox 内全部待处理文件
yws ingest

# 重建 index/*.md + .rag/chunks.json
yws index

# 初始化（目录缺失时）
yws init
```

建议节奏：

- 批量丢文件后：`yws ingest`
- 手改 wiki 正文后：`yws index`
- 长期后台：`yws watch` 或开着 GUI

---

## 10. 图形界面

```powershell
# 方式 1：双击（推荐）
启动易知.bat

# 方式 2：命令行
yws gui
yws-gui.bat
```

GUI 功能：提问（流式 HTML）· 查询 · 列表 CRUD · 产出新知 · 多格式上传。

---

## 11. 目录与索引文件

| 路径 | 说明 |
|------|------|
| `inbox/` | 待整理原始资料 |
| `concepts/` `entities/` `sources/` `comparisons/` `notes/` | 结构化知识 |
| `assets/` | 原文件存档 + 提取文本 |
| `index/stats.md` 等 | 自动索引（勿手改） |
| `.rag/chunks.json` | RAG 片段索引 |
| `.rag/embeddings.db` | 向量 embedding（hybrid/vector 模式） |
| `output/` | produce 产出 |
| `prompts/` | LLM 人设与任务提示词 |

---

## 12. 常见问题

### `yws` 不是内部或外部命令

1. **先关旧终端，新开 CMD/PowerShell**（改 PATH 后必须重开）。
2. 执行 `where yws`：无输出则 PATH 未生效。
3. **任选其一：**
   - 永久加目录：`e:\app\Myknowledge`（见 **§1.3 方式 A**）
   - 或确保 `E:\app` 在 PATH 后直接用根目录 **`e:\app\yws.bat`** 转发（**§1.3 方式 B**）
   - 临时：`e:\app\Myknowledge\yws.bat list`
4. 若曾用 `setx` 改 PATH 导致其它命令也丢失，用系统「环境变量」界面检查用户 PATH 是否被截断。

### ask 回答「暂无足够信息」

库内无相关 RAG 命中。把资料放入 `inbox/` → `yws ingest` → 再提问。

### produce / ask 报 LLM 错误

检查 `.env` 中 `MYKNOWLEDGE_LLM_API_BASE`、`API_KEY`、`MODEL` 是否正确；网络能否访问该端点。

### 端口 18765 被占用

在 `.env` 设置 `MYKNOWLEDGE_PORT=18766`，并重启 GUI。

### 旧版 .doc / .ppt

建议转为 docx / pptx 后再导入；或安装 LibreOffice 辅助转换。

---

## 13. 典型工作流

```powershell
# 1. 丢资料
copy D:\资料\*.pdf e:\app\Myknowledge\inbox\

# 2. 入库 + RAG
yws ingest

# 3. 提问
yws ask "这份 PDF 讲了什么要点"

# 4. 产出新知并入库
yws produce "总结：XX 主题" --wiki

# 5. 查看
yws list --type source
```

---

## 14. 相关文件

- 项目说明：[README.md](README.md)
- GUI 启动：[`启动易知.bat`](启动易知.bat) · [`启动Myknowledge.bat`](启动Myknowledge.bat)
- CLI 入口：[`yws.bat`](yws.bat)
- 详细使用说明：[操作手册.md](操作手册.md)
