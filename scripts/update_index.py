#!/usr/bin/env python3
"""Scan wiki Markdown files and rebuild six index files under index/."""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path

if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

BEIJING = timezone(timedelta(hours=8))
DEFAULT_WIKI_ROOT = Path(__file__).resolve().parent.parent

CONTENT_DIRS = ("concepts", "entities", "sources", "comparisons", "notes", "archive")
SCAN_DIRS = CONTENT_DIRS + ("inbox",)
VALID_TYPES = {"concept", "entity", "source", "comparison", "note"}
VALID_STATUS = {"draft", "refined", "archived"}
MAX_GRAPH_NODES = 50


@dataclass
class WikiPage:
    path: Path
    rel_path: str
    title: str
    type: str
    tags: list[str]
    created: str
    updated: str
    status: str
    links: list[str]
    body: str = ""


def resolve_wiki_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("WIKI_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return DEFAULT_WIKI_ROOT.resolve()


def parse_yaml_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n(.*)", text, re.DOTALL)
    if not match:
        return {}, text
    raw_yaml, body = match.group(1), match.group(2)
    try:
        import yaml  # type: ignore

        meta = yaml.safe_load(raw_yaml) or {}
        if not isinstance(meta, dict):
            meta = {}
        return meta, body
    except Exception:
        return _parse_yaml_fallback(raw_yaml), body


def _parse_yaml_fallback(raw: str) -> dict:
    meta: dict = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip()
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            if not inner:
                meta[key] = []
            else:
                meta[key] = [
                    item.strip().strip('"').strip("'")
                    for item in inner.split(",")
                    if item.strip()
                ]
        else:
            meta[key] = val.strip('"').strip("'")
    return meta


def slugify(title: str) -> str:
    s = title.strip()
    s = re.sub(r'[<>:"/\\|?*]', "", s)
    s = re.sub(r"\s+", "-", s)
    return s[:80] or "untitled"


def collect_pages(wiki_root: Path) -> list[WikiPage]:
    pages: list[WikiPage] = []
    for dir_name in SCAN_DIRS:
        base = wiki_root / dir_name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            if path.name.startswith("."):
                continue
            rel_parts = path.relative_to(wiki_root).parts
            if "inbox-processed" in rel_parts:
                continue
            text = path.read_text(encoding="utf-8")
            meta, body = parse_yaml_frontmatter(text)
            rel = path.relative_to(wiki_root).as_posix()
            pages.append(
                WikiPage(
                    path=path,
                    rel_path=rel,
                    title=str(meta.get("title") or path.stem),
                    type=str(meta.get("type") or "note"),
                    tags=[str(t) for t in (meta.get("tags") or [])],
                    created=str(meta.get("created") or ""),
                    updated=str(meta.get("updated") or meta.get("created") or ""),
                    status=str(meta.get("status") or "draft"),
                    links=[str(x) for x in (meta.get("links") or [])],
                    body=body,
                )
            )
    return pages


def resolve_link(wiki_root: Path, from_dir: Path, link: str) -> Path | None:
    if link.startswith("http://") or link.startswith("https://"):
        return None
    target = (from_dir / link).resolve()
    try:
        target.relative_to(wiki_root.resolve())
    except ValueError:
        return None
    return target if target.exists() else None


def beijing_now_str() -> str:
    return datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M")


def build_tags_md(pages: list[WikiPage], generated_at: str) -> str:
    by_tag: dict[str, list[WikiPage]] = defaultdict(list)
    for p in pages:
        if p.path.parts[-2] == "inbox":
            continue
        if not p.tags:
            by_tag["(无标签)"].append(p)
        else:
            for tag in p.tags:
                by_tag[tag].append(p)

    lines = [
        "---",
        "title: 标签索引",
        "generated_at: " + generated_at,
        "---",
        "",
        "# 标签索引",
        "",
    ]
    for tag in sorted(by_tag.keys(), key=lambda x: x.lower()):
        lines.append(f"## {tag}")
        lines.append("")
        for p in sorted(by_tag[tag], key=lambda x: x.title):
            lines.append(f"- [{p.title}](../{p.rel_path}) — `{p.type}` / `{p.status}`")
        lines.append("")
    return "\n".join(lines)


def _safe_node_id(title: str) -> str:
    nid = re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fff]", "_", title)
    return nid[:40] or "node"


