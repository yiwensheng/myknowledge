"""Linked external document directories — read-only RAG, no file copy."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import ROOT, env_file_path, load_dotenv, wiki_root

BEIJING = timezone(timedelta(hours=8))
log = logging.getLogger("myknowledge.linked_dirs")

# Legacy (pre-3.0.2): install-tree config. Prefer wiki_root/.config for writability.
_LEGACY_CONFIG_FILE = ROOT / ".config" / "linked-dirs.json"


def _now_beijing() -> str:
    return datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M")


def config_file(root: Path | None = None) -> Path:
    """User-writable linked-dirs.json under the wiki data directory."""
    return (root or wiki_root()) / ".config" / "linked-dirs.json"


def _legacy_config_file() -> Path:
    return _LEGACY_CONFIG_FILE


def _parse_env_paths() -> list[str]:
    raw = os.environ.get("MYKNOWLEDGE_EXTRA_DIRS", "").strip()
    if not raw:
        return []
    if ";" in raw or "\n" in raw:
        parts = __import__("re").split(r"[;\n]+", raw)
    else:
        parts = raw.split(os.pathsep)
    out: list[str] = []
    for part in parts:
        part = part.strip().strip('"').strip("'")
        if part:
            out.append(str(Path(part).expanduser().resolve()))
    return out


def _read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("version", 1)
            data.setdefault("auto_index", True)
            data.setdefault("poll_seconds", 60)
            data.setdefault("dirs", [])
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return None


def _empty_config() -> dict[str, Any]:
    return {"version": 1, "auto_index": True, "poll_seconds": 60, "dirs": []}


def _load_raw(root: Path | None = None) -> dict[str, Any]:
    primary = config_file(root)
    data = _read_json_file(primary)
    if data is not None:
        return data
    # Migrate once from install-tree config if present.
    legacy = _read_json_file(_legacy_config_file())
    if legacy is not None:
        try:
            _save_raw(legacy, root)
            log.info("migrated linked-dirs.json to %s", primary)
        except OSError as e:
            log.warning("could not migrate linked-dirs.json to wiki: %s", e)
            return legacy
        return legacy
    return _empty_config()


def _save_raw(data: dict[str, Any], root: Path | None = None) -> None:
    path = config_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Best-effort mirror to legacy path when writable (dev / old tools).
    try:
        legacy = _legacy_config_file()
        if legacy.resolve() != path.resolve():
            legacy.parent.mkdir(parents=True, exist_ok=True)
            legacy.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def _normalize_path(path: str) -> str:
    return str(Path(path).expanduser().resolve())


def _merge_env_into_config(data: dict[str, Any]) -> bool:
    """One-time merge: env-only paths appended to json store."""
    load_dotenv()
    existing = {_normalize_path(d.get("path", "")) for d in data.get("dirs") or [] if d.get("path")}
    changed = False
    for p in _parse_env_paths():
        if p not in existing:
            data.setdefault("dirs", []).append(
                {
                    "path": p,
                    "label": "",
                    "enabled": True,
                    "added_at": _now_beijing(),
                    "source": "env",
                }
            )
            existing.add(p)
            changed = True
    if changed:
        _save_raw(data)
    return changed


def linked_dir_paths(*, enabled_only: bool = True) -> list[Path]:
    load_dotenv()
    data = _load_raw()
    _merge_env_into_config(data)
    out: list[Path] = []
    seen: set[str] = set()
    for item in data.get("dirs") or []:
        if enabled_only and not item.get("enabled", True):
            continue
        raw = str(item.get("path") or "").strip()
        if not raw:
            continue
        p = Path(raw).expanduser()
        try:
            resolved = str(p.resolve())
        except OSError:
            continue
        if resolved in seen:
            continue
        if p.is_dir():
            out.append(p.resolve())
            seen.add(resolved)
    for p in _parse_env_paths():
        if p in seen:
            continue
        if Path(p).is_dir():
            out.append(Path(p))
            seen.add(p)
    return out


def poll_seconds() -> float:
    load_dotenv()
    data = _load_raw()
    env_raw = os.environ.get("MYKNOWLEDGE_LINKED_DIRS_POLL", "").strip()
    if env_raw:
        try:
            sec = float(env_raw)
            return max(15.0, min(sec, 3600.0))
        except ValueError:
            pass
    try:
        sec = float(data.get("poll_seconds") or 60)
    except (TypeError, ValueError):
        sec = 60.0
    return max(15.0, min(sec, 3600.0))


def auto_index_enabled() -> bool:
    load_dotenv()
    env_raw = os.environ.get("MYKNOWLEDGE_LINKED_DIRS_AUTO_INDEX", "").strip().lower()
    if env_raw:
        return env_raw in ("1", "true", "yes", "on")
    data = _load_raw()
    if "auto_index" in data:
        return bool(data.get("auto_index"))
    return True


def dir_stats(path: Path, *, max_scan: int = 80000) -> dict[str, Any]:
    from .media_types import is_supported

    if not path.is_dir():
        return {
            "exists": False,
            "file_count": 0,
            "supported_count": 0,
            "truncated": False,
        }
    total = 0
    supported = 0
    try:
        for p in path.rglob("*"):
            if not p.is_file():
                continue
            total += 1
            if is_supported(p.suffix):
                supported += 1
            if total >= max_scan:
                return {
                    "exists": True,
                    "file_count": total,
                    "supported_count": supported,
                    "truncated": True,
                }
    except OSError:
        return {"exists": False, "file_count": 0, "supported_count": 0, "truncated": False}
    return {
        "exists": True,
        "file_count": total,
        "supported_count": supported,
        "truncated": False,
    }


def list_linked_dirs() -> dict[str, Any]:
    load_dotenv()
    data = _load_raw()
    _merge_env_into_config(data)
    from .linked_dir_jobs import list_active_jobs, path_index_status

    items: list[dict[str, Any]] = []
    for item in data.get("dirs") or []:
        raw = str(item.get("path") or "").strip()
        if not raw:
            continue
        p = Path(raw).expanduser()
        try:
            resolved = _normalize_path(raw)
        except OSError:
            resolved = raw
        stats = dir_stats(p) if p.is_dir() else {"exists": False, "file_count": 0, "supported_count": 0, "truncated": False}
        row = {
            "path": resolved,
            "label": str(item.get("label") or ""),
            "enabled": bool(item.get("enabled", True)),
            "added_at": str(item.get("added_at") or ""),
            "last_indexed_at": str(item.get("last_indexed_at") or ""),
            "source": str(item.get("source") or "ui"),
            "folder_ids": [str(x) for x in (item.get("folder_ids") or []) if str(x).strip()],
            **stats,
        }
        idx = path_index_status(resolved)
        if idx:
            row["index_job"] = idx
        items.append(row)
    return {
        "config_path": str(config_file()),
        "auto_index": auto_index_enabled(),
        "poll_seconds": poll_seconds(),
        "active_count": len(linked_dir_paths()),
        "items": items,
        "index_jobs": list_active_jobs(),
        "note": "文件保留在原目录，仅读取内容写入 RAG；不会复制到易知目录。",
    }


def add_linked_dir(path: str, label: str = "", folder_ids: list[str] | None = None) -> dict[str, Any]:
    path = path.strip()
    if not path:
        raise ValueError("请提供目录路径")
    resolved = _normalize_path(path)
    p = Path(resolved)
    if not p.is_dir():
        raise ValueError(f"目录不存在或不可访问：{resolved}")
    from .folders import normalize_folder_ids

    ids = normalize_folder_ids(folder_ids)
    data = _load_raw()
    dirs = data.setdefault("dirs", [])
    for item in dirs:
        if _normalize_path(str(item.get("path") or "")) == resolved:
            item["enabled"] = True
            if label:
                item["label"] = label.strip()
            if folder_ids is not None:
                item["folder_ids"] = ids
            _save_raw(data)
            _sync_env_from_config(data)
            return list_linked_dirs()
    dirs.append(
        {
            "path": resolved,
            "label": label.strip(),
            "enabled": True,
            "added_at": _now_beijing(),
            "last_indexed_at": "",
            "source": "ui",
            "folder_ids": ids,
        }
    )
    _save_raw(data)
    _sync_env_from_config(data)
    return list_linked_dirs()


def remove_linked_dir(path: str) -> dict[str, Any]:
    resolved = _normalize_path(path.strip())
    data = _load_raw()
    dirs = data.get("dirs") or []
    data["dirs"] = [d for d in dirs if _normalize_path(str(d.get("path") or "")) != resolved]
    _save_raw(data)
    _sync_env_from_config(data)
    return list_linked_dirs()


def set_linked_dir_enabled(path: str, enabled: bool) -> dict[str, Any]:
    resolved = _normalize_path(path.strip())
    data = _load_raw()
    for item in data.get("dirs") or []:
        if _normalize_path(str(item.get("path") or "")) == resolved:
            item["enabled"] = bool(enabled)
            break
    _save_raw(data)
    _sync_env_from_config(data)
    return list_linked_dirs()


def set_linked_dir_folder_ids(path: str, folder_ids: list[str] | None) -> dict[str, Any]:
    from .folders import normalize_folder_ids

    resolved = _normalize_path(path.strip())
    ids = normalize_folder_ids(folder_ids)
    data = _load_raw()
    found = False
    for item in data.get("dirs") or []:
        if _normalize_path(str(item.get("path") or "")) == resolved:
            item["folder_ids"] = ids
            found = True
            break
    if not found:
        raise KeyError(f"外联目录不存在：{resolved}")
    _save_raw(data)
    return list_linked_dirs()


def mark_all_indexed() -> None:
    data = _load_raw()
    now = _now_beijing()
    for item in data.get("dirs") or []:
        if item.get("enabled", True):
            item["last_indexed_at"] = now
    _save_raw(data)


def mark_path_indexed(path: str) -> None:
    resolved = _normalize_path(path.strip())
    data = _load_raw()
    now = _now_beijing()
    for item in data.get("dirs") or []:
        if _normalize_path(str(item.get("path") or "")) == resolved:
            item["last_indexed_at"] = now
            break
    _save_raw(data)


def _sync_env_from_config(data: dict[str, Any]) -> None:
    """Keep MYKNOWLEDGE_EXTRA_DIRS in .env aligned for CLI / docs."""
    paths: list[str] = []
    for item in data.get("dirs") or []:
        if not item.get("enabled", True):
            continue
        raw = str(item.get("path") or "").strip()
        if raw:
            paths.append(raw)
    value = ";".join(paths)
    os.environ["MYKNOWLEDGE_EXTRA_DIRS"] = value
    env_path = env_file_path()
    try:
        lines: list[str] = []
        if env_path.is_file():
            lines = env_path.read_text(encoding="utf-8").splitlines()
        touched = False
        new_lines: list[str] = []
        for line in lines:
            if line.strip().startswith("MYKNOWLEDGE_EXTRA_DIRS="):
                new_lines.append(f"MYKNOWLEDGE_EXTRA_DIRS={value}")
                touched = True
            else:
                new_lines.append(line)
        if not touched:
            if new_lines and new_lines[-1].strip():
                new_lines.append("")
            new_lines.append(f"MYKNOWLEDGE_EXTRA_DIRS={value}")
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")
    except OSError as e:
        log.warning("could not sync MYKNOWLEDGE_EXTRA_DIRS to %s: %s", env_path, e)


def dir_fingerprint(root: Path) -> tuple[int, float]:
    from .media_types import is_supported

    count = 0
    max_mtime = 0.0
    if not root.is_dir():
        return 0, 0.0
    try:
        for path in root.rglob("*"):
            if not path.is_file() or not is_supported(path.suffix):
                continue
            count += 1
            try:
                max_mtime = max(max_mtime, path.stat().st_mtime)
            except OSError:
                continue
    except OSError:
        return 0, 0.0
    return count, max_mtime
