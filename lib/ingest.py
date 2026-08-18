"""Auto-ingest raw files from inbox into wiki + RAG (all media types)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from .assets import store_asset, update_asset_wiki_page
from .config import wiki_root
from .document_analysis import analyze_document, build_source_wiki_body, merge_tags
from .extract import extract_text
from .media_types import TEXT_LIKE, is_supported
from .rag import rebuild_index
from .wiki import parse_frontmatter, save_page, today_beijing

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
_ingest_lock = threading.Lock()
_processing_paths: set[str] = set()
_bg_lock = threading.Lock()
_bg_embed_roots: set[str] = set()


def _run_update_index(root: Path) -> None:
    script = SCRIPTS / "update_index.py"
    if script.is_file():
        subprocess.run(
            [sys.executable, str(script), "--root", str(root)],
            check=False,
            env={**dict(__import__("os").environ), "PYTHONIOENCODING": "utf-8"},
        )


def defer_wiki_index_update(root: Path | None = None) -> None:
    """Rebuild index/*.md in a background thread (non-blocking)."""
    root = root or wiki_root()
    key = str(root.resolve())

    def job() -> None:
        _run_update_index(Path(key))

    threading.Thread(target=job, daemon=True, name="wiki-index-update").start()


def defer_embedding_sync(root: Path | None = None) -> None:
    """Sync vector embeddings in background; coalesce concurrent requests per root."""
    root = root or wiki_root()
    key = str(root.resolve())
    with _bg_lock:
        if key in _bg_embed_roots:
            return
        _bg_embed_roots.add(key)

    def job() -> None:
        try:
            from .rag import _index_path
            from .rag_embed import sync_embeddings

            idx = _index_path(Path(key))
            if not idx.is_file():
                return
            data = json.loads(idx.read_text(encoding="utf-8"))
            sync_embeddings(data.get("chunks") or [], Path(key))
        finally:
            with _bg_lock:
                _bg_embed_roots.discard(key)

    threading.Thread(target=job, daemon=True, name="rag-embed-sync").start()


def defer_refresh_rag(root: Path | None = None) -> None:
    """Rebuild RAG index in background (non-blocking)."""
    root = root or wiki_root()
    key = str(root.resolve())

    def job() -> None:
        refresh_rag(Path(key))

    threading.Thread(target=job, daemon=True, name="rag-refresh").start()


def _guess_type(text: str, filename: str) -> str:
    lower = (text + filename).lower()
    if " vs " in lower or "对比" in text[:200]:
        return "comparison"
    if re.search(r"https?://", text[:500]):
        return "source"
    if any(k in lower for k in ("原理", "方法", "流程", "架构", "闭环")):
        return "concept"
    if any(k in lower for k in ("工具", "产品", "平台", "接口")):
        return "entity"
    return "note"


def _extract_title(text: str, path: Path) -> str:
    meta, body = parse_frontmatter(text)
    if meta.get("title"):
        return str(meta["title"])
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem


def _extract_url(text: str) -> str:
    m = re.search(r"https?://[^\s\)\]\"']+", text)
    return m.group(0) if m else ""


def _maybe_reindex(root: Path, *, defer_index: bool) -> None:
    if defer_index:
        return
    rebuild_index(root)
    _run_update_index(root)


def _ingest_media(
    path: Path,
    root: Path,
    move_inbox: bool,
    original_filename: str | None = None,
    *,
    defer_index: bool = False,
    defer_analyze: bool = False,
) -> str | None:
    from .assets import find_by_hash, file_sha256

    display_name = original_filename or path.name
    digest = file_sha256(path)
    existing = find_by_hash(digest, root)
    if existing and existing.wiki_page:
        ep = root / existing.wiki_page
        if ep.is_file():
            if original_filename:
                from .assets import _safe_filename, _update_asset_filename

                display = _safe_filename(original_filename)
                if display and existing.filename != display:
                    _update_asset_filename(existing.id, display, root)
            _maybe_reindex(root, defer_index=defer_index)
            return existing.wiki_page

    extracted = extract_text(path)
    rec, _ = store_asset(path, root, extracted_text=extracted, original_filename=original_filename)
    title = Path(display_name).stem
    if defer_analyze:
        from .document_analysis import excerpt_fallback

        analysis = excerpt_fallback(extracted)
    else:
        analysis = analyze_document(
            extracted,
            title=title,
            source_kind=rec.category or "document",
        )
    source_lines = [
        f"- 文件名: {rec.filename}",
        f"- 路径: `{rec.rel_path}`",
        f"- 类型: {rec.mime}",
        f"- 大小: {rec.size} bytes",
    ]
    body = build_source_wiki_body(
        title=title,
        source_lines=source_lines,
        raw_content=extracted,
        analysis=analysis,
        body_heading="## 提取内容",
    )
    tags = merge_tags([rec.category], analysis)
    extra_meta = {"assumptions": analysis.assumptions} if analysis.assumptions else None
    page = save_page(
        page_type=analysis.wiki_type if analysis.method == "llm" else "source",
        title=title,
        body=body,
        tags=tags,
        status="draft",
        asset_path=rec.rel_path,
        asset_mime=rec.mime,
        root=root,
        extra_meta=extra_meta,
    )
    update_asset_wiki_page(rec.id, page.rel_path, root)

    if move_inbox and "inbox" in path.parts:
        processed = root / "archive" / "inbox-processed"
        processed.mkdir(parents=True, exist_ok=True)
        dest = processed / path.name
        if dest.exists():
            dest = processed / f"{path.stem}-{today_beijing()}{path.suffix}"
        if path.resolve() != (root / rec.rel_path).resolve():
            try:
                path.unlink()
            except OSError:
                shutil.move(str(path), str(dest))
    return page.rel_path


def _ingest_text_markdown(path: Path, root: Path, move_inbox: bool, *, defer_index: bool = False) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    meta, body = parse_frontmatter(text)
    rel_in_wiki = None

    try:
        rel = path.relative_to(root)
        parts = rel.parts
        if parts and parts[0] in (
            "concepts",
            "entities",
            "sources",
            "comparisons",
            "notes",
            "archive",
            "distill",
        ):
            _maybe_reindex(root, defer_index=defer_index)
            return rel.as_posix()
    except ValueError:
        pass

    if meta.get("type") and meta.get("title"):
        page_type = str(meta["type"])
        title = str(meta["title"])
        rel_in_wiki = save_page(
            page_type=page_type,
            title=title,
            body=body or text,
            tags=[str(t) for t in (meta.get("tags") or [])],
            status=str(meta.get("status") or "draft"),
            links=[str(x) for x in (meta.get("links") or [])],
            source_url=str(meta.get("source_url") or ""),
            asset_path=str(meta.get("asset_path") or ""),
            asset_mime=str(meta.get("asset_mime") or ""),
            root=root,
        ).rel_path
    else:
        title = _extract_title(text, path)
        page_type = _guess_type(text, path.name)
        url = _extract_url(text)
        body_content = body if body else text
        if not body_content.lstrip().startswith("#"):
            body_content = f"# {title}\n\n{body_content}"
        page = save_page(
            page_type=page_type,
            title=title,
            body=body_content,
            tags=[],
            status="draft",
            source_url=url,
            root=root,
        )
        rel_in_wiki = page.rel_path

    if move_inbox and "inbox" in path.parts:
        processed = root / "archive" / "inbox-processed"
        processed.mkdir(parents=True, exist_ok=True)
        dest = processed / path.name
        if dest.exists():
            dest = processed / f"{path.stem}-{today_beijing()}{path.suffix}"
        shutil.move(str(path), str(dest))

    return rel_in_wiki


def ingest_file(
    path: Path,
    root: Path | None = None,
    move_inbox: bool = True,
    original_filename: str | None = None,
    *,
    defer_index: bool = False,
    defer_analyze: bool = False,
) -> str | None:
    root = root or wiki_root()
    key = str(path.resolve())
    with _ingest_lock:
        if key in _processing_paths:
            return None
        resolved = path.resolve()
        if not resolved.is_file():
            return None
        _processing_paths.add(key)
    try:
        path = resolved
        if "inbox-processed" in path.parts or ".extracted" in path.parts:
            return None
        if path.name == "manifest.json":
            return None

        ext = path.suffix.lower()
        if not is_supported(ext):
            return None

        if ext in TEXT_LIKE:
            rel = _ingest_text_markdown(path, root, move_inbox, defer_index=defer_index)
        else:
            rel = _ingest_media(
                path,
                root,
                move_inbox,
                original_filename=original_filename,
                defer_index=defer_index,
                defer_analyze=defer_analyze,
            )

        if rel and not defer_index:
            rebuild_index(root)
            _run_update_index(root)
        return rel
    except FileNotFoundError:
        return None
    finally:
        with _ingest_lock:
            _processing_paths.discard(key)


def _ingest_workers() -> int:
    try:
        w = int(os.environ.get("MYKNOWLEDGE_INGEST_WORKERS", "0"))
    except ValueError:
        w = 0
    if w > 0:
        return min(8, w)
    return min(4, max(1, (os.cpu_count() or 2) // 2))


def ingest_inbox(root: Path | None = None) -> list[str]:
    return ingest_inbox_bulk(root).get("items") or []


def ingest_inbox_bulk(root: Path | None = None, workers: int | None = None) -> dict:
    """Ingest inbox files; optional parallel extract; single RAG rebuild at end."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    root = root or wiki_root()
    inbox = root / "inbox"
    done: list[str] = []
    errors: list[str] = []
    if not inbox.is_dir():
        return {"count": 0, "items": [], "rag_chunks": 0, "errors": errors}

    files = sorted(p for p in inbox.rglob("*") if p.is_file())
    n_workers = workers if workers is not None else _ingest_workers()

    if n_workers <= 1 or len(files) < 2:
        for path in files:
            try:
                rel = ingest_file(path, root, defer_index=True)
                if rel:
                    done.append(rel)
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")
    else:
        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            futs = {
                pool.submit(ingest_file, path, root, True, None, defer_index=True): path
                for path in files
            }
            for fut in as_completed(futs):
                path = futs[fut]
                try:
                    rel = fut.result()
                    if rel:
                        done.append(rel)
                except Exception as exc:
                    errors.append(f"{path.name}: {exc}")

    rag_chunks = 0
    if done:
        rag_chunks = sync_all(root)
    return {"count": len(done), "items": done, "rag_chunks": rag_chunks, "errors": errors}


def sync_all(root: Path | None = None) -> int:
    root = root or wiki_root()
    n = rebuild_index(root)
    _run_update_index(root)
    try:
        from .writing_style import refresh_style_profile, style_enabled

        if style_enabled():
            refresh_style_profile(force=True, root=root, include_llm=False)
    except Exception:
        pass
    return n


def sync_all_after_upload(root: Path | None = None) -> int:
    """Fast path for batch upload: rebuild chunk index, defer embeddings + wiki index pages."""
    root = root or wiki_root()
    n = rebuild_index(root, embed_async=True)
    defer_wiki_index_update(root)
    return n


def refresh_rag(root: Path | None = None) -> int:
    """Rebuild RAG index only (skip markdown index pages) — faster after single writes."""
    return rebuild_index(root)