def build_knowledge_map_md(pages: list[WikiPage], wiki_root: Path, generated_at: str) -> str:
    content_pages = [p for p in pages if p.path.parts[-2] != "inbox" and p.path.parts[-2] != "archive"]
    graph_pages = content_pages[:MAX_GRAPH_NODES]

    lines = [
        "---",
        "title: 知识关联图",
        "generated_at: " + generated_at,
        "---",
        "",
        "# 知识关联图",
        "",
        f"> 展示前 {len(graph_pages)} 个节点（上限 {MAX_GRAPH_NODES}）",
        "",
        "```mermaid",
        "flowchart LR",
    ]

    id_map: dict[str, str] = {}
    for p in graph_pages:
        nid = _safe_node_id(p.title)
        base = nid
        i = 1
        while nid in id_map.values():
            nid = f"{base}_{i}"
            i += 1
        id_map[p.rel_path] = nid
        label = p.title.replace('"', "'")
        lines.append(f'  {nid}["{label}"]')

    edge_count = 0
    for p in graph_pages:
        src = id_map.get(p.rel_path)
        if not src:
            continue
        for link in p.links:
            target_path = resolve_link(wiki_root, p.path.parent, link)
            if not target_path:
                continue
            try:
                rel = target_path.relative_to(wiki_root).as_posix()
            except ValueError:
                continue
            dst = id_map.get(rel)
            if dst and src != dst:
                lines.append(f"  {src} --> {dst}")
                edge_count += 1

    if edge_count == 0 and graph_pages:
        lines.append("  empty[暂无链接]")
    lines.extend(["```", ""])
    return "\n".join(lines)


def build_stats_md(pages: list[WikiPage], generated_at: str) -> str:
    content = [p for p in pages if p.path.parts[-2] != "inbox"]
    type_counts = Counter(p.type for p in content)
    status_counts = Counter(p.status for p in content)
    dir_counts = Counter(p.path.parts[-2] for p in content)

    lines = [
        "---",
        "title: 统计概览",
        "generated_at: " + generated_at,
        "---",
        "",
        "# 统计概览",
        "",
        f"- 总条目（不含 inbox）：**{len(content)}**",
        "",
        "## 按类型",
        "",
    ]
    for t in sorted(type_counts.keys()):
        lines.append(f"- `{t}`: {type_counts[t]}")
    lines.extend(["", "## 按状态", ""])
    for s in sorted(status_counts.keys()):
        lines.append(f"- `{s}`: {status_counts[s]}")
    lines.extend(["", "## 按目录", ""])
    for d in sorted(dir_counts.keys()):
        lines.append(f"- `{d}/`: {dir_counts[d]}")
    lines.append("")
    return "\n".join(lines)


