"""Single-voice spoken narration from YiZhi promo copy → merged MP3."""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

from .config import output_dir
from .podcast_merge import ffmpeg_available, merge_audio_segments
from .tts import split_long_text, synthesize_segments, tts_status
from .yizhi_product import find_promo_docx, load_yizhi_product

_NARRATION_SYSTEM = """你是中文口播撰稿人，写给 TTS 单人朗读的稿子。
要求：
1. 要有亮点与金句（可沿用原文金句，如「没有出处的聪明，不过是幻觉；有出处的沉默，方才是诚实」）。
2. 严禁播客/节目形态：不准出现主持人、嘉宾、听众朋友、欢迎收听、本期节目、开场白套路、双人对话。
3. 语气亲切、过渡自然，像朋友当面讲清楚一件事，绝不是照着章节标题念稿。
4. 只输出可直接朗读的纯正文（自然段落），不要 Markdown 标题、表格、列表符号、章节编号。
5. 只依据用户给出的宣传文案，不编造文案内没有的功能或数据。
6. 篇幅约 1800～2800 字，够一段较长独白；可压缩重复，保留推演、自我进化、本地有据等亮点。"""


def promo_source_text() -> str:
    """Raw promo body used for narration (prefer extracted product load)."""
    body = load_yizhi_product(force=False)
    if not body:
        raise FileNotFoundError(
            "未找到宣传文案。请将「易知-自我进化个人知识库-宣传文案.docx」"
            "放到 docs/ 或 docs/product/，并确保 prompts/yizhi-product.md 已生成。"
        )
    # Drop the short "规则" preface if present; keep main copy after ---
    if "\n---\n" in body:
        body = body.split("\n---\n", 1)[-1].strip()
    return body


def rewrite_spoken_narration(source: str) -> str:
    from .llm import _chat

    user = (
        "请把下面「易知宣传文案」改写成单人口播长稿。\n\n"
        f"【宣传文案】\n{source}\n"
    )
    raw = _chat(_NARRATION_SYSTEM, user, kind="produce")
    text = (raw or "").strip()
    text = re.sub(r"^#+\s*.+$", "", text, flags=re.M)
    text = re.sub(r"[|｜].*[|｜]", "", text)  # drop table-ish lines
    text = re.sub(r"^\s*[-*•]\s+", "", text, flags=re.M)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    # Strip accidental dialogue labels
    text = re.sub(r"^\s*(主持人|嘉宾|旁白)\s*[：:]\s*", "", text, flags=re.M)
    banned = ("欢迎收听", "本期节目", "听众朋友", "主持人：", "嘉宾：")
    for b in banned:
        text = text.replace(b, "")
    if len(text) < 200:
        raise RuntimeError("口播稿生成过短，请检查大模型配置后重试")
    return text


def _chunk_for_tts(script: str) -> list[tuple[str, str]]:
    """One speaker; split by paragraph then TTS length limits."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", script) if p.strip()]
    if not paras:
        paras = [script]
    lines: list[tuple[str, str]] = []
    for p in paras:
        for piece in split_long_text(p, 480):
            if piece.strip():
                lines.append(("旁白", piece.strip()))
    return lines


def synthesize_yizhi_promo_audio(*, rewrite: bool = True, title: str = "易知宣传") -> dict[str, Any]:
    """Build spoken script from promo copy and synthesize a merged MP3/WAV."""
    source = promo_source_text()
    out_dir = output_dir() / "podcasts"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", title).strip("-")[:40] or "yizhi-promo"
    bundle_dir = out_dir / safe
    bundle_dir.mkdir(parents=True, exist_ok=True)
    status_path = bundle_dir / "status.json"
    status_path.write_text(
        json.dumps(
            {"phase": "rewrite" if rewrite else "tts", "title": title},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    script = rewrite_spoken_narration(source) if rewrite else source
    # Even without rewrite, strip heading junk for TTS
    if not rewrite:
        script = re.sub(r"^#+\s*.+$", "", script, flags=re.M)
        script = re.sub(r"————\s*✦\s*————", "。", script)
        script = re.sub(r"\n{3,}", "\n\n", script).strip()

    script_lines = _chunk_for_tts(script)
    if not script_lines:
        raise ValueError("口播文本为空")

    status_path.write_text(
        json.dumps({"phase": "tts", "chunks": len(script_lines)}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    segments = synthesize_segments(script_lines)

    manifest: list[dict] = []
    base_out = output_dir()
    for i, seg in enumerate(segments):
        ext = seg.get("format") or "mp3"
        fname = f"{i+1:03d}-narration.{ext}"
        path = bundle_dir / fname
        path.write_bytes(base64.b64decode(seg["base64"]))
        manifest.append(
            {
                "file": path.relative_to(base_out).as_posix(),
                "absolute": str(path),
                "speaker": "旁白",
                "text": seg.get("text"),
                "format": ext,
            }
        )

    script_path = bundle_dir / "narration.txt"
    script_path.write_text(script + "\n", encoding="utf-8")
    playlist_path = bundle_dir / "playlist.json"
    playlist_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    first_ext = (manifest[0].get("format") or "mp3").lower()
    prefer_mp3 = ffmpeg_available() or first_ext == "mp3"
    merged_path = bundle_dir / ("full.mp3" if prefer_mp3 else "full.wav")
    merged_file = ""
    merged_format = ""
    merged_error = ""
    try:
        out = merge_audio_segments(
            [Path(m["absolute"]) for m in manifest],
            merged_path,
            gap_ms=280,
            prefer_mp3=prefer_mp3,
        )
        merged_file = out.relative_to(base_out).as_posix()
        merged_format = out.suffix.lstrip(".")
    except Exception as exc:
        merged_error = str(exc)

    docx = find_promo_docx()
    merged_abs = str((base_out / merged_file).resolve()) if merged_file else ""
    status_path.write_text(
        json.dumps(
            {
                "phase": "done" if merged_file else "merge_failed",
                "merged_file": merged_file,
                "merged_error": merged_error or None,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "ok": True,
        "title": title,
        "kind": "yizhi_promo_narration",
        "source_docx": str(docx) if docx else None,
        "script_chars": len(script),
        "segments": len(segments),
        "directory": str(bundle_dir.resolve()),
        "output_root": str(base_out.resolve()),
        "script_file": script_path.relative_to(base_out).as_posix(),
        "playlist": str(playlist_path),
        "manifest": manifest,
        "merged_file": merged_file,
        "merged_absolute": merged_abs,
        "merged_format": merged_format,
        "merged_error": merged_error or None,
        "tts": tts_status(),
    }
