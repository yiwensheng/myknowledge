"""Suggest file classification for inbox (read-only; never moves files)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .config import load_dotenv, llm_config, wiki_root
from .extract import extract_text
from .media_types import TEXT_LIKE, is_supported

CATEGORIES: list[tuple[str, str]] = [
    ("enterprise_basics", "企业基础"),
    ("products_services", "产品服务"),
    ("customer_questions", "客户问题"),
    ("case_materials", "案例资料"),
    ("output_rules", "输出规则"),
]

CATEGORY_LABELS = dict(CATEGORIES)


def _max_files() -> int:
    load_dotenv()
    try:
        return max(1, min(40, int(os.environ.get("MYKNOWLEDGE_CLASSIFY_MAX_FILES", "20"))))
    except ValueError:
        return 20


def _excerpt_chars() -> int:
    load_dotenv()
    try:
        return max(400, min(6000, int(os.environ.get("MYKNOWLEDGE_CLASSIFY_EXCERPT_CHARS", "2400"))))
    except ValueError:
        return 2400


def _list_inbox_files(root: Path) -> list[Path]:
    inbox = root / "inbox"
    if not inbox.is_dir():
        return []
    out: list[Path] = []
    for path in sorted(inbox.rglob("*")):
        if not path.is_file():
            continue
        if "inbox-processed" in path.parts or ".extracted" in path.parts:
            continue
        if is_supported(path.suffix):
            out.append(path)
    return out


def _file_excerpt(path: Path, max_chars: int) -> str:
    try:
        if path.suffix.lower() in TEXT_LIKE:
            text = path.read_text(encoding="utf-8", errors="replace")
        else:
            text = extract_text(path)
    except OSError:
        return ""
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) > max_chars:
        return text[:max_chars] + "…"
    return text


def _heuristic_suggest(name: str, excerpt: str) -> dict[str, Any]:
    blob = f"{name} {excerpt[:800]}".lower()
    rules = [
        ("output_rules", ("规则", "话术", "模板", "禁用", "禁止", "语气", "风格")),
        ("customer_questions", ("faq", "问答", "客户问", "常见问题", "咨询")),
        ("case_materials", ("案例", "成交", "复盘", "示范", "样例")),
        ("products_services", ("产品", "服务", "方案", "报价", "功能", "参数")),
        ("enterprise_basics", ("公司简介", "企业", "制度", "流程", "组织", "介绍")),
    ]
    scores: dict[str, int] = {k: 0 for k, _ in CATEGORIES}
    for key, words in rules:
        for w in words:
            if w.lower() in blob or w in name:
                scores[key] += 1
    ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    primary = ranked[0][0] if ranked[0][1] > 0 else "enterprise_basics"
    related = [k for k, s in ranked[1:3] if s > 0]
    wiki_map = {
        "enterprise_basics": "concept",
        "products_services": "source",
        "customer_questions": "note",
        "case_materials": "source",
        "output_rules": "note",
    }
    return {
        "primary_category": primary,
        "related_categories": related,
        "wiki_type": wiki_map.get(primary, "source"),
        "suggested_tags": [CATEGORY_LABELS.get(primary, primary)],
        "reason": "基于文件名/前段正文关键词的启发式建议（未调用 LLM）",
        "uncertain": ranked[0][1] == 0,
    }


def _parse_llm_items(raw: str) -> list[dict[str, Any]]:
    text = raw.strip()
    m = re.search(r"\[[\s\S]*\]", text)
    if m:
        text = m.group(0)
    data = json.loads(text)
    if not isinstance(data, list):
        return []
    return [x for x in data if isinstance(x, dict)]


def _llm_suggest_batch(items: list[dict[str, str]]) -> list[dict[str, Any]]:
    from .llm import _chat

    cats = "、".join(f"{k}（{v}）" for k, v in CATEGORIES)
    system = (
        "你是资料整理助手。根据文件名与正文摘录，为每个文件给出分类建议。"
        "只输出 JSON 数组，不要 markdown 代码围栏，不要其它说明。"
        "每个元素字段：file(文件名), primary_category(主分类 id), related_categories(关联分类 id 数组), "
        "wiki_type(source|concept|entity|comparison|note), suggested_tags(2-5个中文标签), reason(一句话理由), "
        "uncertain(布尔，无法判断时为 true)。"
        f"主分类 id 只能是：{', '.join(k for k, _ in CATEGORIES)}。"
        "禁止编造正文中不存在的产品或事实；信息不足时 uncertain=true 并在 reason 说明。"
        "不要建议移动、删除或改写文件。"
    )
    payload = json.dumps(items, ensure_ascii=False, indent=2)
    user = (
        f"分类体系：{cats}\n\n"
        f"待分析文件（共 {len(items)} 个）：\n{payload}\n\n"
        "请输出 JSON 数组："
    )
    raw = _chat(system, user, kind="produce")
    parsed = _parse_llm_items(raw)
    by_name = {str(x.get("file") or ""): x for x in parsed}
    out: list[dict[str, Any]] = []
    for it in items:
        fname = it["file"]
        row = by_name.get(fname) or {}
        primary = str(row.get("primary_category") or "").strip()
        if primary not in CATEGORY_LABELS:
            primary = _heuristic_suggest(fname, it.get("excerpt") or "")["primary_category"]
        related_raw = row.get("related_categories") or []
        related = [str(x) for x in related_raw if str(x) in CATEGORY_LABELS and str(x) != primary][:3]
        wiki_type = str(row.get("wiki_type") or "source").strip().lower()
        if wiki_type not in ("source", "concept", "entity", "comparison", "note"):
            wiki_type = "source"
        tags = row.get("suggested_tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in re.split(r"[,，;；]", tags) if t.strip()]
        tags = [str(t).strip() for t in tags if str(t).strip()][:6]
        out.append(
            {
                "file": fname,
                "rel_path": it.get("rel_path") or fname,
                "primary_category": primary,
                "related_categories": related,
                "wiki_type": wiki_type,
                "suggested_tags": tags,
                "reason": str(row.get("reason") or "").strip(),
                "uncertain": bool(row.get("uncertain")),
            }
        )
    return out


def _format_markdown(
    suggestions: list[dict[str, Any]],
    *,
    skipped: list[dict[str, str]],
    root: Path,
    scanned: int,
    method: str,
    truncated: int = 0,
) -> str:
    lines = [
        "# 资料分类建议",
        "",
        "> **未移动、未删除、未改写任何原文件。** 确认后再执行「整理待处理文件」或手动调整标签。",
        "",
        f"- 扫描目录：`{root / 'inbox'}`",
        f"- 分析文件数：{len(suggestions)} / 待处理 {scanned} 个",
        f"- 分析方式：{'LLM' if method == 'llm' else '启发式（无 API Key 或未启用 LLM）' if method != 'skip' else '—'}",
        "",
    ]
    if truncated > 0:
        lines.append(f"- 另有 {truncated} 个文件未分析（可在 .env 调整 `MYKNOWLEDGE_CLASSIFY_MAX_FILES`）")
        lines.append("")

    if not suggestions and not skipped:
        lines.extend(["inbox/ 中暂无待分类的支持格式文件。", ""])
        return "\n".join(lines)

    for s in suggestions:
        primary = CATEGORY_LABELS.get(s["primary_category"], s["primary_category"])
        related = "、".join(CATEGORY_LABELS.get(c, c) for c in s.get("related_categories") or [])
        tags = "、".join(s.get("suggested_tags") or []) or "—"
        flag = " ⚠ 待确认" if s.get("uncertain") else ""
        lines.extend(
            [
                f"## {s.get('rel_path') or s.get('file')}{flag}",
                "",
                f"- **主分类**：{primary}",
                f"- **关联分类**：{related or '—'}",
                f"- **建议 wiki 类型**：`{s.get('wiki_type') or 'source'}`",
                f"- **建议标签**：{tags}",
                f"- **理由**：{s.get('reason') or '—'}",
                "",
            ]
        )

    if skipped:
        lines.extend(["## 无法判断的文件", ""])
        for u in skipped:
            lines.append(f"- `{u.get('rel_path') or u.get('file')}`：{u.get('reason') or '信息不足'}")
        lines.append("")

    lines.extend(
        [
            "## 下一步建议",
            "",
            "1. 确认主分类无误后，将文件保留在 inbox/ 并运行「整理待处理文件」",
            "2. 入库后可在资料库中按建议标签补充或修正",
            "3. 「输出规则」类文档可粘贴到 `prompts/output-rules.md` 或通过提问页「写入输出规则」追加",
            "",
        ]
    )
    return "\n".join(lines)


def suggest_classification(
    root: Path | None = None,
    *,
    max_files: int | None = None,
) -> dict[str, Any]:
    """Scan inbox and return classification suggestions without modifying files."""
    root = root or wiki_root()
    limit = max_files if max_files is not None else _max_files()
    files = _list_inbox_files(root)
    scanned = len(files)
    if not files:
        text = _format_markdown([], skipped=[], root=root, scanned=0, method="skip")
        return {"ok": True, "action": "classify-suggest", "count": 0, "output": text, "items": []}

    batch = files[:limit]
    excerpt_len = _excerpt_chars()
    snippets: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    for path in batch:
        rel = str(path.relative_to(root)).replace("\\", "/")
        excerpt = _file_excerpt(path, excerpt_len)
        if not excerpt.strip() and path.suffix.lower() not in TEXT_LIKE:
            skipped.append({"file": path.name, "rel_path": rel, "reason": "未能提取正文，请整理前人工确认"})
            continue
        snippets.append({"file": path.name, "rel_path": rel, "excerpt": excerpt or "（仅文件名，无正文摘录）"})

    cfg = llm_config()
    use_llm = bool(cfg.get("api_key")) and bool(snippets)
    suggestions: list[dict[str, Any]] = []
    method = "heuristic"

    if use_llm:
        try:
            suggestions = _llm_suggest_batch(snippets)
            method = "llm"
        except Exception:
            use_llm = False

    if not use_llm:
        for it in snippets:
            h = _heuristic_suggest(it["file"], it.get("excerpt") or "")
            suggestions.append({"file": it["file"], "rel_path": it["rel_path"], **h})

    uncertain_only = [s for s in suggestions if s.get("uncertain")]
    truncated = max(0, scanned - limit)

    output = _format_markdown(
        suggestions,
        skipped=skipped,
        root=root,
        scanned=scanned,
        method=method,
        truncated=truncated,
    )

    return {
        "ok": True,
        "action": "classify-suggest",
        "count": len(suggestions),
        "uncertain": len(uncertain_only),
        "method": method,
        "items": suggestions,
        "output": output,
    }
