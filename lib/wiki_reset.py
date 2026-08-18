"""Wipe user knowledge data under wiki root (settings / 初始化).

Never deletes files under linked external directories — only removes link records.
Preserves .env (API keys, license) and application install tree.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from .config import CONTENT_DIRS, ROOT, env_file_path, wiki_root

CONFIRM_PHRASE = "确认清空知识库"

# Top-level dirs under wiki that hold user content (recreated empty after wipe).
_WIPE_DIRS = CONTENT_DIRS + (
    "inbox",
    "assets",
    "output",
    "skills",  # wiki-local skills only; package skills stay in install tree
)

# Files at wiki root that are user-authored.
_WIPE_ROOT_FILES = ("purpose.md",)

# Config filenames under wiki/.config (and mirrored under install ROOT/.config when present).
_WIPE_CONFIG_FILES = (
    "folders.json",
    "custom-workflows.json",
    "persona.json",
    "linked-dirs.json",
    "owner.json",
    "service-loop.json",
)


def _safe_rmtree(path: Path) -> None:
    if not path.exists():
        return
    if path.is_file() or path.is_symlink():
        path.unlink(missing_ok=True)
        return
    shutil.rmtree(path, ignore_errors=True)


def _list_linked_paths_for_report(root: Path) -> list[str]:
    paths: list[str] = []
    for cfg in (
        root / ".config" / "linked-dirs.json",
        ROOT / ".config" / "linked-dirs.json",
    ):
        if not cfg.is_file():
            continue
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            for d in data.get("dirs") or []:
                p = str(d.get("path") or "").strip()
                if p and p not in paths:
                    paths.append(p)
        except (OSError, json.JSONDecodeError):
            continue
    env_raw = (os.environ.get("MYKNOWLEDGE_EXTRA_DIRS") or "").strip()
    if env_raw:
        paths.append("（环境变量 MYKNOWLEDGE_EXTRA_DIRS 将清空，不删磁盘目录）")
    return paths


def preview_wiki_reset(root: Path | None = None) -> dict[str, Any]:
    """Describe what will be cleared (for UI disclaimer)."""
    root = root or wiki_root()
    existing_dirs = [name for name in _WIPE_DIRS if (root / name).exists()]
    existing_files = [name for name in _WIPE_ROOT_FILES if (root / name).is_file()]
    rag = root / ".rag"
    mem = root / ".memory"
    cfg = root / ".config"
    return {
        "wiki_root": str(root),
        "confirm_phrase": CONFIRM_PHRASE,
        "will_delete_dirs": existing_dirs
        + ([".rag"] if rag.exists() else [])
        + ([".memory"] if mem.exists() else []),
        "will_reset_config": [f for f in _WIPE_CONFIG_FILES if (cfg / f).is_file()]
        + (
            ["linked-dirs.json（应用配置）"]
            if (ROOT / ".config" / "linked-dirs.json").is_file()
            else []
        ),
        "will_delete_files": existing_files,
        "linked_external_paths_untouched": _list_linked_paths_for_report(root),
        "preserved": [
            "设置中的大模型 / TTS / 授权等 .env 项（API Key 保留）",
            "外联目录在磁盘上的真实文件夹与文件（仅解除易知内的外联登记）",
            "易知安装目录内的程序与内置 skills/prompts",
        ],
        "disclaimer": (
            "此操作不可撤销。将永久删除本机知识库内由您产生的笔记、导入资料、"
            "检索索引、对话记忆、资料夹配置、外联登记与自定义工作流等。"
            "外联指向的外部目录与文件不会被删除。"
            "操作后果由您自行承担；建议事先备份知识库文件夹。"
        ),
    }


def _wipe_linked_dirs_config(root: Path | None = None) -> list[str]:
    """Remove link registrations only; never touch external paths on disk."""
    root = root or wiki_root()
    removed: list[str] = []
    seen: set[Path] = set()
    for cfg_path in (
        root / ".config" / "linked-dirs.json",
        ROOT / ".config" / "linked-dirs.json",
    ):
        try:
            key = cfg_path.resolve()
        except OSError:
            key = cfg_path
        if key in seen:
            continue
        seen.add(key)
        n = 0
        data: dict[str, Any] = {}
        if cfg_path.is_file():
            try:
                raw = json.loads(cfg_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    data = raw
            except (OSError, json.JSONDecodeError):
                data = {}
            dirs = data.get("dirs")
            n = len(dirs) if isinstance(dirs, list) else 0
        elif cfg_path != (root / ".config" / "linked-dirs.json"):
            # Don't create a new linked-dirs.json under install ROOT unless it existed.
            continue
        empty = {
            "version": 1,
            "auto_index": bool(data.get("auto_index", True)) if data else True,
            "poll_seconds": int(data.get("poll_seconds") or 60) if data else 60,
            "dirs": [],
        }
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(
            json.dumps(empty, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        removed.append(f"{cfg_path}（已清空 {n} 条外联登记）")
    return removed


def _clear_extra_dirs_env() -> bool:
    """Strip MYKNOWLEDGE_EXTRA_DIRS from user .env; keep other keys."""
    path = env_file_path()
    if not path.is_file():
        os.environ.pop("MYKNOWLEDGE_EXTRA_DIRS", None)
        return False
    try:
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError:
        return False
    out: list[str] = []
    changed = False
    for line in lines:
        if line.lstrip().startswith("MYKNOWLEDGE_EXTRA_DIRS="):
            changed = True
            continue
        out.append(line)
    if changed:
        path.write_text("".join(out), encoding="utf-8")
    os.environ.pop("MYKNOWLEDGE_EXTRA_DIRS", None)
    return changed


def _recreate_skeleton(root: Path) -> None:
    for name in _WIPE_DIRS:
        (root / name).mkdir(parents=True, exist_ok=True)
    (root / ".config").mkdir(parents=True, exist_ok=True)
    (root / ".rag").mkdir(parents=True, exist_ok=True)
    (root / ".memory").mkdir(parents=True, exist_ok=True)
    try:
        from .distill import ensure_distill_skeleton

        ensure_distill_skeleton(root)
    except Exception:
        pass
    try:
        from .folders import ensure_default_folders

        ensure_default_folders(root)
    except Exception:
        pass


def reset_wiki_knowledge(
    *,
    confirm: str,
    root: Path | None = None,
) -> dict[str, Any]:
    """Destructive wipe of user knowledge data. Requires exact confirm phrase."""
    phrase = (confirm or "").strip()
    if phrase != CONFIRM_PHRASE:
        return {
            "ok": False,
            "error": f"请输入精确确认语：{CONFIRM_PHRASE}",
            "confirm_phrase": CONFIRM_PHRASE,
        }

    root = root or wiki_root()
    if not root.is_dir():
        return {"ok": False, "error": f"知识库目录不存在：{root}"}

    deleted: list[str] = []
    errors: list[str] = []

    for name in _WIPE_DIRS:
        p = root / name
        if p.exists():
            try:
                _safe_rmtree(p)
                deleted.append(name + "/")
            except Exception as e:
                errors.append(f"{name}: {e}")

    for name in (".rag", ".memory"):
        p = root / name
        if p.exists():
            try:
                _safe_rmtree(p)
                deleted.append(name + "/")
            except Exception as e:
                errors.append(f"{name}: {e}")

    pkg_rag = ROOT / ".rag"
    if pkg_rag.exists() and pkg_rag.resolve() != (root / ".rag").resolve():
        try:
            _safe_rmtree(pkg_rag)
            deleted.append("安装树/.rag/")
        except Exception as e:
            errors.append(f"ROOT/.rag: {e}")

    for name in _WIPE_ROOT_FILES:
        p = root / name
        if p.is_file():
            try:
                p.unlink()
                deleted.append(name)
            except Exception as e:
                errors.append(f"{name}: {e}")

    cfg_dir = root / ".config"
    if cfg_dir.is_dir():
        for name in _WIPE_CONFIG_FILES:
            if name == "linked-dirs.json":
                # Handled by _wipe_linked_dirs_config (rewrite empty; never touch externals).
                continue
            p = cfg_dir / name
            if p.is_file():
                try:
                    p.unlink()
                    deleted.append(f".config/{name}")
                except Exception as e:
                    errors.append(f".config/{name}: {e}")

    linked_msgs = _wipe_linked_dirs_config(root)
    deleted.extend(linked_msgs)
    if _clear_extra_dirs_env():
        deleted.append(".env 中的 MYKNOWLEDGE_EXTRA_DIRS")

    _recreate_skeleton(root)

    try:
        from .rag import _invalidate_cache

        _invalidate_cache()
    except Exception:
        pass
    try:
        from .memory_db import ensure_db

        ensure_db(root)
    except Exception:
        pass

    ok = not errors
    return {
        "ok": ok,
        "wiki_root": str(root),
        "deleted": deleted,
        "errors": errors,
        "recreated": list(_WIPE_DIRS)
        + [".rag", ".memory", ".config", "distill 骨架", "默认资料夹"],
        "message": (
            "知识库已清空并重建空目录。外联外部磁盘文件未删除。"
            if ok
            else "部分项目清理失败，请查看 errors；外联外部文件仍未删除。"
        ),
    }
