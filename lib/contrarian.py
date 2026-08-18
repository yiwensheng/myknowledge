"""Contrarian loop: collect core assumptions and surface contradictions (never auto-merge)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import contrarian_enabled, wiki_root
from .wiki import list_pages, parse_frontmatter, save_page

BEIJING = timezone(timedelta(hours=8))
_ASSUMPTION_HEADING = re.compile(r"^###\s*核心假设\s*$", re.MULTILINE)


def collect_assumptions(root: Path | None = None, *, limit: int = 120) -> list[dict[str, str]]:
    """Collect (rel_path, title, assumption) from frontmatter or analysis section."""
    root = root or wiki_root()
    out: list[dict[str, str]] = []
    for page in list_pages(root, include_inbox=False):
        if page.type == "comparison" and "矛盾扫描" in (page.title or ""):
            continue
        try:
            text = page.path.read_text(encoding="utf-8")
        except OSError:
            continue
        meta, body = parse_frontmatter(text)
        raw = meta.get("assumptions") or []
        items: list[str] = []
        if isinstance(raw, list):
            items = [str(x).strip() for x in raw if str(x).strip()]
        elif isinstance(raw, str) and raw.strip():
            items = [raw.strip()]
        if not items:
            items = _assumptions_from_body(body)
        if not items and page.type in ("concept", "comparison", "note"):
            # Fallback: first key points from analysis block
            items = _key_points_fallback(body)[:2]
        for a in items:
            out.append(
                {
                    "rel_path": page.rel_path,
                    "title": page.title,
                    "assumption": a[:400],
                }
            )
            if len(out) >= limit:
                return out
    return out


def _assumptions_from_body(body: str) -> list[str]:
    m = _ASSUMPTION_HEADING.search(body)
    if not m:
        return []
    rest = body[m.end() :]
    next_h = re.search(r"^#{1,3}\s+", rest, re.MULTILINE)
    block = rest[: next_h.start()] if next_h else rest
    items: list[str] = []
    for line in block.splitlines():
        s = line.strip().lstrip("-•* ").strip()
        if s and not s.startswith("#"):
            items.append(s)
        if len(items) >= 8:
            break
    return items


def _key_points_fallback(body: str) -> list[str]:
    m = re.search(r"^###\s*核心要点\s*$", body, re.MULTILINE)
    if not m:
        return []
    rest = body[m.end() :]
    next_h = re.search(r"^#{1,3}\s+", rest, re.MULTILINE)
    block = rest[: next_h.start()] if next_h else rest
    items: list[str] = []
    for line in block.splitlines():
        s = line.strip().lstrip("-•* ").strip()
        if s:
            items.append(s)
        if len(items) >= 4:
            break
    return items


def _parse_conflicts(raw: str) -> list[dict[str, Any]]:
    text = raw.strip()
    m = re.search(r"\{[\s\S]*\}|\[[\s\S]*\]", text)
    if m:
        text = m.group(0)
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("conflicts") or data.get("items") or []
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        a = str(item.get("a") or item.get("assumption_a") or "").strip()
        b = str(item.get("b") or item.get("assumption_b") or "").strip()
        why = str(item.get("why") or item.get("reason") or "").strip()
        path_a = str(item.get("path_a") or item.get("rel_path_a") or "").strip()
        path_b = str(item.get("path_b") or item.get("rel_path_b") or "").strip()
        if a and b and a != b:
            out.append({"a": a, "b": b, "why": why, "path_a": path_a, "path_b": path_b})
    return out[:20]


def scan_contradictions(
    root: Path | None = None,
    *,
    write_draft: bool = True,
    max_assumptions: int = 80,
) -> dict[str, Any]:
    """Find conflicting assumptions; optionally write a comparison draft (no merge)."""
    root = root or wiki_root()
    assumptions = collect_assumptions(root, limit=max_assumptions)
    if len(assumptions) < 2:
        return {
            "ok": True,
            "assumptions": len(assumptions),
            "conflicts": [],
            "draft_path": None,
            "message": "假设不足两条，无法对照。可先开启「矛盾检测」并重新入库分析，或在笔记 frontmatter 写 assumptions。",
            "enabled": contrarian_enabled(),
        }

    from .llm import _chat

    numbered = []
    for i, row in enumerate(assumptions, 1):
        numbered.append(
            f"{i}. [{row['rel_path']}] 《{row['title']}》：{row['assumption']}"
        )
    system = (
        "你是知识库审稿人。只根据给定的「核心假设」列表，找出互相矛盾或不可同时成立的成对假设。"
        "只输出 JSON 对象：{\"conflicts\":[{\"a\":\"假设原文\",\"b\":\"假设原文\","
        "\"path_a\":\"路径\",\"path_b\":\"路径\",\"why\":\"矛盾说明\"}]}。"
        "没有矛盾时 conflicts 为空数组。禁止编造列表中没有的假设；不要提出合并方案。"
    )
    user = "假设列表：\n" + "\n".join(numbered)
    try:
        raw = _chat(system, user, kind="ask")
        conflicts = _parse_conflicts(raw)
    except Exception as exc:
        return {
            "ok": False,
            "assumptions": len(assumptions),
            "conflicts": [],
            "draft_path": None,
            "message": f"扫描失败：{exc}",
            "enabled": contrarian_enabled(),
        }

    draft_path = None
    if write_draft and conflicts:
        draft_path = _write_conflict_draft(conflicts, assumptions, root)

    return {
        "ok": True,
        "assumptions": len(assumptions),
        "conflicts": conflicts,
        "draft_path": draft_path,
        "message": (
            f"发现 {len(conflicts)} 组矛盾，已写入对照稿（未自动合并）。"
            if conflicts and draft_path
            else (
                f"发现 {len(conflicts)} 组矛盾。"
                if conflicts
                else "未发现明显矛盾。"
            )
        ),
        "enabled": contrarian_enabled(),
    }


def _write_conflict_draft(
    conflicts: list[dict[str, Any]],
    assumptions: list[dict[str, str]],
    root: Path,
) -> str:
    now = datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M")
    stamp = datetime.now(BEIJING).strftime("%Y%m%d-%H%M")
    title = f"矛盾扫描 {stamp}"
    lines = [
        f"# {title}",
        "",
        "> 由矛盾检测生成。仅展示冲突，**不自动合并**笔记。请人工决定保留哪一侧。",
        "",
        f"- 扫描时间：{now}",
        f"- 参与假设数：{len(assumptions)}",
        f"- 冲突组数：{len(conflicts)}",
        "",
        "## 冲突对照",
        "",
    ]
    for i, c in enumerate(conflicts, 1):
        lines.append(f"### 冲突 {i}")
        lines.append("")
        lines.append(f"- **假设 A**（`{c.get('path_a') or '—'}`）：{c['a']}")
        lines.append(f"- **假设 B**（`{c.get('path_b') or '—'}`）：{c['b']}")
        if c.get("why"):
            lines.append(f"- **为何矛盾**：{c['why']}")
        lines.append("- **处理**：待人工裁定（保留 A / 保留 B / 改写 / 分场景）")
        lines.append("")
    body = "\n".join(lines)
    page = save_page(
        page_type="comparison",
        title=title,
        body=body,
        tags=["矛盾检测", "contrarian"],
        status="draft",
        root=root,
        extra_meta={"source": "contrarian-scan"},
    )
    return page.rel_path
