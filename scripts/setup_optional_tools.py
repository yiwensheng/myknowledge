#!/usr/bin/env python3
"""Install bundled optional tools: ffmpeg, bun, yt-dlp; link baoyu-fetch if present.

优先：本机已有工具复制进 third_party（可随安装包带走）。
ffmpeg / bun：正式安装包硬依赖；默认允许从官方源拉取（MYKNOWLEDGE_BUNDLE_FFMPEG=0 / MYKNOWLEDGE_BUNDLE_BUN=0 可关）。
也可设 MYKNOWLEDGE_ALLOW_GITHUB_TOOLS=1、MYKNOWLEDGE_FFMPEG_PATH / MYKNOWLEDGE_BUN_PATH / MYKNOWLEDGE_YTDLP_PATH。
yt-dlp 为 B 站字幕入库所需，正式安装包须含 third_party/yt-dlp/yt-dlp.exe。
"""

from __future__ import annotations

import os
import shutil
import sys
import zipfile
from pathlib import Path

if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
THIRD = ROOT / "third_party"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
FFMPEG_EXE = THIRD / "ffmpeg" / "bin" / "ffmpeg.exe"
BUN_EXE = THIRD / "bun" / "bun.exe"
YTDLP_EXE = THIRD / "yt-dlp" / "yt-dlp.exe"
BAOYU_LINK = THIRD / "baoyu-url-to-markdown"

FFMPEG_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
BUN_URL = "https://github.com/oven-sh/bun/releases/latest/download/bun-windows-x64.zip"
YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"


