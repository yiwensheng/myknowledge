#!/usr/bin/env python3
"""Migrate legacy .memory JSON / jsonl into SQLite (.memory/memory.db)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

MYK_ROOT = Path(__file__).resolve().parent.parent
if str(MYK_ROOT) not in sys.path:
    sys.path.insert(0, str(MYK_ROOT))

from lib.config import load_dotenv, wiki_root  # noqa: E402
from lib.memory_db import db_path, ensure_db, migrate_from_files  # noqa: E402


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Migrate Myknowledge memory files to SQLite")
    parser.add_argument(
        "--wiki-root",
        default=os.environ.get("WIKI_ROOT") or os.environ.get("MYKNOWLEDGE_ROOT") or str(MYK_ROOT),
        help="Wiki root directory",
    )
    args = parser.parse_args()
    root = Path(args.wiki_root).expanduser().resolve()
    ensure_db(root)
    stats = migrate_from_files(root)
    print(f"SQLite: {db_path(root)}")
    print(
        f"Migrated this run: sessions={stats['sessions']} "
        f"turns={stats['turns']} qa={stats['qa_entries']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
