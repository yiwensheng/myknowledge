# B 站字幕入库 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 粘贴 B 站链接经「保存网页」字幕优先入库并走现有 RAG；安装包内置 yt-dlp；无字幕明确失败。

**Architecture:** `fetch_url` 识别 bilibili/b23 → `bilibili_fetch` 调 yt-dlp 仅取字幕与元数据 → 复用 `ingest_url` 落盘与增量索引。`setup_optional_tools` 将 yt-dlp.exe 打入 `third_party/yt-dlp/`。

**Tech Stack:** Python 3、yt-dlp（独立 exe）、现有 FastAPI URL job、Electron 导入页（尽量不改 UI）。

**Spec:** `docs/superpowers/specs/2026-07-18-bilibili-subtitle-ingest-design.md`

---

## File map

| File | Responsibility |
|------|----------------|
| `lib/runtime_tools.py` | `find_ytdlp()` |
| `lib/bilibili_fetch.py` | 识别 URL、调 yt-dlp、解析 VTT/JSON3/SRV、生成 Markdown |
| `lib/url_fetch.py` | bilibili 分流 |
| `scripts/setup_optional_tools.py` | 打包 yt-dlp |
| `scripts/build-portable.ps1` / `YizhiStart.vbs` | PATH 含 yt-dlp |
| `tests/test_bilibili_fetch.py` | 单元测试 |

---

### Task 1: find_ytdlp

- [x] **Step 1:** 在 `lib/runtime_tools.py` 增加 `bundled_ytdlp_path` / `find_ytdlp`（env → third_party → which）
- [x] **Step 2:** 快速手工验证函数可 import

### Task 2: bilibili_fetch + 测试

- [x] **Step 1:** 写 `tests/test_bilibili_fetch.py`：`is_bilibili_url`、字幕优先级、无字幕报错文案（mock subprocess）
- [x] **Step 2:** 实现 `lib/bilibili_fetch.py` 使测试通过
- [x] **Step 3:** `python -m pytest tests/test_bilibili_fetch.py -q`

### Task 3: 接入 fetch_url

- [x] **Step 1:** `fetch_url` 开头若 `is_bilibili_url` 则 `fetch_bilibili` → `FetchedPage`
- [x] **Step 2:** progress 回调相位文案「正在获取 B 站字幕…」

### Task 4: 打包 yt-dlp

- [x] **Step 1:** `setup_optional_tools.py` 增加 `install_ytdlp`（复制本机或 GitHub release `yt-dlp.exe`）
- [x] **Step 2:** `main()` 调用；`build-portable` PATH 与 `YizhiStart.vbs` PATH 增加 `third_party\yt-dlp`
- [x] **Step 3:** 开发机跑一次 `python scripts/setup_optional_tools.py`，确认 `third_party/yt-dlp/yt-dlp.exe` 存在

### Task 5: 文档与更新记录

- [x] **Step 1:** `docs/更新记录.md` 追加条目（真实北京时间）
- [x] **Step 2:** 如有 FAQ/导入说明一句「支持 B 站有字幕视频」

### Task 6: 手工冒烟（有网时）

- [ ] **Step 1:** 用已知有字幕 BV 调 `ingest_url` 或 GUI「保存网页」
- [ ] **Step 2:** 确认笔记与检索库有内容
