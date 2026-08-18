# 易知 · B 站字幕入库设计

> 日期：2026-07-18  
> 状态：已确认（用户同意方案 1；**yt-dlp 打入安装包**；无字幕明确失败，不做语音转写）

## 背景

参考 Chubby Skills 的「字幕优先」思路：把 B 站链接采成 Markdown，再走易知现有入库与 RAG。易知已有 URL → wiki → `upsert_page_index` 链路，缺口是平台化采集。

## 目标

1. 用户在「导入资料」粘贴 B 站链接，点「保存网页」即可入库。
2. **仅使用字幕**（优先中文，含人工/AI 字幕）；无字幕则失败并提示改粘贴文稿。
3. 成功后与普通网页相同：本地化 Markdown、`sources/` 笔记、增量 RAG。
4. **安装包内置 yt-dlp**（`third_party/yt-dlp/`），用户机无需另行安装。

## 非目标（本版）

- 语音转写（FunASR 等）
- 合集/多 P 批量、直播
- 抖音 / 小红书 / 其他短视频平台
- 默认下载视频本体（只拉字幕与元数据）

## 方案

在现有 `fetch_url` 入口识别 B 站 URL，走专用抓取器，再进入 `ingest_url` 不变的后半段。

```text
URL 框 → /api/url job
  → ingest_url → fetch_url
       ├─ bilibili / b23.tv → bilibili_fetch（yt-dlp 字幕）
       └─ 其他 → 现有网页抓取
  → analyze → save_page → upsert RAG
```

## 行为细则

| 情况 | 行为 |
|------|------|
| `bilibili.com/video/…`、`b23.tv/…` | 走字幕抓取 |
| 有字幕 | Markdown：标题、UP 主、BV/链接、字幕正文；`method=bilibili-subtitle` |
| 无字幕 / 仅空字幕 | `RuntimeError`，文案：「该视频无可用字幕，请粘贴文稿或换有字幕的视频」 |
| 无 yt-dlp（开发机未装且未打包） | 提示缺少 yt-dlp（正式包应已有） |
| 短链 b23.tv | yt-dlp 自行解析，或先跟跳转 |

字幕语言优先级：`zh-Hans` / `zh-CN` / `zh` / `ai-zh` → 其他中文变体 → 任意可用字幕（并在文首注明语言）。

## yt-dlp 打包

- 路径：`third_party/yt-dlp/yt-dlp.exe`（Windows 独立可执行文件）
- `setup_optional_tools.py`：优先复制本机 `yt-dlp`；允许时也可下载官方 release；构建安装包时须成功落入 staging
- `lib/runtime_tools.py`：`find_ytdlp()`，顺序：`MYKNOWLEDGE_YTDLP_PATH` → `third_party` → PATH
- 启动器 PATH 增加 `third_party\yt-dlp`（与 ffmpeg/bun 一致）

## UI / 文案

- 仍用「保存网页」；进度相位文案可含「正在获取 B 站字幕…」
- 失败用现有 job `error` + Toast，不写空笔记

## 验收

1. 有字幕 BV：入库可搜，提问可引用字幕内容  
2. 无字幕 BV：失败提示清晰，wiki 无新空页  
3. 普通网页 URL：行为不变  
4. 干净安装包目录存在 `third_party\yt-dlp\yt-dlp.exe`，无需系统 PATH 中的 yt-dlp  

## 主要改动文件

| 文件 | 职责 |
|------|------|
| `lib/bilibili_fetch.py`（新） | URL 识别、yt-dlp 拉字幕、拼 Markdown |
| `lib/url_fetch.py` | 入口分流到 bilibili |
| `lib/runtime_tools.py` | `find_ytdlp` |
| `scripts/setup_optional_tools.py` | 安装/复制 yt-dlp |
| `scripts/build-portable.ps1` / 启动器 PATH | 暴露 yt-dlp |
| 测试 | URL 识别与字幕解析单测（mock yt-dlp） |