def build_open_questions_md(
    pages: list[WikiPage], wiki_root: Path, generated_at: str
) -> str:
    drafts: list[WikiPage] = []
    orphans: list[WikiPage] = []
    broken_links: list[tuple[WikiPage, str]] = []

    for p in pages:
        if p.path.parts[-2] in ("inbox", "archive"):
            continue
        if p.status == "draft":
            drafts.append(p)
        if not p.links:
            orphans.append(p)
        for link in p.links:
            if resolve_link(wiki_root, p.path.parent, link) is None and not link.startswith(
                "http"
            ):
                broken_links.append((p, link))

    purpose_questions: list[str] = []
    purpose_path = wiki_root / "purpose.md"
    if purpose_path.exists():
        text = purpose_path.read_text(encoding="utf-8")
        in_section = False
        for line in text.splitlines():
            if "开放问题记录区" in line:
                in_section = True
                continue
            if in_section and line.strip().startswith("- ") and len(line.strip()) > 2:
                purpose_questions.append(line.strip()[2:])

    lines = [
        "---",
        "title: 开放问题与缺口",
        "generated_at: " + generated_at,
        "---",
        "",
        "# 开放问题与缺口",
        "",
        "## 草稿（status: draft）",
        "",
    ]
    if drafts:
        for p in sorted(drafts, key=lambda x: x.title):
            lines.append(f"- [{p.title}](../{p.rel_path})")
    else:
        lines.append("- （无）")
    lines.extend(["", "## 孤岛（无 links）", ""])
    if orphans:
        for p in sorted(orphans, key=lambda x: x.title):
            lines.append(f"- [{p.title}](../{p.rel_path})")
    else:
        lines.append("- （无）")
    lines.extend(["", "## 断链（links 指向不存在文件）", ""])
    if broken_links:
        for p, link in broken_links:
            lines.append(f"- [{p.title}](../{p.rel_path}) → `{link}`")
    else:
        lines.append("- （无）")
    lines.extend(["", "## 待回答问题（来自 purpose.md）", ""])
    if purpose_questions:
        for q in purpose_questions:
            lines.append(f"- {q}")
    else:
        lines.append("- （无）")
    lines.append("")
    return "\n".join(lines)


def build_recent_md(pages: list[WikiPage], generated_at: str, limit: int = 20) -> str:
    content = [p for p in pages if p.path.parts[-2] != "inbox"]

    def sort_key(p: WikiPage) -> str:
        return p.updated or p.created or "1970-01-01"

    recent = sorted(content, key=sort_key, reverse=True)[:limit]
    lines = [
        "---",
        "title: 最近更新",
        "generated_at: " + generated_at,
        "---",
        "",
        "# 最近更新",
        "",
        "| 更新日期 | 标题 | 类型 | 状态 |",
        "|----------|------|------|------|",
    ]
    for p in recent:
        lines.append(
            f"| {p.updated or p.created or '-'} | [{p.title}](../{p.rel_path}) | `{p.type}` | `{p.status}` |"
        )
    lines.append("")
    return "\n".join(lines)


def build_sync_log_md(generated_at: str) -> str:
    return "\n".join(
        [
            "---",
            "title: 同步记录",
            "generated_at: " + generated_at,
            "---",
            "",
            "# 同步记录",
            "",
            "> 手动记录外部资料纳入知识库的情况（可选）。",
            "",
            "| 日期 | 来源 | 方式 | 条数 | 备注 |",
            "|------|------|------|------|------|",
            "| | | inbox / url / 外联目录 | | |",
            "",
        ]
    )


def update_indexes(wiki_root: Path) -> None:
    generated_at = beijing_now_str()
    pages = collect_pages(wiki_root)
    index_dir = wiki_root / "index"
    index_dir.mkdir(parents=True, exist_ok=True)

    outputs = {
        "tags.md": build_tags_md(pages, generated_at),
        "knowledge-map.md": build_knowledge_map_md(pages, wiki_root, generated_at),
        "stats.md": build_stats_md(pages, generated_at),
        "open-questions.md": build_open_questions_md(pages, wiki_root, generated_at),
        "recent.md": build_recent_md(pages, generated_at),
        "sync-log.md": build_sync_log_md(generated_at),
    }
    for name, content in outputs.items():
        (index_dir / name).write_text(content, encoding="utf-8")
        print(f"Wrote index/{name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild wiki index files.")
    parser.add_argument("--root", help="Wiki root directory")
    args = parser.parse_args()
    wiki_root = resolve_wiki_root(args.root)
    if not wiki_root.is_dir():
        print(f"Error: wiki root not found: {wiki_root}", file=sys.stderr)
        return 1
    update_indexes(wiki_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
