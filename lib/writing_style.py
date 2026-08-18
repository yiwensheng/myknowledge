"""Learn tone and writing habits from the wiki; inject into ask/produce prompts."""

from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import RAG_DIR, load_dotenv, wiki_root
from .wiki import WikiPage, list_pages

BEIJING = timezone(timedelta(hours=8))
STYLE_FILE = "writing_style.json"
MAX_EXCERPT_CHARS = 12_000


def style_enabled() -> bool:
    load_dotenv()
    raw = os.environ.get("MYKNOWLEDGE_STYLE_ENABLED", "1").strip().lower()
    return raw not in ("0", "false", "no")


def style_sample_pages() -> int:
    load_dotenv()
    try:
        return max(3, min(40, int(os.environ.get("MYKNOWLEDGE_STYLE_SAMPLE_PAGES", "18"))))
    except ValueError:
        return 18


def style_llm_distill() -> bool:
    load_dotenv()
    raw = os.environ.get("MYKNOWLEDGE_STYLE_LLM_DISTILL", "1").strip().lower()
    return raw not in ("0", "false", "no")


def style_refresh_hours() -> float:
    load_dotenv()
    try:
        return max(1.0, float(os.environ.get("MYKNOWLEDGE_STYLE_REFRESH_HOURS", "24")))
    except ValueError:
        return 24.0


def _style_path(root: Path | None = None) -> Path:
    base = wiki_root() if root is None else root
    d = base / ".rag" if (base / ".rag").exists() else RAG_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d / STYLE_FILE


def _strip_markdown(text: str) -> str:
    t = re.sub(r"```[\s\S]*?```", " ", text)
    t = re.sub(r"`[^`]+`", " ", t)
    t = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"^#{1,6}\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"^>\s?", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s*[-*+]\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s*\d+\.\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"\|", " ", t)
    t = re.sub(r"-{3,}", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?；;])\s*|\n+", text)
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if len(p) >= 4:
            out.append(p)
    return out


