"""ParseBench 风格多模态 PDF 解析（本地化，不依赖 gaik/LlamaParse）。

源自今日头条文《用AI准确提取文档一切》所述思路：
- 表格输出 HTML（colspan/rowspan），而非扁平 Markdown
- 图表转「扁平表头」表格
- 布局元素带 data-bbox / data-label（归一化 0–1000）
- 可选合并跨页表格

默认关闭：需显式工作流，或 MYKNOWLEDGE_PDF_LLM_PARSE=1 时在导入链路增强。
需 LLM 支持 image_url（多模态）；费用与耗时高于本地解析器。
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .config import llm_config, wiki_root

_LAYOUT_LABELS = (
    "Caption",
    "Footnote",
    "Formula",
    "List-item",
    "Page-footer",
    "Page-header",
    "Picture",
    "Section-header",
    "Table",
    "Text",
    "Title",
)

SYSTEM_PROMPT = f"""你是文档版面解析器。用户会提供 PDF 某一页的整页截图。
不要「读成散文」；要输出**带结构编码**的内容，便于下游重建布局与正确读表。

硬性输出契约（只输出下列 HTML，不要 Markdown 围栏、不要前言后语）：
1. 按**阅读顺序**，每个布局元素恰好包在一个 <div> 中。
2. 每个 div 必须有属性：
   - data-label：取值仅限 {", ".join(_LAYOUT_LABELS)}
   - data-bbox：归一化坐标，格式 "x_min,y_min,x_max,y_max"，范围为 0–1000（相对本页宽高）
