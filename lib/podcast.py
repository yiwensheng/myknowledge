"""Podcast script parsing and audio synthesis."""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

from .config import output_dir
from .podcast_merge import ffmpeg_available, merge_audio_segments
from .tts import synthesize_segments, tts_status

_SPEAKER_LINE = re.compile(
    r"^\s*(?:\*\*)?([^*：:\n]{1,12})(?:\*\*)?\s*[：:]\s*(.+?)\s*$"
)

_DIALOGUE_HEADINGS = ("对话脚本", "对话正文", "对话内容", "本期对话")
_STOP_HEADINGS = (
    "待人工确认",
    "参考依据",
    "参考资料",
    "依据来源",
    "引用来源",
    "来源说明",
    "附录",
    "脚注",
    "节目简介",
    "摘要",
)

_ALLOWED_SPEAKERS = frozenset({"主持人", "嘉宾"})


def _strip_md_heading(line: str) -> str:
    return re.sub(r"^#+\s*", "", line.strip())


def _normalize_section_title(title: str) -> str:
    """Strip markdown heading/bold wrappers for section-title matching."""
    t = _strip_md_heading(title)
    t = re.sub(r"^\*\*(.+?)\*\*$", r"\1", t.strip())
    return t.strip()


def _is_stop_section(title: str) -> bool:
    """True only when the whole line is a stop section title (not dialogue body)."""
    t = _normalize_section_title(title)
    if not t or len(t) > 24:
        return False
    return any(t == k or t.startswith(k) for k in _STOP_HEADINGS)


def _is_dialogue_section(title: str) -> bool:
    t = _normalize_section_title(title)
    return any(k in t for k in _DIALOGUE_HEADINGS) or t == "对话"


def extract_podcast_dialogue_text(content: str) -> str:
    """Keep only the dialogue-script block for TTS (exclude intro, citations, tables)."""
    content = re.sub(r"<!--.*?-->", "", content, flags=re.S)
    lines = content.splitlines()
    in_dialogue = False
    out: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("#"):
            title = _strip_md_heading(stripped)
            if _is_dialogue_section(title):
                in_dialogue = True
                continue
            if in_dialogue:
                # 下一节标题结束对话；勿对正文做「脚注/摘要」子串截断
                break
            continue
        if not in_dialogue:
            continue
        if stripped.startswith("|") or stripped.startswith("---"):
            # 表格通常属「待确认/参考」；无 # 标题时也结束对话区
            if out:
                break
            continue
        if _is_stop_section(stripped):
            break
        out.append(raw)
    if out:
        return "\n".join(out)

    # Fallback: scan for speaker lines, stop at real section titles / tables
    in_dialogue = False
    out = []
    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("#"):
            title = _strip_md_heading(stripped)
            if _is_stop_section(title):
                if in_dialogue:
                    break
                continue
            if in_dialogue and not _is_dialogue_section(title):
                break
            continue
        if stripped.startswith("|") or stripped.startswith("---"):
            if in_dialogue and out:
                break
            continue
        if in_dialogue and _is_stop_section(stripped):
            break
        m = _SPEAKER_LINE.match(stripped)
        if m and _normalize_speaker(m.group(1)):
            in_dialogue = True
        if in_dialogue:
            out.append(raw)
    return "\n".join(out)


def _normalize_speaker(name: str) -> str | None:
    name = name.strip()
    if name in _ALLOWED_SPEAKERS:
        return name
    if name.startswith("主持人"):
        return "主持人"
    if name.startswith("嘉宾"):
        return "嘉宾"
    return None


def _is_dialogue_continuation(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if s.startswith("|") or s.startswith("---"):
        return False
    if s.startswith("#"):
        return False
    if _SPEAKER_LINE.match(s):
        return False
    if _is_stop_section(s):
        return False
    return True


def parse_podcast_script(content: str) -> list[tuple[str, str]]:
    dialogue = extract_podcast_dialogue_text(content)
    lines: list[tuple[str, str]] = []
    for raw in dialogue.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("<!--"):
            continue
        if line.startswith("|") or line.startswith("---"):
            continue
        m = _SPEAKER_LINE.match(line)
        if m:
            speaker = _normalize_speaker(m.group(1))
            if not speaker:
                continue
            text = m.group(2).strip()
            if text:
                lines.append((speaker, text))
            continue
        if lines and _is_dialogue_continuation(line):
            prev_sp, prev_txt = lines[-1]
            lines[-1] = (prev_sp, prev_txt + " " + line)
    return [(s, t) for s, t in lines if t.strip()]


def synthesize_podcast(content: str, *, title: str = "播客") -> dict[str, Any]:
    script_lines = parse_podcast_script(content)
    if len(script_lines) < 2:
        raise ValueError(
            "播客稿「对话脚本」中需至少 2 行 **主持人** / **嘉宾** 对话；"
            "参考依据、待人工确认等章节不会被朗读。"
        )
    segments = synthesize_segments(script_lines)
    out_dir = output_dir() / "podcasts"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", title).strip("-")[:40] or "podcast"
    bundle_dir = out_dir / safe
    bundle_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    base_out = output_dir()
    for i, seg in enumerate(segments):
        ext = seg.get("format") or "mp3"
        fname = f"{i+1:03d}-{seg.get('speaker','')}.{ext}".replace("/", "-")
        path = bundle_dir / fname
        path.write_bytes(base64.b64decode(seg["base64"]))
        manifest.append(
            {
                "file": path.relative_to(base_out).as_posix(),
                "absolute": str(path),
                "speaker": seg.get("speaker"),
                "text": seg.get("text"),
                "format": ext,
            }
        )
    playlist_path = bundle_dir / "playlist.json"
    playlist_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    merged_file = ""
    merged_format = ""
    merged_error = ""
    segment_paths = [Path(m["absolute"]) for m in manifest]
    exts = {(m.get("format") or Path(m["absolute"]).suffix.lstrip(".")).lower() for m in manifest}
    # 与分段同容器合并：全 wav 出 full.wav（不强制转 mp3，避免 libmp3lame 失败导致无完整文件）
    prefer_mp3 = exts == {"mp3"} or (ffmpeg_available() and "mp3" in exts and "wav" not in exts)
    merged_path = bundle_dir / ("full.mp3" if prefer_mp3 else "full.wav")
    try:
        out = merge_audio_segments(
            segment_paths,
            merged_path,
            gap_ms=450,
            prefer_mp3=prefer_mp3,
        )
        merged_file = out.relative_to(base_out).as_posix()
        merged_format = out.suffix.lstrip(".")
    except Exception as exc:
        merged_error = str(exc)
        # 最后兜底：全 wav 再试一次纯拼接
        if all(p.suffix.lower() == ".wav" for p in segment_paths):
            try:
                wav_out = bundle_dir / "full.wav"
                out = merge_audio_segments(
                    segment_paths, wav_out, gap_ms=450, prefer_mp3=False
                )
                merged_file = out.relative_to(base_out).as_posix()
                merged_format = "wav"
                merged_error = ""
            except Exception as exc2:
                merged_error = f"{exc}; 回退 WAV 亦失败: {exc2}"


    return {
        "ok": True,
        "title": title,
        "lines": len(script_lines),
        "segments": len(segments),
        "directory": str(bundle_dir),
        "playlist": str(playlist_path),
        "manifest": manifest,
        "merged_file": merged_file,
        "merged_format": merged_format,
        "merged_error": merged_error or None,
        "tts": tts_status(),
    }
