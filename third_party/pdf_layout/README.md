# 易知 PDF 版面 / 表格 ONNX 模型目录
#
# 约定文件（可商用许可，禁止 AGPL）：
#   detection.onnx   — 表格区域检测（必选才启用 ONNX 路径）
#   structure.onnx   — 表格结构（可选；当前实现主要用 OCR 网格填格）
#
# 用户安装包须随包携带上述文件；运行时不联网下载。
# 开发机获取（推荐，经 hf-mirror 导出 Microsoft TATR）：
#   $env:HF_ENDPOINT='https://hf-mirror.com'
#   python scripts/export_tatr_detection_onnx.py
# 或：
#   .\scripts\fetch_pdf_layout_models.ps1
#
# 产物：detection.onnx（约 110MB）+ detection.meta.json（format=tatr）
#
# 环境变量：
#   MYKNOWLEDGE_PDF_LAYOUT=1|0
#   MYKNOWLEDGE_PDF_LAYOUT_DIR=绝对路径（可选覆盖）
#   MYKNOWLEDGE_PDF_LAYOUT_MAX_PAGES=40
#   MYKNOWLEDGE_PDF_LAYOUT_FORCE=1  — 强文本页也跑版面（默认仅弱文本页）
#
# 无 detection.onnx 时：扫描页回退到 Tesseract word-box 启发式，导入不失败。