3. 表格（data-label="Table"）内必须用 HTML <table><tr><th>/<td>，并用 colspan、rowspan 保留合并单元格与多级表头。禁止用 Markdown 管道表。
4. 图表/图形（Picture）：若含可读数据，另输出一张「扁平表头」HTML 表（每个数据单元格的行包含其全部标签，如 "Primary 2015"），并给图表本身一个 Picture 的 div；无法读数则仅 Picture + 简短 Caption。
5. 页眉页脚用 Page-header / Page-footer；正文 Text；标题 Title；小节 Section-header。
6. 文字语言与原文档一致；勿编造看不见的单元格或数字。
"""

USER_PROMPT_PAGE = """请解析本页截图。按系统契约输出带 data-bbox / data-label 的 div 序列；表格用 HTML。"""

USER_PROMPT_MERGE = (
    "若本页表格是上一页表格的续页，请在本页输出完整续行，并在首个 Table 的 div 上增加 "
    'data-continued="1"；表头若重复可省略，但列结构须与跨页一致。'
)

_FENCE_RE = re.compile(r"^```(?:html|HTML|xml)?\s*|\s*```$", re.MULTILINE)
_DIV_RE = re.compile(
    r"<div\b([^>]*)>(.*?)</div>",
    re.IGNORECASE | re.DOTALL,
)


def pdf_llm_parse_enabled() -> bool:
    """MYKNOWLEDGE_PDF_LLM_PARSE 默认关。"""
    v = (os.environ.get("MYKNOWLEDGE_PDF_LLM_PARSE") or "0").strip().lower()
    return v not in ("0", "false", "no", "off", "")


def _max_pages() -> int:
    raw = (os.environ.get("MYKNOWLEDGE_PDF_LLM_PARSE_MAX_PAGES") or "").strip()
    try:
        n = int(raw) if raw else 8
    except ValueError:
        n = 8
    return max(1, min(40, n))


def _dpi() -> int:
    raw = (os.environ.get("MYKNOWLEDGE_PDF_LLM_PARSE_DPI") or "").strip()
    try:
        dpi = int(raw) if raw else 140
    except ValueError:
        dpi = 140
    return max(72, min(220, dpi))


def strip_code_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = _FENCE_RE.sub("", t).strip()
        if t.lower().startswith("html"):
            t = t[4:].lstrip()
    return t.strip()


def clean_llm_parse_html(raw: str, *, keep_bbox: bool = False) -> str:
    """清洗模型输出：去围栏；默认可读正文（去 bbox），保留 HTML 表。"""
    html = strip_code_fences(raw)
    if not html:
        return ""
    if keep_bbox:
        return html

    parts: list[str] = []
    for m in _DIV_RE.finditer(html):
        attrs = m.group(1) or ""
        inner = (m.group(2) or "").strip()
        label_m = re.search(r'data-label\s*=\s*["\']([^"\']+)["\']', attrs, re.I)
        label = (label_m.group(1) if label_m else "Text").strip()
        if label in ("Page-header", "Page-footer"):
            continue
        if not inner:
            continue
        if label == "Title":
            parts.append(f"# {re.sub(r'<[^>]+>', '', inner).strip()}")
        elif label == "Section-header":
            parts.append(f"## {re.sub(r'<[^>]+>', '', inner).strip()}")
        elif label == "Table":
            tm = re.search(r"(<table\b.*?</table>)", inner, re.I | re.DOTALL)
            parts.append(tm.group(1) if tm else inner)
        elif label == "Picture":
            cap = re.sub(r"<[^>]+>", " ", inner).strip()
            if cap:
                parts.append(f"[图] {cap}")
        elif label == "Caption":
            parts.append(re.sub(r"<[^>]+>", "", inner).strip())
        elif label == "List-item":
            line = re.sub(r"<[^>]+>", "", inner).strip()
            parts.append(f"- {line}" if line else inner)
        else:
            if "<table" in inner.lower():
                parts.append(inner)
            else:
                parts.append(re.sub(r"<[^>]+>", "", inner).strip() or inner)
    if parts:
        return "\n\n".join(p for p in parts if p)
    return html


def _page_jpeg_b64(page, dpi: int) -> str | None:
    try:
        import fitz  # type: ignore
        from PIL import Image  # type: ignore

        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        w, h = img.size
        max_side = 1280
        if max(w, h) > max_side:
            scale = max_side / float(max(w, h))
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=78)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return None


def _vision_chat(system: str, user_text: str, image_b64: str) -> str:
    cfg = llm_config()
    if not cfg.get("api_key") or not cfg.get("chat_url"):
        return "未配置 LLM API Key。"
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                ],
            },
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
        "stream": False,
    }
    req = urllib.request.Request(
        str(cfg["chat_url"]),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {cfg['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            obj = json.loads(resp.read().decode("utf-8", errors="replace"))
        return (
            ((obj.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        ).strip()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:600]
        return f"LLM 请求失败: HTTP {e.code} {body}"
    except Exception as e:
        return f"LLM 请求失败: {type(e).__name__}: {e}"


def parse_pdf_with_llm(
    path: Path,
    *,
    merge_table: bool = True,
    max_pages: int | None = None,
    keep_bbox: bool = False,
) -> dict[str, Any]:
    """逐页视觉解析 PDF，返回 clean / raw 文本。"""
    path = Path(path)
    if not path.is_file():
        return {"ok": False, "error": f"文件不存在: {path}", "output": ""}
    if path.suffix.lower() != ".pdf":
        return {"ok": False, "error": "仅支持 PDF", "output": ""}

    try:
        import fitz  # type: ignore
    except ImportError:
        return {"ok": False, "error": "需要 PyMuPDF（pymupdf）", "output": ""}

    cfg = llm_config()
    if not cfg.get("api_key"):
        return {"ok": False, "error": "未配置 LLM API Key", "output": ""}

    limit = max_pages if max_pages is not None else _max_pages()
    dpi = _dpi()
    raw_pages: list[str] = []
    clean_pages: list[str] = []
    errors: list[str] = []

    with fitz.open(str(path)) as doc:
        n = min(doc.page_count, limit)
        for i in range(n):
            page = doc.load_page(i)
            b64 = _page_jpeg_b64(page, dpi)
            if not b64:
                errors.append(f"第{i + 1}页渲染失败")
                continue
            user = USER_PROMPT_PAGE
            if merge_table and i > 0:
                user = USER_PROMPT_PAGE + "\n" + USER_PROMPT_MERGE
            raw = _vision_chat(SYSTEM_PROMPT, user, b64)
            if raw.startswith("LLM 请求失败") or raw.startswith("未配置"):
                errors.append(f"第{i + 1}页: {raw[:200]}")
                continue
            raw_pages.append(f"--- 第{i + 1}页-LLM版面 ---\n{strip_code_fences(raw)}")
            cleaned = clean_llm_parse_html(raw, keep_bbox=keep_bbox)
            if cleaned:
                clean_pages.append(f"--- 第{i + 1}页 ---\n{cleaned}")

    if not clean_pages and not raw_pages:
        return {
            "ok": False,
            "error": "；".join(errors) or "无有效页输出",
            "output": "；".join(errors) or "无有效页输出",
        }

    clean = "\n\n".join(clean_pages)
    notice = ""
    if errors:
        notice = "\n\n（部分页失败）\n" + "\n".join(errors)
    return {
        "ok": True,
        "action": "pdf-llm-parse",
        "pages": len(clean_pages),
        "max_pages": limit,
        "merge_table": merge_table,
        "text": clean + notice,
        "raw": "\n\n".join(raw_pages),
        "output": clean + notice,
        "errors": errors,
    }


def run_pdf_llm_parse(topic: str = "", root: Path | None = None) -> dict[str, Any]:
    """工作流入口：topic 为 PDF 路径；空则取 inbox 首个 PDF。"""
    root = root or wiki_root()
    topic = (topic or "").strip()
    path: Path | None = None
    # 路径可能夹带开关词，先取首行/首段像路径的部分
    path_token = topic.splitlines()[0].strip() if topic else ""
    for junk in ("保留坐标", "不合表", "keep_bbox", "merge_table=0"):
        path_token = path_token.replace(junk, "").strip()
    if path_token:
        path = Path(path_token)
        if not path.is_absolute():
            cand = root / path_token
            if cand.is_file():
                path = cand
    if path is None or not path.is_file():
        inbox = root / "inbox"
        if inbox.is_dir():
            for p in sorted(inbox.rglob("*.pdf")):
                if "inbox-processed" in p.parts:
                    continue
                path = p
                break
    if path is None or not path.is_file():
        return {
            "ok": False,
            "error": "需要 PDF 路径，或在 inbox 放入 PDF",
            "output": "需要参数：PDF 文件路径（可相对知识库根目录）；空=inbox 首个 PDF",
        }

    merge = "不合表" not in topic and "merge_table=0" not in topic.lower()
    keep_bbox = "保留坐标" in topic or "keep_bbox" in topic.lower()

    result = parse_pdf_with_llm(path, merge_table=merge, keep_bbox=keep_bbox)
    if not result.get("ok"):
        return result

    out_dir = root / "notes" / "parse-preview"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = path.stem[:60]
        preview = out_dir / f"llm-parse-{stem}.md"
        body = (
            f"# LLM 版面解析预览：{path.name}\n\n"
            f"- 源：`{path}`\n"
            f"- 页数（本次）：{result.get('pages')}\n"
            f"- merge_table：{merge}\n\n"
            f"{result.get('text') or ''}\n"
        )
        preview.write_text(body, encoding="utf-8")
        result["preview_path"] = str(preview.relative_to(root)).replace("\\", "/")
        result["output"] = (
            f"# LLM 版面解析完成\n\n"
            f"- 文件：`{path.name}`\n"
            f"- 预览：`{result['preview_path']}`（未自动入库，请确认后手动导入）\n"
            f"- 解析页数：{result.get('pages')}\n\n"
            f"{(result.get('text') or '')[:4000]}"
        )
    except Exception as e:
        result["output"] = (result.get("text") or "") + f"\n\n（预览写入失败: {e}）"
    return result
