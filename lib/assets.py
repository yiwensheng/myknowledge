"""Asset storage and manifest for media files."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, asdict, field, fields
from pathlib import Path

from .config import wiki_root
from .media_types import MIME_MAP, category_for, is_supported
from .wiki import today_beijing

MANIFEST = "assets/manifest.json"
EXTRACTED_DIR = "assets/.extracted"


@dataclass
class AssetRecord:
    id: str
    rel_path: str
    filename: str
    category: str
    mime: str
    size: int
    extracted_path: str
    wiki_page: str
    created: str
    updated: str
    folder_ids: list[str] = field(default_factory=list)


def _manifest_path(root: Path) -> Path:
    return root / MANIFEST


def load_manifest(root: Path | None = None) -> dict:
    root = root or wiki_root()
    p = _manifest_path(root)
    if not p.is_file():
        return {"items": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"items": []}


def save_manifest(data: dict, root: Path | None = None) -> None:
    root = root or wiki_root()
    p = _manifest_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def list_assets(root: Path | None = None) -> list[AssetRecord]:
    data = load_manifest(root)
    out: list[AssetRecord] = []
    allowed = {f.name for f in fields(AssetRecord)}
    for item in data.get("items") or []:
        if not isinstance(item, dict):
            continue
        try:
            kwargs = {k: item[k] for k in allowed if k in item}
            if "folder_ids" not in kwargs:
                kwargs["folder_ids"] = list(item.get("folder_ids") or [])
            else:
                kwargs["folder_ids"] = [str(x) for x in (kwargs["folder_ids"] or []) if str(x).strip()]
            out.append(AssetRecord(**kwargs))
        except TypeError:
            continue
    return out


def set_asset_folder_ids(asset_id: str, folder_ids: list[str], root: Path | None = None) -> AssetRecord:
    from .folders import normalize_folder_ids

    root = root or wiki_root()
    ids = normalize_folder_ids(folder_ids, root)
    data = load_manifest(root)
    for item in data.get("items") or []:
        if str(item.get("id")) != asset_id:
            continue
        item["folder_ids"] = ids
        save_manifest(data, root)
        rec = get_asset(asset_id, root)
        if not rec:
            raise KeyError(asset_id)
        return rec
    raise KeyError(asset_id)


def _safe_filename(name: str) -> str:
    base = Path(name).name.strip()
    base = re.sub(r'[<>:"/\\|?*]', "_", base)
    return base or "upload.bin"


def list_assets_page(
    root: Path | None = None,
    page: int = 1,
    size: int = 20,
) -> dict:
    from .paging import paginate

    items = [asdict(a) for a in list_assets(root)]
    items.sort(key=lambda x: (x.get("updated") or "", x.get("filename") or ""), reverse=True)
    return paginate(items, page, size)


def find_by_hash(digest: str, root: Path | None = None) -> AssetRecord | None:
    for rec in list_assets(root):
        if rec.id == digest:
            return rec
    return None


def store_asset(
    src: Path,
    root: Path | None = None,
    extracted_text: str = "",
    original_filename: str | None = None,
) -> tuple[AssetRecord, str]:
    """Copy file into assets/, save extracted sidecar. Returns (record, extracted_text)."""
    root = root or wiki_root()
    if not is_supported(src.suffix):
        raise ValueError(f"unsupported extension: {src.suffix}")

    display_name = _safe_filename(original_filename or src.name)
    digest = file_sha256(src)
    existing = find_by_hash(digest, root)
    if existing:
        ep = root / existing.extracted_path
        text = ep.read_text(encoding="utf-8") if ep.is_file() else extracted_text
        if original_filename and existing.filename != display_name:
            _update_asset_filename(existing.id, display_name, root)
            existing = find_by_hash(digest, root) or existing
        return existing, text

    cat = category_for(src.suffix)
    dest_dir = root / "assets" / cat
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{digest}-{display_name}"
    if not dest.is_file():
        shutil.copy2(src, dest)

    ext_dir = root / EXTRACTED_DIR
    ext_dir.mkdir(parents=True, exist_ok=True)
    ext_path = ext_dir / f"{digest}.txt"
    if extracted_text:
        ext_path.write_text(extracted_text, encoding="utf-8")
    elif not ext_path.is_file():
        ext_path.write_text("", encoding="utf-8")

    today = today_beijing()
    rel = dest.relative_to(root).as_posix()
    rec = AssetRecord(
        id=digest,
        rel_path=rel,
        filename=display_name,
        category=cat,
        mime=MIME_MAP.get(Path(display_name).suffix.lower(), "application/octet-stream"),
        size=dest.stat().st_size,
        extracted_path=f"{EXTRACTED_DIR}/{digest}.txt",
        wiki_page="",
        created=today,
        updated=today,
    )
    data = load_manifest(root)
    items = [i for i in (data.get("items") or []) if i.get("id") != digest]
    items.append(asdict(rec))
    data["items"] = items
    save_manifest(data, root)
    text = ext_path.read_text(encoding="utf-8") if ext_path.is_file() else extracted_text
    return rec, text


def _update_asset_filename(asset_id: str, filename: str, root: Path | None = None) -> None:
    root = root or wiki_root()
    data = load_manifest(root)
    for item in data.get("items") or []:
        if item.get("id") == asset_id:
            item["filename"] = filename
            item["updated"] = today_beijing()
    save_manifest(data, root)


def update_asset_wiki_page(asset_id: str, wiki_page: str, root: Path | None = None) -> None:
    root = root or wiki_root()
    data = load_manifest(root)
    for item in data.get("items") or []:
        if item.get("id") == asset_id:
            item["wiki_page"] = wiki_page
            item["updated"] = today_beijing()
    save_manifest(data, root)


def read_extracted(rec: AssetRecord, root: Path | None = None) -> str:
    root = root or wiki_root()
    p = root / rec.extracted_path
    if p.is_file():
        return p.read_text(encoding="utf-8")
    return ""


def get_asset(asset_id: str, root: Path | None = None) -> AssetRecord | None:
    for rec in list_assets(root):
        if rec.id == asset_id:
            return rec
    return None


def rename_asset(asset_id: str, filename: str, root: Path | None = None) -> AssetRecord:
    root = root or wiki_root()
    rec = get_asset(asset_id, root)
    if not rec:
        raise FileNotFoundError("asset not found")

    new_name = _safe_filename(filename)
    if not new_name:
        raise ValueError("invalid filename")

    old_path = root / rec.rel_path
    if not old_path.is_file():
        raise FileNotFoundError("asset file missing on disk")

    new_path = old_path.parent / f"{rec.id}-{new_name}"
    if new_path != old_path:
        if new_path.is_file():
            raise ValueError("target filename already exists")
        old_path.rename(new_path)

    new_rel = new_path.relative_to(root).as_posix()
    data = load_manifest(root)
    for item in data.get("items") or []:
        if item.get("id") == asset_id:
            item["filename"] = new_name
            item["rel_path"] = new_rel
            item["mime"] = MIME_MAP.get(Path(new_name).suffix.lower(), item.get("mime", ""))
            item["updated"] = today_beijing()
    save_manifest(data, root)

    if rec.wiki_page:
        wp = root / rec.wiki_page
        if wp.is_file():
            from .wiki import parse_frontmatter, serialize_page

            meta, body = parse_frontmatter(wp.read_text(encoding="utf-8"))
            meta["asset_path"] = new_rel
            meta["title"] = Path(new_name).stem
            meta["updated"] = today_beijing()
            wp.write_text(serialize_page(meta, body), encoding="utf-8")

    updated = get_asset(asset_id, root)
    if not updated:
        raise RuntimeError("asset update failed")
    return updated


def delete_asset(asset_id: str, root: Path | None = None) -> dict:
    root = root or wiki_root()
    rec = get_asset(asset_id, root)
    if not rec:
        raise FileNotFoundError("asset not found")

    deleted_wiki = ""
    if rec.wiki_page:
        from .wiki import delete_page

        if delete_page(rec.wiki_page, root):
            deleted_wiki = rec.wiki_page

    for rel in (rec.rel_path, rec.extracted_path):
        p = root / rel
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass

    data = load_manifest(root)
    data["items"] = [i for i in (data.get("items") or []) if i.get("id") != asset_id]
    save_manifest(data, root)

    from .rag import rebuild_index

    rebuild_index(root)
    return {"deleted": asset_id, "wiki_page": deleted_wiki}
