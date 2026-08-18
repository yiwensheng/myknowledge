# 易知 · PDF 结构化解析（B+C）设计

**日期**：2026-08-07  
**状态**：已实施（P0–P2）  
**产品**：易知（Myknowledge）  
**动机**：今日头条文介绍的 RAGFlow DeepDoc「按结构读懂 PDF」对合同/报表有用；整仓 RAGFlow/Docker **不可**内置。采用 **B（pdfplumber 表格 + 分块标记）+ C（随包 ONNX 版面/表格模型）**，安装到其它电脑仍可用。

---

## 1. 目标与非目标

### 目标

1. **数字 PDF**：整表提取为 Markdown 表格块，避免 `extract_text()` 把表拆成碎行。  
2. **扫描 / 弱文本页**：版面检测定位表格/图文区 → 裁切 → OCR（优先现有 Tesseract）→ 表格结构还原为 Markdown。  
3. **随安装包分发**：模型与 `onnxruntime` 打进 Setup；换机无需 Docker、无需首次联网下模型（首次安装即带权重）。  
4. **可降级**：缺模型 / 缺 OCR / 关开关时，回退到现有文本层 + OCR 路径，导入不失败。  
5. **能力面板可见**：关于/能力检测展示「PDF 表格」「PDF 版面模型」状态。

### 非目标

- 不嵌入 RAGFlow / DeepDoc 整仓，不依赖 Docker。  
- 不做可视化人工调块 UI（DeepDoc 卖点；易知本期只保证提取质量）。  
- 不保证印章/手写批注高精度（仍靠 OCR；印章可作弱图区 OCR）。  
- 不改 RAG 切块算法本身（只改善进入 RAG 的**提取文本**质量）。

---

## 2. 用户可见行为

| 场景 | 行为 |
|------|------|
| 导入含表的数字 PDF | 提取文本中出现 `--- 第N页-表格K ---` + Markdown 表 |
| 导入扫描合同/报表 | 弱文本页：版面检出表区 → OCR → Markdown 表；正文区 OCR 段落保留 |
| 关闭功能 | `MYKNOWLEDGE_PDF_TABLES=0` 关表格增强；`MYKNOWLEDGE_PDF_LAYOUT=0` 关 ONNX 版面（仍可保留数字 PDF 的 pdfplumber 表，见开关细则） |
| 旧 PDF | 须**重新导入**才补全结构块（与现 OCR 策略一致） |

---

## 3. 架构

```text
导入 PDF
  → lib/extract._extract_pdf
       ├─ 文本层（现有 pdfplumber/pypdf）
       ├─ B: pdfplumber.find_tables / extract_tables → Markdown
       ├─ C: 弱文本页或「有表候选」页
       │     ├─ 页光栅化（PyMuPDF，现有）
       │     ├─ ONNX 版面/表格检测（bundled）
       │     ├─ 表区裁切 + 结构识别（ONNX）或网格启发式
       │     └─ 单元格文字：优先 PDF 字框落入；否则 Tesseract
       └─ 现有内嵌图/整页 OCR 增强（保留，与表块去重）
  → 合成带标记的纯文本 → 现有 ingest / RAG
```

**新模块（建议）**

| 文件 | 职责 |
|------|------|
| `lib/pdf_tables.py` | B：pdfplumber → Markdown；表去重/空表过滤 |
| `lib/pdf_layout.py` | C：加载 ONNX、页图推理、表区 bbox、结构 → Markdown |
| `lib/extract.py` | 编排调用；环境开关；失败吞掉并 notice |
| `third_party/pdf_layout/README.md` + `*.onnx` | 随仓/随包权重（Apache/MIT 许可） |
| `lib/capabilities.py` | 检测 onnxruntime + 模型文件是否就位 |
| `requirements-runtime.txt` | 增加 `onnxruntime`（CPU）；必要时 `numpy`（若未间接依赖） |
| `scripts/build-portable.ps1` / prune | 确保 `third_party/pdf_layout` 进入 staging，不被 prune 掉 |

---

## 4. 模型选型（C）约束

必须满足：

1. **许可**：Apache-2.0 / MIT / BSD 等可商用随专有客户端分发；**避免 AGPL**（如部分 DocLayNet YOLO 捆绑包）。  
2. **运行时**：仅 `onnxruntime` CPU，无 PyTorch / Paddle / CUDA。  
3. **体积**：目标合计权重约 **50～150 MB**（可接受安装包再增）；若超 200MB 须在实现前再确认。  
4. **离线**：权重放在 `third_party/pdf_layout/`，禁止运行时静默从 HuggingFace 下载（安装机可能无网）。

**首选组合（实现时锁定具体文件名）：**

- **表格检测 + 结构**：Microsoft Table Transformer（TATR）检测/结构 ONNX（社区常用导出；许可友好）。  
- **可选版面粗检**：若仅 TATR 即可覆盖「找表」，可不另加 DocLayout，以控体积。  
- **OCR**：继续本机 **Tesseract**（`chi_sim+eng`）；不强制再绑一套 PP-OCR（除非后续证明 Tesseract 在扫描表上不可用）。