def _analyze_plain(text: str) -> dict[str, Any]:
    sentences = _split_sentences(text)
    if not sentences:
        return {}
    lengths = [len(s) for s in sentences]
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    list_lines = len(re.findall(r"^[\s]*[-*+]\s", text, re.MULTILINE))
    list_lines += len(re.findall(r"^[\s]*\d+\.\s", text, re.MULTILINE))
    headings = len(re.findall(r"^#{1,6}\s", text, re.MULTILINE))
    table_rows = len(re.findall(r"^\|.+\|$", text, re.MULTILINE))

    starters: Counter[str] = Counter()
    for s in sentences[:200]:
        m = re.match(r"^([\u4e00-\u9fffA-Za-z「『（(]{1,8})", s)
        if m:
            starters[m.group(1)] += 1

    connectors = Counter()
    for word in ("因此", "所以", "但是", "然而", "此外", "同时", "首先", "其次", "总之", "换言之", "例如", "也就是说"):
        connectors[word] = text.count(word)

    question_ratio = sum(1 for s in sentences if "?" in s or "？" in s) / max(len(sentences), 1)
    exclaim_ratio = sum(1 for s in sentences if "!" in s or "！" in s) / max(len(sentences), 1)

    return {
        "sentence_count": len(sentences),
        "avg_sentence_len": round(sum(lengths) / len(lengths), 1),
        "median_sentence_len": sorted(lengths)[len(lengths) // 2],
        "paragraph_count": max(len(paras), 1),
        "avg_paragraph_sentences": round(len(sentences) / max(len(paras), 1), 1),
        "list_line_ratio": round(list_lines / max(len(text.splitlines()), 1), 3),
        "heading_density": round(headings / max(len(paras), 1), 2),
        "table_row_count": table_rows,
        "top_starters": [w for w, _ in starters.most_common(6)],
        "connectors": {k: v for k, v in connectors.most_common(8) if v > 0},
        "question_ratio": round(question_ratio, 3),
        "exclaim_ratio": round(exclaim_ratio, 3),
        "chars_analyzed": len(text),
    }


def _score_page(page: WikiPage) -> float:
    body = page.body.strip()
    if len(body) < 120:
        return 0.0
    score = min(len(body) / 800.0, 3.0)
    if page.status == "published":
        score += 1.5
    if page.type in ("note", "concept", "comparison"):
        score += 1.0
    elif page.type == "source":
        score += 0.3
    if page.rel_path.startswith("inbox/"):
        score *= 0.5
    return score


def _select_pages(pages: list[WikiPage], limit: int) -> list[WikiPage]:
    ranked = sorted(pages, key=_score_page, reverse=True)
    picked: list[WikiPage] = []
    seen_prefix: set[str] = set()
    for p in ranked:
        if _score_page(p) <= 0:
            continue
        prefix = p.rel_path.split("/")[0]
        if prefix in seen_prefix and len(picked) >= limit // 2:
            continue
        picked.append(p)
        seen_prefix.add(prefix)
        if len(picked) >= limit:
            break
    return picked


def _collect_excerpts(pages: list[WikiPage], max_chars: int = MAX_EXCERPT_CHARS) -> tuple[str, list[str]]:
    parts: list[str] = []
    titles: list[str] = []
    used = 0
    for p in pages:
        body = p.body.strip()
        if not body:
            continue
        chunk = body[: min(900, len(body))]
        block = f"### {p.title}\n{chunk}"
        if used + len(block) > max_chars:
            remain = max_chars - used
            if remain < 200:
                break
            block = block[:remain]
        parts.append(block)
        titles.append(p.title)
        used += len(block)
        if used >= max_chars:
            break
    return "\n\n".join(parts), titles


def _heuristic_summary(metrics: dict[str, Any]) -> str:
    if not metrics:
        return "（样本不足，暂无法归纳句式习惯）"
    avg = metrics.get("avg_sentence_len", 0)
    if avg <= 18:
        pace = "短句为主、节奏紧凑"
    elif avg <= 32:
        pace = "句长适中、叙述与说明并重"
    else:
        pace = "偏长句、适合展开论述"

    structure_bits: list[str] = []
    if metrics.get("list_line_ratio", 0) >= 0.15:
        structure_bits.append("常用条目式列举")
    if metrics.get("heading_density", 0) >= 0.4:
        structure_bits.append("小节标题分层清晰")
    if metrics.get("table_row_count", 0) >= 3:
        structure_bits.append("习惯用表格做对比或清单")

    tone_bits: list[str] = []
    if metrics.get("question_ratio", 0) >= 0.08:
        tone_bits.append("偶用设问引导")
    if metrics.get("exclaim_ratio", 0) >= 0.05:
        tone_bits.append("语气略带强调")
    connectors = metrics.get("connectors") or {}
    if connectors:
        top_conn = ", ".join(list(connectors.keys())[:4])
        tone_bits.append(f"常见衔接词：{top_conn}")

    starters = metrics.get("top_starters") or []
    starter_line = f"常见起句：{'、'.join(starters[:5])}" if starters else ""

    lines = [f"句长特征：{pace}（均句长约 {avg} 字）。"]
    if structure_bits:
        lines.append("结构习惯：" + "；".join(structure_bits) + "。")
    if tone_bits:
        lines.append("语气习惯：" + "；".join(tone_bits) + "。")
    if starter_line:
        lines.append(starter_line + "。")
    return "\n".join(lines)


def _distill_with_llm(excerpts: str, heuristic: str) -> str:
    from .llm import _chat

    system = (
        "你是写作风格分析师。根据用户知识库原文摘录，归纳其语气、句式与行文习惯。"
        "只描述可观察到的风格，不要评价好坏，不要编造摘录中不存在的习惯。"
        "输出 4–6 条 bullet，每条一行，中文，具体可操作（例如「偏好先结论后依据」）。"
    )
    user = (
        f"统计摘要（供参考）：\n{heuristic}\n\n"
        f"原文摘录：\n{excerpts[:9000]}\n\n"
        "请输出风格要点 bullet 列表："
    )
    try:
        raw = _chat(system, user, kind="produce")
        bullets = []
        for line in raw.splitlines():
            line = re.sub(r"^[\s\-*•\d.)]+", "", line.strip())
            if len(line) >= 6:
                bullets.append(line)
        if bullets:
            return "\n".join(f"- {b}" for b in bullets[:8])
    except Exception:
        pass
    return ""


def refresh_style_profile(
    force: bool = False,
    root: Path | None = None,
    *,
    include_llm: bool | None = None,
) -> dict[str, Any]:
    """Rebuild cached style profile from wiki pages."""
    existing = load_style_profile(root)
    if not force and not _profile_stale(existing):
        return existing

    pages = [
        p
        for p in list_pages(root=root, include_inbox=False)
        if p.body.strip() and not p.rel_path.startswith("assets/")
    ]
    if not pages:
        pages = [p for p in list_pages(root=root, include_inbox=True) if p.body.strip()]

    sample_n = style_sample_pages()
    picked = _select_pages(pages, sample_n)
    excerpts, titles = _collect_excerpts(picked)

    plain = _strip_markdown(excerpts)
    metrics = _analyze_plain(plain)
    heuristic = _heuristic_summary(metrics)

    llm_block = str(existing.get("llm_summary") or "")
    should_distill = include_llm if include_llm is not None else style_llm_distill()
    if should_distill and len(plain) >= 400 and (include_llm is True or not llm_block or _profile_stale(existing)):
        distilled = _distill_with_llm(excerpts, heuristic)
        if distilled:
            llm_block = distilled

    profile: dict[str, Any] = {
        "updated_at": datetime.now(BEIJING).strftime("%Y-%m-%dT%H:%M:%S%z"),
        "sample_count": len(picked),
        "sample_titles": titles[:12],
        "metrics": metrics,
        "heuristic_summary": heuristic,
        "llm_summary": llm_block,
    }
    path = _style_path(root)
    path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return profile


def load_style_profile(root: Path | None = None) -> dict[str, Any]:
    path = _style_path(root)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _profile_stale(profile: dict[str, Any]) -> bool:
    if not profile:
        return True
    updated = profile.get("updated_at") or ""
    try:
        dt = datetime.strptime(updated.replace("+0800", "+08:00"), "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return True
    age = datetime.now(BEIJING) - dt
    return age > timedelta(hours=style_refresh_hours())


_profile_lock_time = 0.0


def get_style_profile(refresh_if_stale: bool = True, root: Path | None = None) -> dict[str, Any]:
    global _profile_lock_time
    if not style_enabled():
        return {}
    profile = load_style_profile(root)
    if refresh_if_stale and _profile_stale(profile):
        now = time.time()
        if now - _profile_lock_time > 5.0:
            _profile_lock_time = now
            try:
                profile = refresh_style_profile(force=True, root=root, include_llm=True)
            except Exception:
                pass
    return profile


def format_style_block(profile: dict[str, Any] | None = None, *, refresh_if_stale: bool = True) -> str:
    if not style_enabled():
        return ""
    profile = profile or get_style_profile(refresh_if_stale=refresh_if_stale)
    if not profile:
        return ""

    parts = [
        "## 知识库写作风格（请模仿，勿违背事实约束）",
        "以下从用户已有笔记中归纳；回答与产出时在**不增添片段外事实**的前提下，对齐语气、句式和段落习惯。",
        "",
        profile.get("heuristic_summary") or "",
    ]
    llm = (profile.get("llm_summary") or "").strip()
    if llm:
        parts.extend(["", "### 行文习惯要点", llm])

    samples = profile.get("sample_titles") or []
    if samples:
        parts.extend(["", f"参考条目示例：{', '.join(samples[:6])}"])

    parts.extend(
        [
            "",
            "### 表达品质（在 grounded 前提下尽量做到）",
            "- 像高水平助手一样**整合**多段片段：归类、对比、因果链梳理，避免逐段复述。",
            "- 段落衔接自然、层次清楚；先给可直接使用的结论，再列依据。",
            "- 模仿上述风格，但**禁止**为求流畅而编造片段中不存在的信息。",
        ]
    )
    return "\n".join(p for p in parts if p is not None).strip()


def get_style_block(*, refresh_if_stale: bool = True) -> str:
    return format_style_block(refresh_if_stale=refresh_if_stale)
