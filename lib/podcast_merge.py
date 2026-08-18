"""Merge podcast segment audio into one file (ffmpeg or WAV concat)."""

from __future__ import annotations

import shutil
import tempfile
import wave
from pathlib import Path

from .runtime_tools import find_ffmpeg, subprocess_run_hidden


def _find_ffmpeg() -> str | None:
    return find_ffmpeg()


def _merge_wav_files(paths: list[Path], out_path: Path, *, gap_ms: int = 0) -> None:
    if not paths:
        raise ValueError("no wav files")
    with wave.open(str(paths[0]), "rb") as w0:
        nch, sampwidth, framerate, _, _ = w0.getparams()[:5]
        chunks = [w0.readframes(w0.getnframes())]
    silence = b""
    if gap_ms > 0 and framerate > 0:
        nframes = int(framerate * gap_ms / 1000)
        silence = b"\x00" * nframes * nch * sampwidth
    for p in paths[1:]:
        if silence:
            chunks.append(silence)
        with wave.open(str(p), "rb") as w:
            if (w.getnchannels(), w.getsampwidth(), w.getframerate()) != (nch, sampwidth, framerate):
                raise RuntimeError(f"WAV 参数不一致: {p.name}")
            chunks.append(w.readframes(w.getnframes()))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as out:
        out.setnchannels(nch)
        out.setsampwidth(sampwidth)
        out.setframerate(framerate)
        for chunk in chunks:
            out.writeframes(chunk)


def _merge_with_ffmpeg(ffmpeg: str, paths: list[Path], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_ext = out_path.suffix.lower()
    # concat 列表：单引号路径；Windows 用正斜杠更稳
    list_lines = []
    for p in paths:
        pos = p.resolve().as_posix().replace("'", r"'\''")
        list_lines.append(f"file '{pos}'")
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tf:
        tf.write("\n".join(list_lines))
        list_path = tf.name
    try:
        base = [
            ffmpeg,
            "-hide_banner",
            "-nostdin",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            list_path,
        ]
        # 同格式优先 stream copy，避免依赖 libmp3lame
        attempts: list[list[str]] = []
        if out_ext == ".mp3" and all(p.suffix.lower() == ".mp3" for p in paths):
            attempts.append(base + ["-c", "copy", str(out_path)])
        if out_ext == ".mp3":
            attempts.append(base + ["-c:a", "libmp3lame", "-q:a", "2", str(out_path)])
        elif out_ext == ".wav":
            attempts.append(base + ["-c:a", "pcm_s16le", str(out_path)])
        else:
            attempts.append(base + ["-c:a", "aac", "-b:a", "192k", str(out_path)])

        last_err = "ffmpeg failed"
        # cwd=bin：保证同目录 DLL 可加载；CREATE_NO_WINDOW：避免安装版黑窗一闪
        ff_cwd = str(Path(ffmpeg).resolve().parent)
        for cmd in attempts:
            try:
                proc = subprocess_run_hidden(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=600,
                    cwd=ff_cwd,
                )
            except FileNotFoundError as exc:
                raise RuntimeError(
                    "找不到 ffmpeg（请确认 third_party/ffmpeg/bin 含 ffmpeg.exe 与 *.dll）"
                ) from exc
            except OSError as exc:
                raise RuntimeError(
                    f"无法启动 ffmpeg（常为缺少 avcodec 等 DLL）：{exc}"
                ) from exc
            if proc.returncode == 0 and out_path.is_file():
                return
            last_err = (proc.stderr or proc.stdout or "ffmpeg failed").strip()[:500] or last_err
        raise RuntimeError(last_err)

    finally:
        Path(list_path).unlink(missing_ok=True)


def ffmpeg_available() -> bool:
    return _find_ffmpeg() is not None


def merge_audio_segments(
    paths: list[Path],
    out_path: Path,
    *,
    gap_ms: int = 450,
    prefer_mp3: bool = True,
) -> Path:
    """Merge segment files in order; returns output path."""
    files = [p.resolve() for p in paths if p.is_file()]
    if not files:
        raise ValueError("没有可合并的音频片段")
    if len(files) == 1:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(files[0], out_path)
        return out_path

    all_wav = all(p.suffix.lower() == ".wav" for p in files)
    all_mp3 = all(p.suffix.lower() == ".mp3" for p in files)

    # WAV：纯 Python 拼接，不依赖 ffmpeg/libmp3lame（智谱/通义等默认 wav）
    if all_wav and not prefer_mp3:
        target = out_path if out_path.suffix.lower() == ".wav" else out_path.with_suffix(".wav")
        _merge_wav_files(files, target, gap_ms=gap_ms)
        return target

    ffmpeg = _find_ffmpeg()
    if all_wav and prefer_mp3:
        wav_target = out_path.with_suffix(".wav")
        if ffmpeg:
            mp3_target = out_path if out_path.suffix.lower() == ".mp3" else out_path.with_suffix(".mp3")
            try:
                _merge_with_ffmpeg(ffmpeg, files, mp3_target)
                return mp3_target
            except RuntimeError:
                _merge_wav_files(files, wav_target, gap_ms=gap_ms)
                return wav_target
        _merge_wav_files(files, wav_target, gap_ms=gap_ms)
        return wav_target

    if not ffmpeg:
        raise RuntimeError("合并多段 MP3 需要安装 ffmpeg；或改用输出 WAV 的 TTS（如智谱 GLM）")

    if prefer_mp3 or all_mp3:
        target = out_path if out_path.suffix.lower() == ".mp3" else out_path.with_suffix(".mp3")
    else:
        target = out_path
    _merge_with_ffmpeg(ffmpeg, files, target)
    return target
