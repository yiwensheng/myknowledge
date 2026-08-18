#!/usr/bin/env python3
"""Verify PDF structure extraction prints table markers."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.extract import extract_text  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/verify_pdf_structure.py <file.pdf>")
        return 2
    path = Path(sys.argv[1])
    text = extract_text(path)
    has_table = "-表格" in text
    print(f"file={path}")
    print(f"chars={len(text)} has_table_marker={has_table}")
    # print first table block snippet
    if has_table:
        i = text.index("-表格")
        print(text[max(0, i - 20) : i + 200])
    else:
        print(text[:400])
    return 0 if has_table else 1


if __name__ == "__main__":
    raise SystemExit(main())