def _allow_github() -> bool:
    return os.environ.get("MYKNOWLEDGE_ALLOW_GITHUB_TOOLS", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _under_third(path: Path) -> bool:
    try:
        path.resolve().relative_to(THIRD.resolve())
        return True
    except ValueError:
        return False


def _download(url: str, dest: Path) -> None:
    import urllib.request

    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  下载 {url}")
    urllib.request.urlretrieve(url, dest)  # noqa: S310


def _extract_member(zf: zipfile.ZipFile, suffix: str, dest: Path) -> bool:
    for name in zf.namelist():
        if not name.endswith(suffix):
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(name) as src, open(dest, "wb") as out:
            shutil.copyfileobj(src, out)
        return True
    return False


def _vendor_copy(src: Path, dest: Path, sibling_names: tuple[str, ...] = ()) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    for name in sibling_names:
        sibling = src.parent / name
        if sibling.is_file():
            shutil.copy2(sibling, dest.parent / name)


def _vendor_ffmpeg_tree(src_exe: Path) -> None:
    """拷贝 Windows ffmpeg 整目录（须含 avcodec 等 DLL，只拷 exe 会闪退）。"""
    dest_dir = FFMPEG_EXE.parent
    dest_dir.mkdir(parents=True, exist_ok=True)
    src_dir = src_exe.parent
    if sys.platform == "win32" and src_dir.is_dir():
        for item in src_dir.iterdir():
            if not item.is_file():
                continue
            # bin 内常用：ffmpeg/ffprobe/ffplay + av*.dll / sw*.dll / postproc*.dll
            name = item.name.lower()
            if name.endswith((".exe", ".dll")) or name.endswith(".pdb"):
                if name.endswith(".pdb"):
                    continue
                shutil.copy2(item, dest_dir / item.name)
    else:
        _vendor_copy(src_exe, FFMPEG_EXE, ("ffprobe.exe", "ffprobe", "ffplay.exe", "ffplay"))
    if not FFMPEG_EXE.is_file():
        raise OSError(f"拷贝后缺少 {FFMPEG_EXE}")


def _ffmpeg_runs(exe: Path) -> bool:
    if not exe.is_file():
        return False
    try:
        import subprocess

        kwargs: dict = {
            "capture_output": True,
            "text": True,
            "timeout": 15,
            "check": False,
            "cwd": str(exe.parent),
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        r = subprocess.run([str(exe), "-hide_banner", "-version"], **kwargs)
        return r.returncode == 0 and "ffmpeg" in ((r.stdout or "") + (r.stderr or "")).lower()
    except OSError:
        return False
    except Exception:
        return False


def _extract_ffmpeg_bin_from_zip(zf: zipfile.ZipFile, dest_dir: Path) -> bool:
    """从 BtbN 等发行包中解压 **/bin/* 到 dest_dir。"""
    dest_dir.mkdir(parents=True, exist_ok=True)
    wrote = 0
    for name in zf.namelist():
        norm = name.replace("\\", "/")
        if "/bin/" not in norm and not norm.startswith("bin/"):
            continue
        leaf = Path(norm).name
        if not leaf or leaf.endswith("/"):
            continue
        low = leaf.lower()
        if not (low.endswith(".exe") or low.endswith(".dll")):
            continue
        with zf.open(name) as src, open(dest_dir / leaf, "wb") as out:
            shutil.copyfileobj(src, out)
        wrote += 1
    return wrote > 0 and (dest_dir / "ffmpeg.exe").is_file()


def install_ffmpeg() -> bool:
    from lib.runtime_tools import find_ffmpeg as _find

    if _ffmpeg_runs(FFMPEG_EXE):
        print(f"[ffmpeg] 已就绪: {FFMPEG_EXE}")
        return True
    if FFMPEG_EXE.is_file():
        print(f"[ffmpeg] 已有 {FFMPEG_EXE} 但无法运行（多半缺 DLL），尝试从本机重新拷贝…")

    found = _find()
    if found:
        src = Path(found)
        if _under_third(src) and _ffmpeg_runs(src):
            print(f"[ffmpeg] 已就绪: {src}")
            return True
        if not _under_third(src):
            try:
                _vendor_ffmpeg_tree(src)
                if _ffmpeg_runs(FFMPEG_EXE):
                    print(f"[ffmpeg] 已从本机复制（含 DLL）: {src} -> {FFMPEG_EXE}")
                    return True
                print("[ffmpeg] 拷贝完成但仍无法运行 ffmpeg -version")
            except OSError as exc:
                print(f"[ffmpeg] 复制失败: {exc}")

    # 内置 Python 通常已卸 pip，跳过；有 pip 时才试 imageio-ffmpeg
    try:
        import subprocess

        r = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True,
            check=False,
        )
        if r.returncode == 0:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-q", "imageio-ffmpeg"],
                check=False,
            )
            exe = _find()
            if exe:
                src = Path(exe)
                if not _under_third(src):
                    _vendor_ffmpeg_tree(src)
                if _ffmpeg_runs(FFMPEG_EXE) or _ffmpeg_runs(Path(exe)):
                    print(f"[ffmpeg] 已通过 imageio-ffmpeg: {FFMPEG_EXE if FFMPEG_EXE.is_file() else exe}")
                    return True
    except Exception as exc:
        print(f"[ffmpeg] pip/imageio 跳过: {exc}")

    # 与 bun 相同：安装包硬依赖 ffmpeg（exe+DLL），默认尝试官方 zip（MYKNOWLEDGE_BUNDLE_FFMPEG=0 关闭）
    if sys.platform == "win32" and (
        _allow_github() or os.environ.get("MYKNOWLEDGE_BUNDLE_FFMPEG", "1").strip() != "0"
    ):
        zip_path = THIRD / "_cache" / "ffmpeg.zip"
        try:
            _download(FFMPEG_URL, zip_path)
            with zipfile.ZipFile(zip_path) as zf:
                if not _extract_ffmpeg_bin_from_zip(zf, FFMPEG_EXE.parent):
                    print("[ffmpeg] 解压失败：zip 内未找到 bin/ffmpeg.exe(+dll)")
                    return False
            if not _ffmpeg_runs(FFMPEG_EXE):
                print("[ffmpeg] 已解压但 ffmpeg -version 失败")
                return False
            print(f"[ffmpeg] 已从官方包安装: {FFMPEG_EXE}")
            return True
        except OSError as exc:
            print(f"[ffmpeg] 官方包安装失败: {exc}")
            return False

    print(
        "[ffmpeg] 本机未找到可运行的 ffmpeg（需 exe+DLL）。\n"
        "  请任选：1) 安装到 PATH / C:\\ffmpeg\\bin  2) 设 MYKNOWLEDGE_FFMPEG_PATH\n"
        "  3) 将完整 bin（含 *.dll）放到 third_party/ffmpeg/bin/\n"
        "  4) 联网拉取：默认 MYKNOWLEDGE_BUNDLE_FFMPEG=1；或 MYKNOWLEDGE_ALLOW_GITHUB_TOOLS=1"
    )
    return False


def _resolve_bun_exe(path: Path) -> Path | None:
    """bun.cmd / 路径 → 真实 bun.exe。"""
    if path.is_file() and path.suffix.lower() == ".exe":
        return path
    if path.suffix.lower() in (".cmd", ".ps1", ""):
        candidates = [
            path.parent / "node_modules" / "bun" / "bin" / "bun.exe",
            path.parent / "bun.exe",
        ]
        for c in candidates:
            if c.is_file():
                return c
    if path.is_file():
        return path
    return None


