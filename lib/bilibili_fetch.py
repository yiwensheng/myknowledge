"""Fetch Bilibili video subtitles (no audio transcription) for wiki ingest."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from .runtime_tools import find_ffmpeg, find_ytdlp

_NO_SUB_MSG = "该视频无可用字幕，请粘贴文稿或换有字幕的视频"
_NO_YTDLP_MSG = (
    "未找到 yt-dlp。正式安装包应含 third_party\\yt-dlp\\yt-dlp.exe；"
    "开发机可运行 python scripts/setup_optional_tools.py，或设置 MYKNOWLEDGE_YTDLP_PATH"
)

# Prefer simplified Chinese / AI Chinese, then traditional, then any.
_LANG_PREF = (
    "zh-Hans",
    "zh-CN",
    "zh",
    "ai-zh",
    "zh-Hant",
    "zh-TW",
    "zh-HK",
)


def is_bilibili_url(url: str) -> bool:
    host = (urlparse(url).netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host == "b23.tv" or host.endswith(".b23.tv") or "bilibili.com" in host


def pick_subtitle_lang(available: dict[str, list]) -> str | None:
    """Pick best language key from yt-dlp subtitles / automatic_captions maps."""
    if not available:
        return None
    keys = list(available.keys())
    lower_map = {k.lower(): k for k in keys}
    for pref in _LANG_PREF:
        if pref.lower() in lower_map:
            return lower_map[pref.lower()]
    for pref in _LANG_PREF:
        for lk, orig in lower_map.items():
            if lk.startswith(pref.lower()) or pref.lower() in lk:
                return orig
    # any Chinese-ish
    for lk, orig in lower_map.items():
        if "zh" in lk or "chi" in lk or "cn" in lk:
            return orig
    return keys[0]


def vtt_to_text(vtt: str) -> str:
    """Strip WEBVTT timestamps/headers to plain lines."""
    lines: list[str] = []
    for raw in vtt.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.upper().startswith("WEBVTT"):
            continue
        if line.upper().startswith("NOTE"):
            continue
        if "-->" in line:
            continue
        if re.match(r"^\d+$", line):
            continue
        # drop simple cue settings tags
        line = re.sub(r"<[^>]+>", "", line)
        if line:
            lines.append(line)
    # collapse consecutive duplicates (common in auto subs)
    out: list[str] = []
    for line in lines:
        if out and out[-1] == line:
            continue
        out.append(line)
    return "\n".join(out).strip()


def _merged_caption_maps(info: dict) -> dict[str, list]:
    merged: dict[str, list] = {}
    for key in ("subtitles", "automatic_captions"):
        block = info.get(key) or {}
        if not isinstance(block, dict):
            continue
        for lang, tracks in block.items():
            if tracks:
                merged[lang] = tracks
    return merged


def _ytdlp_json(url: str, ytdlp: str) -> dict:
    cmd = [ytdlp, "-J", "--no-playlist", "--skip-download", url]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"yt-dlp 执行失败: {e}") from e
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:400]
        raise RuntimeError(f"无法解析 B 站链接: {err or proc.returncode}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError("yt-dlp 返回的元数据不是合法 JSON") from e


def _download_subs(url: str, ytdlp: str, lang: str, out_dir: Path) -> Path | None:
    outtmpl = str(out_dir / "%(id)s")
    cmd = [
        ytdlp,
        "--skip-download",
        "--no-playlist",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs",
        lang,
        "--convert-subs",
        "vtt",
        "-o",
        outtmpl,
        url,
    ]
    ffmpeg = find_ffmpeg()
    env = os.environ.copy()
    if ffmpeg:
        env["PATH"] = str(Path(ffmpeg).parent) + os.pathsep + env.get("PATH", "")
    try:
        subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=240,
            check=False,
            env=env,
            cwd=str(out_dir),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    # Prefer .vtt then .srt
    cands = sorted(out_dir.glob("*.vtt")) + sorted(out_dir.glob("*.srt"))
    return cands[0] if cands else None


def build_bilibili_markdown(
    *,
    title: str,
    uploader: str,
    url: str,
    lang: str,
    body: str,
    video_id: str = "",
) -> str:
    parts = [
        f"# {title}",
        "",
        f"- 来源: {url}",
        f"- UP主: {uploader or '未知'}",
    ]
    if video_id:
        parts.append(f"- 视频 ID: {video_id}")
    parts.append(f"- 字幕语言: {lang}")
    parts.append("")
    parts.append("## 字幕文稿")
    parts.append("")
    parts.append(body)
    parts.append("")
    return "\n".join(parts)


def fetch_bilibili(
    url: str,
    progress: Callable[[str, str], None] | None = None,
):
    """Fetch Bilibili page as Markdown from subtitles only. Returns url_fetch.FetchedPage."""
    from .url_fetch import FetchedPage

    ytdlp = find_ytdlp()
    if not ytdlp:
        raise RuntimeError(_NO_YTDLP_MSG)

    if progress:
        progress("fetch", "正在获取 B 站元数据…")
    info = _ytdlp_json(url, ytdlp)
    title = str(info.get("title") or "").strip() or "B站视频"
    uploader = str(info.get("uploader") or info.get("channel") or "").strip()
    webpage = str(info.get("webpage_url") or url).strip()
    video_id = str(info.get("id") or "").strip()

    caps = _merged_caption_maps(info)
    lang = pick_subtitle_lang(caps)
    if not lang:
        raise RuntimeError(_NO_SUB_MSG)

    if progress:
        progress("fetch", f"正在获取 B 站字幕（{lang}）…")
    with tempfile.TemporaryDirectory(prefix="yizhi-bili-") as td:
        sub_path = _download_subs(webpage or url, ytdlp, lang, Path(td))
        if not sub_path or not sub_path.is_file():
            raise RuntimeError(_NO_SUB_MSG)
        raw = sub_path.read_text(encoding="utf-8", errors="replace")
        if sub_path.suffix.lower() == ".vtt":
            body = vtt_to_text(raw)
        else:
            # crude srt strip
            body = vtt_to_text(re.sub(r"^\d+\s*$", "", raw, flags=re.M))
        if len(body) < 40:
            raise RuntimeError(_NO_SUB_MSG)

    md = build_bilibili_markdown(
        title=title,
        uploader=uploader,
        url=webpage or url,
        lang=lang,
        body=body,
        video_id=video_id,
    )
    return FetchedPage(
        url=webpage or url,
        title=title,
        markdown=md,
        method="bilibili-subtitle",
    )