实现阶段若 TATR ONNX 导出/推理不稳，**降级路径**：版面仅用 OpenCV 线框/投影启发式找表 + OCR（仍属 C 的轻量实现，但精度低于 TATR）。

---

## 5. 开关与性能

| 环境变量 | 默认 | 含义 |
|----------|------|------|
| `MYKNOWLEDGE_PDF_TABLES` | `1` | 数字 PDF pdfplumber 表格提取 |
| `MYKNOWLEDGE_PDF_LAYOUT` | `1` | ONNX 版面/扫描表增强；模型缺失时自动跳过并 notice |
| `MYKNOWLEDGE_PDF_OCR` | `1` | 现有扫描/内嵌图 OCR（不变） |
| `MYKNOWLEDGE_PDF_LAYOUT_MAX_PAGES` | `40` | 版面模型处理页数上限（防大文件拖死） |
| `MYKNOWLEDGE_PDF_OCR_DPI` | `160` | 现有；布局推理可用同 DPI 或略高（如 200） |

性能原则：

- 数字页、文本丰富且 pdfplumber 已抽出表 → **跳过**该页 ONNX（省 CPU）。  
- 弱文本页或文本层疑似碎表 → 跑 ONNX。  
- 会话内懒加载 ONNX Session，进程内复用。

---

## 6. 输出格式约定（进 RAG 的文本）

```text
--- 第3页 ---
（正文段落…）

--- 第3页-表格1 ---
| 条款 | 内容 |
| --- | --- |
| 第三条 | 违约金为合同额的 10% |

--- 第3页-扫描 OCR ---
（非表区 OCR，若有）
```

同一物理表若 B 与 C 重复，以 **B（数字字层）优先**，丢弃重叠 IoU 高的 C 结果。

---

## 7. 打包与换机

1. `requirements-runtime.txt` 增加 `onnxruntime`（锁定兼容 cp313 / Win amd64 的版本范围）。  
2. 仓库提交或发版脚本准备好 `third_party/pdf_layout/*.onnx`（可用 `scripts/fetch_pdf_layout_models.ps1` 在**开发机**下载一次，再进 git-lfs 或随发版资源拷贝；**用户机不下载**）。  
3. `build-portable` 复制 `third_party/pdf_layout`；`prune` **不得删除**该目录下的 `.onnx`。  
4. PyInstaller 后端若冻结：确认 onnxruntime DLL 与模型路径（相对 `wiki_root` / 安装根 / `third_party`）可解析——与现有 `third_party/ffmpeg` 模式对齐。

---

## 8. 验收标准

1. 数字 PDF（含 2～3 个有线框表）：导入后笔记/索引文本中可见完整 Markdown 表；问答能引用表内单元格语义。  
2. 扫描 PDF（弱文本页 + 表）：无表时仍有 OCR；有表时至少有一个 `第N页-表格K` 块（精度允许瑕疵，但须优于纯 `extract_text`）。  
3. 删除/移走 `third_party/pdf_layout`：导入成功，notice 提示跳过版面模型；B 表仍可用。  
4. `MYKNOWLEDGE_PDF_LAYOUT=0`：不加载 ONNX。  
5. 干净安装包（无开发环境）在未装 Python 的机器上：后端能跑通上述路径（Tesseract 仍按现能力说明可选增强）。  
6. 更新记录 + changelog 要点；能力检测显示模型就绪/缺失。

---

## 9. 实现分期（仍属本次 B+C，顺序执行）

| 阶段 | 内容 | 验证 |
|------|------|------|
| P0 | B：`pdf_tables` + 接入 `_extract_pdf` + 开关 + 单测样例 PDF | 数字表 Markdown |
| P1 | C：模型目录约定 + onnxruntime + TATR（或已定模型）推理 + 扫描表 Markdown | 扫描样例有表块 |
| P2 | 打包进 staging、capabilities、文档、更新记录 | 安装树内路径自检脚本 |

---

## 10. 风险

| 风险 | 缓解 |
|------|------|
| 安装包体积增大 | 只打检测+结构必要权重；文档标明增量 |
| CPU 导入变慢 | 页数上限、数字页跳过 ONNX、懒加载 |
| 许可污染 | 禁止 AGPL 模型；README 列明许可证 |
| 冻结 exe 找不到模型 | 统一 `resolve_pdf_layout_dir()` 多候选路径 |
| Tesseract 未装 | notice；数字表仍可用；扫描表降级 |

---

## 11. 参考

- 动机文：[今日头条 · RAGFlow/DeepDoc](https://www.toutiao.com/article/7670842195934446114/)  
- 现有：`lib/extract.py` PDF OCR（2.4.1）  
- 规则：安装包对外下载为 `.zip`（产物仍 `.exe`）— 与本功能独立
