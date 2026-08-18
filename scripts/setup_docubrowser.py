#!/usr/bin/env python3
"""Fetch and install bundled DocuBrowser (GPL-3.0) for 易知."""

from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "third_party" / "DocuBrowser"
REPO = "https://github.com/linuxrebel/DocuBrowser.git"
STAMP_FILE = ".pip_deps_stamp"

# requirements.txt package name -> import name
IMPORT_CHECKS: tuple[tuple[str, str], ...] = (
    ("pdfplumber", "pdfplumber"),
    ("pypdf", "pypdf"),
    ("python-docx", "docx"),
    ("python-pptx", "pptx"),
    ("openpyxl", "openpyxl"),
    ("ebooklib", "ebooklib"),
    ("beautifulsoup4", "bs4"),
    ("mobi", "mobi"),
    ("numpy", "numpy"),
    ("psutil", "psutil"),
    ("colorama", "colorama"),
)


def _requirements_fingerprint(req: Path) -> str:
    return hashlib.sha256(req.read_bytes()).hexdigest()


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def deps_satisfied() -> bool:
    return all(_module_available(mod) for _, mod in IMPORT_CHECKS)


def _read_stamp(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _write_stamp(path: Path, fingerprint: str) -> None:
    path.write_text(fingerprint + "\n", encoding="utf-8")


def ensure_python_deps(req: Path) -> None:
    stamp_path = TARGET / STAMP_FILE
    fingerprint = _requirements_fingerprint(req)
    if _read_stamp(stamp_path) == fingerprint and deps_satisfied():
        print("[DocuBrowser] Python 依赖已就绪（跳过 pip install）")
        return

    print("[DocuBrowser] 安装 Python 依赖 …")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "-r", str(req)],
        check=False,
    )
    if deps_satisfied():
        _write_stamp(stamp_path, fingerprint)
        print("[DocuBrowser] Python 依赖安装完成")
    else:
        missing = [pkg for pkg, mod in IMPORT_CHECKS if not _module_available(mod)]
        print(f"[DocuBrowser] 警告: 以下依赖可能未就绪: {', '.join(missing)}")


def main() -> int:
    if not (TARGET / "docubrowser.py").is_file():
        print(f"[DocuBrowser] 正在克隆到 {TARGET} …")
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--depth", "1", REPO, str(TARGET)],
            check=True,
        )
    else:
        print(f"[DocuBrowser] 已存在: {TARGET}")

    req = TARGET / "requirements.txt"
    if req.is_file():
        ensure_python_deps(req)
    print("[DocuBrowser] 就绪（GPL-3.0，见 third_party/DocuBrowser/LICENSE）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
