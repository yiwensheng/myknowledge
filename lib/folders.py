"""User-defined knowledge folders（资料夹）— logical multi-tags for wiki/assets/linked dirs."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import wiki_root

BEIJING = timezone(timedelta(hours=8))

DEFAULT_FOLDERS: list[dict[str, Any]] = [
    {"id": "fld-work", "name": "工作", "sort": 0},
    {"id": "fld-study", "name": "学习", "sort": 1},
    {"id": "fld-life", "name": "生活", "sort": 2},
    {"id": "fld-reading", "name": "阅读", "sort": 3},
    {"id": "fld-archive", "name": "归档", "sort": 4},
]


def _now() -> str:
    return datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M")


def _config_path(root: Path | None = None) -> Path:
    return (root or wiki_root()) / ".config" / "folders.json"


def _load(root: Path | None = None) -> dict[str, Any]:
    path = _config_path(root)
    if not path.is_file():
        return {"version": 1, "folders": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("version", 1)
            data.setdefault("folders", [])
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"version": 1, "folders": []}


def _save(data: dict[str, Any], root: Path | None = None) -> None:
    path = _config_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_folder_ids(raw: list[str] | None, root: Path | None = None) -> list[str]:
    if not raw:
        return []
    ensure_default_folders(root)
    valid = {f["id"] for f in list_folders(root)}
    out: list[str] = []
    seen: set[str] = set()
    for fid in raw:
        fid = str(fid or "").strip()
        if not fid or fid in seen:
            continue
        if fid not in valid:
            continue
        seen.add(fid)
        out.append(fid)
    return out


def ensure_default_folders(root: Path | None = None) -> list[dict[str, Any]]:
    data = _load(root)
    existing_ids = {str(f.get("id")) for f in (data.get("folders") or []) if f.get("id")}
    existing_names = {str(f.get("name")) for f in (data.get("folders") or []) if f.get("name")}
    changed = False
    for i, d in enumerate(DEFAULT_FOLDERS):
        if d["id"] in existing_ids or d["name"] in existing_names:
            continue
        data.setdefault("folders", []).append(
            {
                **d,
                "sort": d.get("sort", i),
                "created_at": _now(),
                "builtin": True,
            }
        )
        existing_ids.add(d["id"])
        existing_names.add(d["name"])
        changed = True
    if changed or not data.get("folders"):
        if not data.get("folders"):
            for i, d in enumerate(DEFAULT_FOLDERS):
                data.setdefault("folders", []).append(
                    {**d, "sort": i, "created_at": _now(), "builtin": True}
                )
        _save(data, root)
    return list_folders(root)


def list_folders(root: Path | None = None) -> list[dict[str, Any]]:
    data = _load(root)
    folders = [f for f in (data.get("folders") or []) if isinstance(f, dict) and f.get("id") and f.get("name")]
    folders.sort(key=lambda f: (int(f.get("sort") or 0), str(f.get("name") or "")))
    return folders


def create_folder(name: str, root: Path | None = None) -> dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise ValueError("资料夹名称不能为空")
    if len(name) > 40:
        raise ValueError("资料夹名称过长")
    ensure_default_folders(root)
    data = _load(root)
    for f in data.get("folders") or []:
        if str(f.get("name")) == name:
            raise ValueError(f"资料夹已存在：{name}")
    slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", name).strip("-")[:24] or "fld"
    item = {
        "id": f"fld-{slug}-{uuid.uuid4().hex[:6]}",
        "name": name,
        "sort": len(data.get("folders") or []),
        "created_at": _now(),
        "builtin": False,
    }
    data.setdefault("folders", []).append(item)
    _save(data, root)
    return item


def update_folder(folder_id: str, *, name: str | None = None, root: Path | None = None) -> dict[str, Any]:
    folder_id = (folder_id or "").strip()
    data = _load(root)
    for f in data.get("folders") or []:
        if str(f.get("id")) != folder_id:
            continue
        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError("资料夹名称不能为空")
            for other in data.get("folders") or []:
                if other is not f and str(other.get("name")) == name:
                    raise ValueError(f"资料夹已存在：{name}")
            f["name"] = name
        _save(data, root)
        return dict(f)
    raise KeyError(f"资料夹不存在：{folder_id}")


def delete_folder(folder_id: str, root: Path | None = None) -> None:
    folder_id = (folder_id or "").strip()
    data = _load(root)
    before = len(data.get("folders") or [])
    data["folders"] = [f for f in (data.get("folders") or []) if str(f.get("id")) != folder_id]
    if len(data["folders"]) == before:
        raise KeyError(f"资料夹不存在：{folder_id}")
    _save(data, root)


def expand_folder_ids_to_scope_paths(folder_ids: list[str] | None, root: Path | None = None) -> list[str]:
    """Resolve folder membership → scope_paths for RAG (empty input → empty list)."""
    root = root or wiki_root()
    wanted = set(normalize_folder_ids(folder_ids, root))
    if not wanted:
        return []

    out: set[str] = set()

    from .wiki import list_pages

    for page in list_pages(root, include_inbox=False):
        p_ids = set(getattr(page, "folder_ids", None) or [])
        if p_ids & wanted:
            out.add(page.rel_path.replace("\\", "/"))

    from .assets import list_assets

    for asset in list_assets(root):
        a_ids = set(getattr(asset, "folder_ids", None) or [])
        if a_ids & wanted:
            out.add(asset.rel_path.replace("\\", "/"))
            if asset.wiki_page:
                out.add(asset.wiki_page.replace("\\", "/"))

    try:
        from .linked_dirs import list_linked_dirs

        for item in list_linked_dirs().get("items") or []:
            d_ids = set(item.get("folder_ids") or [])
            if not (d_ids & wanted):
                continue
            raw = str(item.get("path") or "").strip()
            if not raw:
                continue
            try:
                abs_p = str(Path(raw).expanduser().resolve()).replace("\\", "/")
            except OSError:
                abs_p = raw.replace("\\", "/")
            out.add(f"@external:{abs_p}")
    except Exception:
        pass

    return sorted(out)


def merge_scope_with_folders(
    scope_paths: list[str] | None,
    folder_ids: list[str] | None,
    root: Path | None = None,
) -> list[str] | None:
    """
    Combine explicit paths with folder expansion.
    - Neither set → None (search all)
    - Only folders → folder paths
    - Only paths → paths
    - Both → intersection if both non-empty after expand; if folder expand empty, keep paths
    """
    paths = [p for p in (scope_paths or []) if p and str(p).strip()]
    fpaths = expand_folder_ids_to_scope_paths(folder_ids, root)
    if not paths and not fpaths:
        return None if not (folder_ids or []) else []
    if paths and fpaths:
        ps, fs = set(paths), set(fpaths)
        inter = sorted(ps & fs)
        # If user picked folders + files, prefer union so both constraints contribute
        return sorted(ps | fs)
    return paths or fpaths
