#!/usr/bin/env python3
"""Initialize Myknowledge wiki directory tree."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

MYK_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WIKI_ROOT = MYK_ROOT

DIRS = [
    "inbox",
    "concepts",
    "entities",
    "sources",
    "comparisons",
    "notes",
    "templates",
    "index",
    "archive",
    "output",
    "assets",
]

PURPOSE = """# 知识库研究方向

> 编辑本文件，约束 AI 分类与标签，避免 tags 膨胀。

## 关注领域

- 个人效率与知识管理
- 软件开发与 AI 工具
- 行业资讯与方法论

## 排除 / 低优先级

- 纯娱乐八卦、临时促销信息

## 标签约定

- 使用 2–4 个 tag
- 同一概念只用一种 tag 写法

## 开放问题记录区

- 

"""


def resolve_wiki_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("WIKI_ROOT") or os.environ.get("MYKNOWLEDGE_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return DEFAULT_WIKI_ROOT.resolve()


def init_wiki(wiki_root: Path, force: bool = False) -> None:
    wiki_root.mkdir(parents=True, exist_ok=True)
    for name in DIRS:
        (wiki_root / name).mkdir(exist_ok=True)
    (wiki_root / ".rag").mkdir(exist_ok=True)
    (wiki_root / ".memory").mkdir(exist_ok=True)
    (wiki_root / ".memory" / "sessions").mkdir(exist_ok=True)
    (wiki_root / "notes" / "qa").mkdir(parents=True, exist_ok=True)
    # 技能目录：优先用户可写的 wiki_root；安装目录（Program Files）可能无写权限
    (wiki_root / "skills").mkdir(exist_ok=True)
    try:
        (MYK_ROOT / "skills").mkdir(exist_ok=True)
    except OSError as e:
        print(f"Note: skip install-dir skills/ ({e})")
    for sub in ("documents", "images", "audio", "video", ".extracted"):
        (wiki_root / "assets" / sub).mkdir(parents=True, exist_ok=True)

    purpose_path = wiki_root / "purpose.md"
    if not purpose_path.exists() or force:
        purpose_path.write_text(PURPOSE, encoding="utf-8")

    src_templates = MYK_ROOT / "templates"
    wiki_templates = wiki_root / "templates"
    if src_templates.is_dir():
        for src in src_templates.glob("*.md"):
            dst = wiki_templates / src.name
            if not dst.exists() or force:
                shutil.copy2(src, dst)

    cache_path = wiki_root / ".wiki-cache.json"
    if not cache_path.exists():
        cache_path.write_text("{}\n", encoding="utf-8")

    try:
        if str(MYK_ROOT) not in sys.path:
            sys.path.insert(0, str(MYK_ROOT))
        from lib.memory_db import ensure_db

        ensure_db(wiki_root)
    except Exception as e:
        print(f"Note: memory SQLite skipped: {e}")

    print(f"Wiki initialized: {wiki_root}")

    # Loop Engineering scaffold (STATE.md, LOOP.md, .loop/)
    try:
        if str(MYK_ROOT) not in sys.path:
            sys.path.insert(0, str(MYK_ROOT))
        from lib.loop_engine import ensure_loop_scaffold

        ensure_loop_scaffold(wiki_root)
    except Exception as e:
        print(f"Note: loop scaffold skipped: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize Myknowledge wiki.")
    parser.add_argument("--root")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    init_wiki(resolve_wiki_root(args.root), force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