def install_bun() -> bool:
    from lib.runtime_tools import find_bun as _find

    if BUN_EXE.is_file():
        print(f"[bun] 已就绪: {BUN_EXE}")
        return True

    found = _find()
    if found:
        resolved = _resolve_bun_exe(Path(found))
        if resolved and resolved.is_file():
            if _under_third(resolved.resolve()):
                print(f"[bun] 已就绪: {resolved}")
                return True
            try:
                _vendor_copy(resolved, BUN_EXE)
                print(f"[bun] 已从本机复制: {resolved} -> {BUN_EXE}")
                return True
            except OSError as exc:
                print(f"[bun] 复制失败: {exc}")

    if sys.platform == "win32":
        try:
            import subprocess

            subprocess.run(["npm", "install", "-g", "bun"], check=False, capture_output=True)
            existing = _find()
            if existing:
                resolved = _resolve_bun_exe(Path(existing))
                if resolved and resolved.is_file():
                    _vendor_copy(resolved, BUN_EXE)
                    print(f"[bun] 已通过 npm 安装并复制: {BUN_EXE}")
                    return True
        except OSError as exc:
            print(f"[bun] npm 安装失败: {exc}")

    # 与 yt-dlp 相同：网页/公众号抓取硬依赖 bun，默认尝试拉取官方 zip（可用 MYKNOWLEDGE_BUNDLE_BUN=0 关闭）
    if sys.platform == "win32" and (
        _allow_github() or os.environ.get("MYKNOWLEDGE_BUNDLE_BUN", "1").strip() != "0"
    ):
        zip_path = THIRD / "_cache" / "bun.zip"
        try:
            _download(BUN_URL, zip_path)
            with zipfile.ZipFile(zip_path) as zf:
                if not _extract_member(zf, "bun.exe", BUN_EXE):
                    found_zip = False
                    for name in zf.namelist():
                        if name.endswith("/bun.exe") or name.endswith("\\bun.exe"):
                            BUN_EXE.parent.mkdir(parents=True, exist_ok=True)
                            with zf.open(name) as src, open(BUN_EXE, "wb") as out:
                                shutil.copyfileobj(src, out)
                            found_zip = True
                            break
                    if not found_zip:
                        print("[bun] 解压失败：zip 内未找到 bun.exe")
                        return False
            if BUN_EXE.is_file() and BUN_EXE.stat().st_size > 1_000_000:
                print(f"[bun] 已从 GitHub 安装: {BUN_EXE}")
                return True
            if BUN_EXE.is_file():
                BUN_EXE.unlink(missing_ok=True)
            print("[bun] 下载文件异常（过小），已删除")
        except OSError as exc:
            print(f"[bun] GitHub 安装失败: {exc}")

    print(
        "[bun] 未就绪。请 npm i -g bun，或设 MYKNOWLEDGE_BUN_PATH，"
        "或 MYKNOWLEDGE_ALLOW_GITHUB_TOOLS=1 后重试"
    )
    return False


def install_ytdlp() -> bool:
    """Ensure third_party/yt-dlp/yt-dlp.exe (bundled for installer)."""
    from lib.runtime_tools import find_ytdlp as _find

    if YTDLP_EXE.is_file():
        print(f"[yt-dlp] 已就绪: {YTDLP_EXE}")
        return True

    env = os.environ.get("MYKNOWLEDGE_YTDLP_PATH", "").strip()
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env))
    found = _find()
    if found:
        candidates.append(Path(found))

    for src in candidates:
        if not src.is_file():
            continue
        if _under_third(src.resolve()):
            print(f"[yt-dlp] 已就绪: {src}")
            return True
        try:
            _vendor_copy(src, YTDLP_EXE)
            print(f"[yt-dlp] 已从本机复制: {src} -> {YTDLP_EXE}")
            return True
        except OSError as exc:
            print(f"[yt-dlp] 复制失败 ({src}): {exc}")

    # yt-dlp 为安装包硬依赖：缺省时尽量拉取官方 exe（单文件）；也可用 ALLOW_GITHUB
    if sys.platform == "win32" and (_allow_github() or os.environ.get("MYKNOWLEDGE_BUNDLE_YTDLP", "1").strip() != "0"):
        try:
            _download(YTDLP_URL, YTDLP_EXE)
            if YTDLP_EXE.is_file() and YTDLP_EXE.stat().st_size > 1_000_000:
                print(f"[yt-dlp] 已从 GitHub 安装: {YTDLP_EXE}")
                return True
            if YTDLP_EXE.is_file():
                YTDLP_EXE.unlink(missing_ok=True)
            print("[yt-dlp] 下载文件异常（过小），已删除")
        except OSError as exc:
            print(f"[yt-dlp] GitHub 安装失败: {exc}")

    print(
        "[yt-dlp] 未就绪。请设 MYKNOWLEDGE_YTDLP_PATH，或安装 yt-dlp 到 PATH，"
        "或 MYKNOWLEDGE_ALLOW_GITHUB_TOOLS=1 后重试"
    )
    return False


