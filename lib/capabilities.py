"""Detect optional runtime capabilities for GUI settings panel."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from .config import load_dotenv, rag_embedding_config, wiki_root
from .runtime_tools import find_bun, find_ffmpeg
from .url_fetch import _find_baoyu_fetch


def _check_tesseract() -> dict[str, Any]:
    exe = shutil.which("tesseract")
    return {
        "id": "tesseract",
        "label": "Tesseract OCR",
        "ok": bool(exe),
        "detail": exe or "未安装 — 独立图片与 PDF 内嵌图/扫描页识别受限（建议安装并含 chi_sim）",
        "impact": "独立图片 OCR；PDF 内嵌图与扫描页 OCR",
    }


def _check_pymupdf() -> dict[str, Any]:
    try:
        import fitz  # type: ignore

        ver = getattr(fitz, "VersionBind", "") or ""
        ok = True
        detail = f"已安装 {ver}".strip() if ver else "已安装"
    except ImportError:
        ok = False
        detail = "未安装 — pip install pymupdf 后可对 PDF 抽图/整页渲染再 OCR"
    return {
        "id": "pymupdf",
        "label": "PyMuPDF（PDF 渲染/抽图）",
        "ok": ok,
        "detail": detail,
        "impact": "PDF 内嵌图提取与扫描页光栅化（OCR 仍依赖 Tesseract）",
    }



def _check_pdf_tables() -> dict[str, Any]:
    try:
        import pdfplumber  # noqa: F401

        ok = True
        detail = "pdfplumber 可用"
    except ImportError:
        ok = False
        detail = "未安装 pdfplumber"
    from .pdf_tables import pdf_tables_enabled

    en = pdf_tables_enabled()
    return {
        "id": "pdf_tables",
        "label": "PDF 数字表格提取",
        "ok": ok and en,
        "detail": detail if en else "已关闭 MYKNOWLEDGE_PDF_TABLES=0",
        "impact": "导入 PDF 时保留整表为 Markdown",
    }


def _check_pdf_layout() -> dict[str, Any]:
    from .pdf_layout import layout_models_ready, pdf_layout_enabled, resolve_pdf_layout_dir

    en = pdf_layout_enabled()
    d = resolve_pdf_layout_dir()
    ready = layout_models_ready(d)
    try:
        import onnxruntime  # noqa: F401

        ort = True
    except ImportError:
        ort = False
    ok = bool(en and ready and ort)
    if not en:
        detail = "已关闭 MYKNOWLEDGE_PDF_LAYOUT=0"
    elif not ort:
        detail = "未安装 onnxruntime（扫描表仍可用 OCR 启发式）"
    elif not ready:
        detail = f"模型未就绪: {(d or Path('third_party/pdf_layout'))} 缺 detection.onnx"
    else:
        detail = f"ONNX 就绪 @ {d}"
    return {
        "id": "pdf_layout",
        "label": "PDF 版面/扫描表（ONNX）",
        "ok": ok,
        "detail": detail,
        "impact": "弱文本页表格区域检测；无模型时 OCR 启发式降级",
    }


def _check_ffmpeg() -> dict[str, Any]:
    exe = find_ffmpeg()
    return {
        "id": "ffmpeg",
        "label": "ffmpeg",
        "ok": bool(exe),
        "detail": exe or "未安装 — 运行 python scripts/setup_optional_tools.py 安装内置 ffmpeg",
        "impact": "播客 TTS 合并",
    }


def _check_bun() -> dict[str, Any]:
    exe = find_bun()
    baoyu = _find_baoyu_fetch()
    ok = bool(exe and baoyu)
    detail = ""
    if not exe:
        detail = "未安装 bun — 运行 python scripts/setup_optional_tools.py 安装内置 bun"
    elif not baoyu:
        detail = "未找到 baoyu-fetch 脚本"
    else:
        detail = f"{exe} · {baoyu}"
    return {
        "id": "bun_baoyu",
        "label": "bun + baoyu-fetch",
        "ok": ok,
        "detail": detail,
        "impact": "网页/公众号抓取",
    }


def _check_embedding() -> dict[str, Any]:
    load_dotenv()
    cfg = rag_embedding_config()
    enabled = bool(cfg.get("enabled"))
    has_key = bool(cfg.get("api_key"))
    ok = enabled and has_key
    return {
        "id": "embedding",
        "label": "向量 Embedding API",
        "ok": ok,
        "detail": f"model={cfg.get('model', '')} · enabled={enabled} · key={'有' if has_key else '无'}",
        "impact": "语义检索 / hybrid RAG",
    }


def _check_llm() -> dict[str, Any]:
    load_dotenv()
    import os

    from .settings import _llm_settings_hidden

    base = os.environ.get("MYKNOWLEDGE_LLM_API_BASE", "").strip()
    key = os.environ.get("MYKNOWLEDGE_LLM_API_KEY", "").strip()
    ok = bool(base and key)
    if _llm_settings_hidden():
        detail = "已由安装包预配置" if ok else "安装包未正确写入大模型配置"
    elif ok:
        detail = "已配置（地址与 Key 已填写）"
    elif base and not key:
        detail = "已填写地址，缺少 API Key"
    elif key and not base:
        detail = "已填写 Key，缺少 API 地址"
    else:
        detail = "未配置 — 请在下方「大模型」中填写 API 地址与 Key"
    return {
        "id": "llm",
        "label": "大模型 API",
        "ok": ok,
        "detail": detail,
        "impact": "提问 / 写文章 / 文档分析",
    }


def _check_rerank() -> dict[str, Any]:
    from .config import rag_rerank_config

    cfg = rag_rerank_config()
    ok = bool(cfg.get("enabled"))
    return {
        "id": "rerank",
        "label": "Rerank API",
        "ok": ok,
        "detail": f"model={cfg.get('model', '')} · url={cfg.get('url') or '无（需配置 MYKNOWLEDGE_RERANK_URL 或与 Embedding 同 base）'}",
        "impact": "粗排后精排（可选）",
    }


def _check_fts5() -> dict[str, Any]:
    from .rag_fts import fts5_stats

    st = fts5_stats()
    ok = bool(st.get("enabled"))
    return {
        "id": "fts5",
        "label": "FTS5 关键词索引",
        "ok": ok,
        "detail": f"chunks={st.get('chunks', 0)}",
        "impact": "BM25 混合检索",
    }


def _check_parse_quality() -> dict[str, Any]:
    return {
        "id": "parse_quality",
        "label": "解析质量抽检",
        "ok": True,
        "detail": "工作流「解析质量抽检」；分块对 Markdown/HTML 表按行切分",
        "impact": "导入前抽检提取/分块是否人类可读",
    }


def _check_pdf_llm_parse() -> dict[str, Any]:
    import os

    from .pdf_llm_parse import pdf_llm_parse_enabled

    en = pdf_llm_parse_enabled()
    force = (os.environ.get("MYKNOWLEDGE_PDF_LLM_PARSE_FORCE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    detail = "工作流「LLM 版面解析」随时可用"
    if en:
        detail += "；导入增强已开" + ("（FORCE）" if force else "（弱文本才替换）")
    else:
        detail += "；导入默认关（MYKNOWLEDGE_PDF_LLM_PARSE=0）"
    return {
        "id": "pdf_llm_parse",
        "label": "LLM 版面解析（ParseBench 风格）",
        "ok": True,
        "detail": detail,
        "impact": "复杂表/跨页：HTML 表+视觉模型；需多模态 API，费 token",
    }


def list_capabilities() -> dict[str, Any]:
    items = [
        _check_llm(),
        _check_embedding(),
        _check_fts5(),
        _check_rerank(),
        _check_tesseract(),
        _check_pymupdf(),
        _check_pdf_tables(),
        _check_pdf_layout(),
        _check_parse_quality(),
        _check_pdf_llm_parse(),
        _check_ffmpeg(),
        _check_bun(),
    ]
    return {
        "wiki_root": str(wiki_root()),
        "items": items,
        "all_ok": all(i["ok"] for i in items),
    }
