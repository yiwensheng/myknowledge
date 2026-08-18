#!/usr/bin/env python3
"""Ensure RAG FTS5 schema exists and optionally rebuild from chunks.json."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

MYK_ROOT = Path(__file__).resolve().parent.parent
if str(MYK_ROOT) not in sys.path:
    sys.path.insert(0, str(MYK_ROOT))

from lib.config import load_dotenv, wiki_root  # noqa: E402
from lib.rag import _index_path  # noqa: E402
from lib.rag_fts import ensure_fts_schema, fts5_stats, sync_fts_index  # noqa: E402


def main() -> int:
    load_dotenv()
    root = Path(os.environ.get("WIKI_ROOT") or os.environ.get("MYKNOWLEDGE_ROOT") or MYK_ROOT).resolve()
    os.environ.setdefault("MYKNOWLEDGE_FTS5", "1")

    if not ensure_fts_schema(root):
        print("FTS5 disabled or schema not created")
        return 1

    idx = _index_path(root)
    if not idx.is_file():
        print(f"No index at {idx}")
        return 0

    data = json.loads(idx.read_text(encoding="utf-8"))
    chunks = list(data.get("chunks") or [])
    stats = sync_fts_index(chunks, root)
    st = fts5_stats(root)
    print(f"FTS5 synced: {stats.get('synced', 0)} chunks · db={st}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
