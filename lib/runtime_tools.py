"""Resolve bundled or system optional tools (ffmpeg, bun, yt-dlp)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .config import ROOT

THIRD_PARTY = ROOT / "third_party"


def subprocess_run_hidden(cmd: list[str] | tuple[str, ...], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
    """Run a console tool without flashing a Windows console window (e.g. ffmpeg)."""
    if sys.platform == "win32":
        flags = int(kwargs.pop("creationflags", 0) or 0)
        kwargs["creationflags"] = flags | subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    return subprocess.run(cmd, **kwargs)


def bundled_ffmpeg_path() -> Path | None:
    for rel in (
        "ffmpeg/bin/ffmpeg.exe",
        "ffmpeg/ffmpeg.exe",
        "ffmpeg/bin/ffmpeg",
        "ffmpeg/ffmpeg",
    ):
        p = THIRD_PARTY / rel
        if p.is_file():
            return p
    return None


def _windows_ffmpeg_candidates() -> list[Path]:
    """本机常见安装位置（不依赖 PATH，避免构建时找不到却去 GitHub）。"""
    home = Path.home()
    return [
        Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
        Path(r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"),
        Path(r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe"),
        home / "scoop" / "apps" / "ffmpeg" / "current" / "bin" / "ffmpeg.exe",
        home / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe",
    ]


def find_ffmpeg() -> str | None:
    env = os.environ.get("MYKNOWLEDGE_FFMPEG_PATH", "").strip()
    if env and Path(env).is_file():
        return env
    bundled = bundled_ffmpeg_path()
    if bundled:
        return str(bundled)
    found = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if found:
        return found
    if sys.platform == "win32":
        for p in _windows_ffmpeg_candidates():
            if p.is_file():
                return str(p)
    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).is_file():
            return exe
    except Exception:
        pass
    return None


def bundled_bun_path() -> Path | None:
    for rel in ("bun/bun.exe", "bun/bun"):
        p = THIRD_PARTY / rel
        if p.is_file():
            return p
    return None


def find_bun() -> str | None:
    env = os.environ.get("MYKNOWLEDGE_BUN_PATH", "").strip()
    if env and Path(env).is_file():
        return env
    bundled = bundled_bun_path()
    if bundled:
        return str(bundled)
    found = shutil.which("bun") or shutil.which("bun.exe")
    if found:
        return found
    if sys.platform == "win32":
        npm_bin = Path.home() / "AppData" / "Roaming" / "npm"
        for name in ("bun.cmd", "bun.exe", "bun"):
            candidate = npm_bin / name
            if candidate.is_file():
                return str(candidate)
    return None


def bundled_ytdlp_path() -> Path | None:
    for rel in ("yt-dlp/yt-dlp.exe", "yt-dlp/yt-dlp", "yt-dlp.exe"):
        p = THIRD_PARTY / rel
        if p.is_file():
            return p
    return None


def find_ytdlp() -> str | None:
    env = os.environ.get("MYKNOWLEDGE_YTDLP_PATH", "").strip()
    if env and Path(env).is_file():
        return env
    bundled = bundled_ytdlp_path()
    if bundled:
        return str(bundled)
    found = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
    if found:
        return found
    if sys.platform == "win32":
        home = Path.home()
        for p in (
            home / "scoop" / "apps" / "yt-dlp" / "current" / "yt-dlp.exe",
            home / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links" / "yt-dlp.exe",
            Path(r"C:\yt-dlp\yt-dlp.exe"),
        ):
            if p.is_file():
                return str(p)
    return None
