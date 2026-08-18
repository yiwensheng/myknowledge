"""PDF layout / scanned-table enhancement (ONNX optional + Tesseract fallback)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

_PDF_OCR_MIN_PAGE_CHARS = 40
_SESSION_CACHE: dict[str, Any] = {}


def pdf_layout_enabled() -> bool:
    """MYKNOWLEDGE_PDF_LAYOUT 默认开启；显式 0/false/off 关闭。"""
    v = (os.environ.get("MYKNOWLEDGE_PDF_LAYOUT") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _layout_max_pages() -> int:
    raw = (os.environ.get("MYKNOWLEDGE_PDF_LAYOUT_MAX_PAGES") or "").strip()
    try:
        n = int(raw) if raw else 40
    except ValueError:
        n = 40
    return max(1, min(n, 200))


def _layout_dpi() -> int:
    raw = (os.environ.get("MYKNOWLEDGE_PDF_OCR_DPI") or "").strip()
    try:
        dpi = int(raw) if raw else 160
    except ValueError:
        dpi = 160
    return max(72, min(dpi, 300))


def resolve_pdf_layout_dir() -> Path | None:
    """Locate third_party/pdf_layout next to install root or repo root."""
    env = (os.environ.get("MYKNOWLEDGE_PDF_LAYOUT_DIR") or "").strip()
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env))
    here = Path(__file__).resolve()
    # lib/ -> repo root
    candidates.append(here.parents[1] / "third_party" / "pdf_layout")
    # frozen / staging: MYK_ROOT or cwd
    for key in ("MYK_ROOT", "YIZHI_ROOT"):
        root = (os.environ.get(key) or "").strip()
        if root:
            candidates.append(Path(root) / "third_party" / "pdf_layout")
    candidates.append(Path.cwd() / "third_party" / "pdf_layout")
    for c in candidates:
        try:
            if c.is_dir():
                return c
        except OSError:
            continue
    return None


def layout_models_ready(layout_dir: Path | None = None) -> bool:
    d = layout_dir if layout_dir is not None else resolve_pdf_layout_dir()
    if d is None:
        return False
    return (d / "detection.onnx").is_file()


def _onnx_available() -> bool:
    try:
        import onnxruntime  # noqa: F401

        return True
    except ImportError:
        return False


def _tesseract_available() -> bool:
    import shutil

    return bool(shutil.which("tesseract"))


def _get_detection_session(model_path: Path):
    key = str(model_path.resolve())
    if key in _SESSION_CACHE:
        return _SESSION_CACHE[key]
    import onnxruntime as ort  # type: ignore

    sess = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    _SESSION_CACHE[key] = sess
    return sess


def _rows_to_markdown(rows: list[list[str]]) -> str:
    cleaned: list[list[str]] = []
    for row in rows:
        cells = [re.sub(r"\s+", " ", (c or "").replace("|", "\\|")).strip() for c in row]
        if not any(cells):
            continue
        cleaned.append(cells)
    if not cleaned:
        return ""
    width = max(len(r) for r in cleaned)
    for r in cleaned:
        while len(r) < width:
            r.append("")
    header = cleaned[0]
    body = cleaned[1:]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for r in body:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def _table_from_tesseract_data(img) -> str:
    """Heuristic: cluster OCR words into rows/columns → Markdown."""
    if not _tesseract_available():
        return ""
    try:
        import pytesseract  # type: ignore
    except ImportError:
        return ""
    try:
        data = pytesseract.image_to_data(img, lang="chi_sim+eng", output_type=pytesseract.Output.DICT)
    except Exception:
        try:
            data = pytesseract.image_to_data(img, lang="eng", output_type=pytesseract.Output.DICT)
        except Exception:
            return ""

    words: list[tuple[int, int, int, int, str]] = []
    n = len(data.get("text") or [])
    for i in range(n):
        txt = (data["text"][i] or "").strip()
        if not txt:
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1
        if conf < 0:
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        words.append((y, x, w, h, txt))
    if len(words) < 4:
        return ""

    words.sort(key=lambda t: (t[0], t[1]))
    # cluster by y (row)
    rows_bins: list[list[tuple[int, int, int, int, str]]] = []
    y_tol = max(8, int(sum(t[3] for t in words) / len(words) * 0.6))
    for item in words:
        y = item[0]
        if not rows_bins:
            rows_bins.append([item])
            continue
        prev_y = rows_bins[-1][0][0]
        if abs(y - prev_y) <= y_tol:
            rows_bins[-1].append(item)
        else:
            rows_bins.append([item])
    if len(rows_bins) < 2:
        return ""

    # estimate columns from median x gaps on densest row
    densest = max(rows_bins, key=len)
    densest_sorted = sorted(densest, key=lambda t: t[1])
    xs = [t[1] for t in densest_sorted]
    if len(xs) < 2:
        return ""
    gaps = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
    # if words are too evenly spaced as one stream, require multiple large gaps
    median_gap = sorted(gaps)[len(gaps) // 2] if gaps else 0
    col_break = max(24, int(median_gap * 1.8))

    def split_row(row: list[tuple[int, int, int, int, str]]) -> list[str]:
        row = sorted(row, key=lambda t: t[1])
        cols: list[list[str]] = [[]]
        last_x2 = row[0][1] + row[0][2]
        cols[0].append(row[0][4])
        for t in row[1:]:
            x = t[1]
            if x - last_x2 > col_break:
                cols.append([])
            cols[-1].append(t[4])
            last_x2 = t[1] + t[2]
        return [" ".join(c) for c in cols]

    grid = [split_row(r) for r in rows_bins]
    # require at least 2 columns somewhere
    if max(len(r) for r in grid) < 2:
        return ""
    return _rows_to_markdown(grid)


def _detect_table_boxes_onnx(img, model_path: Path) -> list[tuple[int, int, int, int]]:
    """
    Run detection.onnx.
    Supports:
    - TATR (logits + pred_boxes cxcywh normalized) when detection.meta.json format=tatr
    - generic YOLO-ish [N,4|6] boxes
    Returns list of (x0,y0,x1,y1) in image pixels.
    """
    try:
        import numpy as np  # type: ignore
    except ImportError:
        return []
    try:
        sess = _get_detection_session(model_path)
    except Exception:
        return []

    w, h = img.size
    meta_path = model_path.with_name("detection.meta.json")
    fmt = ""
    size = 640
    if meta_path.is_file():
        try:
            import json

            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            fmt = str(meta.get("format") or "")
            size = int(meta.get("size") or size)
        except Exception:
            pass

    rgb = img.convert("RGB").resize((size, size))
    arr = np.asarray(rgb, dtype=np.float32) / 255.0
    # ImageNet-ish normalize for TATR/DETR family
    if fmt == "tatr":
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(1, 3, 1, 1)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(1, 3, 1, 1)
        nchw = np.transpose(arr, (2, 0, 1))[None, ...]
        nchw = (nchw - mean) / std
    else:
        nchw = np.transpose(arr, (2, 0, 1))[None, ...]

    inp = sess.get_inputs()[0]
    name = inp.name
    try:
        outs = sess.run(None, {name: nchw})
    except Exception:
        try:
            outs = sess.run(None, {name: np.transpose(nchw, (0, 2, 3, 1))})
        except Exception:
            return []

    boxes: list[tuple[int, int, int, int]] = []

    # TATR: logits [1,Q,C], boxes [1,Q,4] cxcywh normalized 0..1
    if fmt == "tatr" and len(outs) >= 2:
        logits = np.asarray(outs[0])
        pred = np.asarray(outs[1])
        if logits.ndim == 3:
            logits = logits[0]
        if pred.ndim == 3:
            pred = pred[0]
        # softmax over classes; class 0 often "table" for detection (2 classes: table / no-object)
        exp = np.exp(logits - logits.max(axis=-1, keepdims=True))
        probs = exp / exp.sum(axis=-1, keepdims=True)
        # pick best non-last class if last is no-object
        if probs.shape[-1] >= 2:
            score = probs[:, 0]
        else:
            score = probs.max(axis=-1)
        for i, sc in enumerate(score):
            if float(sc) < 0.5:
                continue
            cx, cy, bw, bh = [float(x) for x in pred[i][:4]]
            x1 = (cx - bw / 2.0) * w
            y1 = (cy - bh / 2.0) * h
            x2 = (cx + bw / 2.0) * w
            y2 = (cy + bh / 2.0) * h
            xa, xb = sorted((int(x1), int(x2)))
            ya, yb = sorted((int(y1), int(y2)))
            if xb - xa < 40 or yb - ya < 40:
                continue
            boxes.append((max(0, xa), max(0, ya), min(w, xb), min(h, yb)))
        boxes.sort(key=lambda b: (b[1], b[0]))
        return boxes[:8]

    for out in outs:
        a = np.asarray(out)
        if a.ndim == 3:
            a = a[0]
        if a.ndim != 2 or a.shape[1] < 4:
            continue
        for row in a:
            vals = [float(x) for x in row[:6]]
            if len(vals) >= 5:
                score = vals[4] if vals[4] <= 1.0 else vals[4] / 100.0
                if score < 0.25:
                    continue
            x1, y1, x2, y2 = vals[0], vals[1], vals[2], vals[3]
            if max(abs(x1), abs(y1), abs(x2), abs(y2)) <= 1.5:
                x1, x2 = x1 * w, x2 * w
                y1, y2 = y1 * h, y2 * h
            else:
                x1, x2 = x1 * w / size, x2 * w / size
                y1, y2 = y1 * h / size, y2 * h / size
            xa, xb = sorted((int(x1), int(x2)))
            ya, yb = sorted((int(y1), int(y2)))
            if xb - xa < 40 or yb - ya < 40:
                continue
            boxes.append((max(0, xa), max(0, ya), min(w, xb), min(h, yb)))
    boxes.sort(key=lambda b: (b[1], b[0]))
    return boxes[:8]

def _render_page_image(path: Path, page_index: int, dpi: int):
    import fitz  # type: ignore
    from PIL import Image  # type: ignore

    doc = fitz.open(str(path))
    try:
        page = doc.load_page(page_index)
        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    finally:
        doc.close()


def extract_layout_table_blocks(
    path: Path,
    page_texts: list[str],
    skip_pages: set[int] | None = None,
) -> tuple[dict[int, list[str]], list[str]]:
    """
    For weak-text pages (and optionally all pages without digital tables),
    return page_no → labeled markdown table blocks, plus notices.
    """
    notices: list[str] = []
    out: dict[int, list[str]] = {}
    if not pdf_layout_enabled():
        return out, notices

    skip = skip_pages or set()
    layout_dir = resolve_pdf_layout_dir()
    det_path = (layout_dir / "detection.onnx") if layout_dir else None
    use_onnx = bool(det_path and det_path.is_file() and _onnx_available())
    if layout_dir is None:
        notices.append("（未找到 third_party/pdf_layout；扫描表使用 OCR 启发式，可运行 scripts/fetch_pdf_layout_models.ps1）")
    elif not (det_path and det_path.is_file()):
        notices.append("（pdf_layout 无 detection.onnx；扫描表使用 OCR 启发式）")
    elif not _onnx_available():
        notices.append("（未安装 onnxruntime；扫描表使用 OCR 启发式）")

    try:
        import fitz  # noqa: F401
    except ImportError:
        notices.append("（缺少 PyMuPDF，跳过版面表格增强）")
        return out, notices

    dpi = _layout_dpi()
    max_pages = min(len(page_texts), _layout_max_pages())
    for i in range(max_pages):
        page_no = i + 1
        if page_no in skip:
            continue
        text = page_texts[i] if i < len(page_texts) else ""
        weak = len(text.strip()) < _PDF_OCR_MIN_PAGE_CHARS
        # 强文本页已有数字表则已 skip；无数字表但文本很碎时也可尝试
        if not weak and page_no not in skip:
            # only run layout on weak pages to save CPU unless env forces
            force = (os.environ.get("MYKNOWLEDGE_PDF_LAYOUT_FORCE") or "").strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
            if not force:
                continue
        try:
            img = _render_page_image(path, i, dpi)
        except Exception:
            continue

        mds: list[str] = []
        if use_onnx and det_path is not None:
            boxes = _detect_table_boxes_onnx(img, det_path)
            for bi, (x0, y0, x1, y1) in enumerate(boxes, 1):
                crop = img.crop((x0, y0, x1, y1))
                md = _table_from_tesseract_data(crop)
                if md:
                    mds.append(md)
        if not mds:
            md = _table_from_tesseract_data(img)
            if md:
                mds.append(md)

        blocks: list[str] = []
        for k, md in enumerate(mds, 1):
            blocks.append(f"--- 第{page_no}页-表格{k} ---\n{md}")
        if blocks:
            out[page_no] = blocks
    return out, notices
