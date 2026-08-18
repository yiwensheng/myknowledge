# PDF 结构化解析（B+C）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `subagent-driven-development`. Steps use checkbox (`- [ ]`) syntax. **勿自动 git commit**（除非用户明确要求）。

**Goal:** 易知导入 PDF 时保留整表（Markdown），并对扫描/弱文本页用随包装的 ONNX（可降级）+ 现有 Tesseract 抽出表格，换机离线可用。

**Architecture:** 在 `lib/extract._extract_pdf` 编排：B=`lib/pdf_tables.py`（pdfplumber）；C=`lib/pdf_layout.py`（页图 → ONNX 表检/结构，失败则 Tesseract word-box 网格启发式）；模型在 `third_party/pdf_layout/`；开关与现有 OCR 并列。

**Tech Stack:** Python 3.11+、pdfplumber、PyMuPDF、Pillow、onnxruntime（CPU）、Tesseract（可选增强）、pytest。

**Spec:** `docs/superpowers/specs/2026-08-07-pdf-structure-b-c-design.md`

---

## File map

| 文件 | 职责 |
|------|------|
| `lib/pdf_tables.py` | 数字 PDF：`extract_tables` → Markdown；空表过滤 |
| `lib/pdf_layout.py` | 解析模型目录、ONNX Session 懒加载、表区推理、结构→Markdown；无模型时 word-box 启发式 |
| `lib/extract.py` | 调用 B/C、去重、notices、环境变量 |
| `lib/capabilities.py` | 能力项：pdf_tables / pdf_layout |
| `third_party/pdf_layout/README.md` | 许可、文件名、如何 fetch |
| `scripts/fetch_pdf_layout_models.ps1` | 开发机下载 ONNX 到 `third_party/pdf_layout/` |
| `scripts/verify_pdf_structure.py` | 对样例 PDF 打印是否含表格块 |
| `tests/test_pdf_tables.py` | B 单测（合成简易 PDF 或 fixture） |
| `tests/test_pdf_layout_fallback.py` | 无模型时不抛错 |
| `requirements-runtime.txt` | `onnxruntime`、`numpy` |
| `scripts/prune_install_staging.ps1` | 保留 `third_party/pdf_layout/*.onnx` |
| `.env.example` | 文档化新开关 |
| `docs/更新记录.md` | 开发记录 |

---

### Task 1: P0 — `pdf_tables` + 单测

**Files:**
- Create: `lib/pdf_tables.py`
- Create: `tests/test_pdf_tables.py`
- Modify: `lib/extract.py`（接入）

- [ ] **Step 1: 写失败测试**

`tests/test_pdf_tables.py`：用 pdfplumber/reportlab 或纯 pdfplumber 打开一个内存/临时 PDF（若难生成，则用 `pdfplumber` 对 fixture；优先用代码画一页简单表）。断言 `tables_as_markdown(path)` 返回的字符串含 `|` 与表头。

- [ ] **Step 2: 实现 `lib/pdf_tables.py`**

公开 API：

```python
def pdf_tables_enabled() -> bool: ...
def extract_tables_markdown(path: Path) -> list[tuple[int, str]]:
    """Return list of (1-based page_no, markdown_table)."""
```

用 `pdfplumber.open` → 每页 `extract_tables()` / `find_tables()`，过滤全空行，单元格 `None`→`""`，输出 GFM 表。

- [ ] **Step 3: 接入 `_extract_pdf`**

在拼装每页正文后插入该页表格块：`--- 第{n}页-表格{k} ---`。开关 `MYKNOWLEDGE_PDF_TABLES` 默认开。

- [ ] **Step 4: 跑测**

```powershell
cd E:\app\Myknowledge
python -m pytest tests/test_pdf_tables.py -v
```

Expected: PASS

---

### Task 2: P1 — `pdf_layout` 骨架 + 无模型降级

**Files:**
- Create: `lib/pdf_layout.py`
- Create: `tests/test_pdf_layout_fallback.py`

- [ ] **Step 1: 实现路径解析与开关**

```python
def pdf_layout_enabled() -> bool: ...
def resolve_pdf_layout_dir() -> Path | None: ...
def layout_models_ready() -> bool: ...
```

候选根：安装根/`third_party/pdf_layout`、`Path(__file__).resolve().parents[1]/third_party/pdf_layout`。

- [ ] **Step 2: 无 ONNX 时的扫描表启发式**

对弱文本页：PyMuPDF 渲图 → `pytesseract.image_to_data` → 按行聚类 y → 多列则拼 Markdown。失败返回 `[]`。

- [ ] **Step 3: ONNX 表检测钩子**

若存在约定文件（见 Task 3 README）：`detection.onnx`（及可选 `structure.onnx`），用 `onnxruntime.InferenceSession` 跑检测；裁切 ROI 后结构模型或启发式填格；单元格字优先 OCR。模型加载失败 → 回退 Step 2，并记 notice。

- [ ] **Step 4: 测试**

无模型目录或空目录时 `augment_scan_tables(path, page_texts)` 不抛异常。

---

### Task 3: 模型目录、fetch 脚本、runtime 依赖

**Files:**
- Create: `third_party/pdf_layout/README.md`
- Create: `scripts/fetch_pdf_layout_models.ps1`
- Modify: `requirements-runtime.txt`（`numpy>=1.26`、`onnxruntime>=1.17`）

- [ ] **Step 1: README 写明文件名与许可（Apache-2.0 / MIT only）**

约定至少：`detection.onnx`；可选 `structure.onnx`。说明用户机不下载。

- [ ] **Step 2: fetch 脚本**

开发机下载预转换 ONNX（URL 写死在脚本；若上游变更可改）。下载失败则打印手动放置说明，不使构建中断。

- [ ] **Step 3: 尝试执行 fetch**（本机有网时）

有模型则 Task 2 ONNX 路径可测；无则启发式仍可用。

---

### Task 4: 编排去重、capabilities、verify 脚本

**Files:**
- Modify: `lib/extract.py`
- Modify: `lib/capabilities.py`
- Create: `scripts/verify_pdf_structure.py`
- Modify: `.env.example`
- Modify: `scripts/prune_install_staging.ps1`（白名单保留 onnx）

- [ ] **Step 1: `_extract_pdf` 合并 B/C/OCR**，IoU/同页重复表以 B 优先。

- [ ] **Step 2: capabilities** 增加 `pdf_tables`、`pdf_layout` 两项。

- [ ] **Step 3: verify 脚本** 对给定 PDF 打印是否含 `-表格`。

- [ ] **Step 4: prune** 确保不删 `third_party\pdf_layout\*.onnx`。

---

### Task 5: 文档与设计状态

**Files:**
- Modify: `docs/更新记录.md`
- Modify: `docs/superpowers/specs/2026-08-07-pdf-structure-b-c-design.md`（状态→实施中/已完成）
- Modify: `docs/commercial/changelog.html`（仅当确认进下一安装版时；本任务先写开发记录，changelog 条目标「随下一版」）

- [ ] **Step 1: 更新记录顶部追加**（真实北京时间）

- [ ] **Step 2: 规格状态改为已实施（P0–P2 完成后）**

---

## Spec coverage

| Spec 项 | Task |
|---------|------|
| 数字 PDF Markdown 表 | 1 |
| 扫描表 ONNX + OCR | 2–3 |
| 降级不失败 | 2 |
| 随包 third_party | 3–4 |
| 开关 | 1–2 |
| capabilities | 4 |
| 更新记录 | 5 |

## 执行说明

- 用户规则：**不要自动 commit**。  
- 默认 **Inline Execution**（本会话按 Task 顺序做）。