def link_baoyu_fetch() -> bool:
    skill_scripts = Path.home() / ".agents" / "skills" / "baoyu-url-to-markdown"
    fetch = skill_scripts / "scripts" / "baoyu-fetch"
    if fetch.is_file():
        if BAOYU_LINK.is_dir():
            print(f"[baoyu-fetch] 已链接: {BAOYU_LINK}")
            return True
        try:
            if sys.platform == "win32":
                import subprocess

                subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(BAOYU_LINK), str(skill_scripts)],
                    check=True,
                    capture_output=True,
                )
            else:
                BAOYU_LINK.symlink_to(skill_scripts, target_is_directory=True)
            print(f"[baoyu-fetch] 已链接到 {skill_scripts}")
            return True
        except OSError:
            try:
                shutil.copytree(skill_scripts, BAOYU_LINK, dirs_exist_ok=True)
                print(f"[baoyu-fetch] 已复制到 {BAOYU_LINK}")
                return True
            except OSError as exc:
                print(f"[baoyu-fetch] 链接/复制失败: {exc}")
                return False
    bundled = ROOT / "third_party" / "baoyu-url-to-markdown" / "scripts" / "baoyu-fetch"
    if bundled.is_file():
        print(f"[baoyu-fetch] 已就绪: {bundled}")
        return True
    print("[baoyu-fetch] 未找到 baoyu-url-to-markdown skill，可安装 baoyu-url-to-markdown 技能后重试")
    return False


def patch_env_rerank() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    text = env_path.read_text(encoding="utf-8")
    lines = []
    seen = set()
    for line in text.splitlines():
        key = line.split("=", 1)[0].strip() if "=" in line and not line.strip().startswith("#") else ""
        if key in ("MYKNOWLEDGE_RERANK", "MYKNOWLEDGE_RERANK_MODEL"):
            seen.add(key)
        lines.append(line)
    additions = []
    if "MYKNOWLEDGE_RERANK" not in seen:
        additions.append("MYKNOWLEDGE_RERANK=1")
    if "MYKNOWLEDGE_RERANK_MODEL" not in seen:
        additions.append("MYKNOWLEDGE_RERANK_MODEL=bge-reranker-v2-m3")
    if additions:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("# Rerank（URL 默认同 Embedding API base）")
        lines.extend(additions)
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("[rerank] 已在 .env 启用 MYKNOWLEDGE_RERANK=1")


def main() -> int:
    print("=== 易知可选工具安装 ===")
    print(
        "策略: 优先复制本机工具；ffmpeg/bun 默认可拉取官方包"
        "（MYKNOWLEDGE_BUNDLE_FFMPEG / MYKNOWLEDGE_BUNDLE_BUN；ALLOW_GITHUB_TOOLS=1 亦可）"
    )
    ok_ff = install_ffmpeg()
    ok_bun = install_bun()
    ok_ytdlp = install_ytdlp()
    ok_baoyu = link_baoyu_fetch()
    patch_env_rerank()
    print("")
    print("结果:")
    print(f"  ffmpeg: {'OK' if ok_ff else 'FAIL'}")
    print(f"  bun: {'OK' if ok_bun else 'FAIL'}")
    print(f"  yt-dlp: {'OK' if ok_ytdlp else 'FAIL'}")
    print(f"  baoyu-fetch: {'OK' if ok_baoyu else 'SKIP'}")
    if ok_bun and ok_baoyu:
        scripts_dir = _find_baoyu_scripts_dir()
        if scripts_dir and not (scripts_dir / "node_modules").is_dir():
            print("[baoyu-fetch] 正在 bun install …")
            import subprocess

            bun = str(BUN_EXE if BUN_EXE.is_file() else "bun")
            subprocess.run([bun, "install"], cwd=str(scripts_dir), check=False)
    # yt-dlp 失败不阻断开发机 ffmpeg/bun；打包脚本另行 assert
    return 0 if ok_ff and ok_bun else 1


def _find_baoyu_scripts_dir() -> Path | None:
    for base in (BAOYU_LINK, Path.home() / ".agents" / "skills" / "baoyu-url-to-markdown"):
        scripts = base / "scripts"
        if (scripts / "baoyu-fetch").is_file():
            return scripts
    return None


if __name__ == "__main__":
    raise SystemExit(main())
