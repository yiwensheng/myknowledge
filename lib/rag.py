"""Local RAG: markdown chunking, TF + vector hybrid retrieval, optional external augment."""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .config import (
    extra_dirs,
    load_dotenv,
    rag_chunk_params,
    rag_child_chunk_size,
    rag_hybrid_weights,
    rag_mode,
    rag_parent_child_enabled,
    rag_top_k,
    wiki_root,
)
from .rag_chunk import chunk_document, chunk_document_parent_child
from .wiki import WikiPage, list_pages, parse_frontmatter

INDEX_FILE = "chunks.json"

_index_cache: dict[str, tuple[float, list[dict], dict[str, int]]] = {}


@dataclass
class RagChunk:
    chunk_id: str
    rel_path: str
    title: str
    text: str
    score: float = 0.0
    retrieval: str = "local"
    asset_path: str = ""
    tags: list[str] = field(default_factory=list)
    parent_id: str = ""
    parent_text: str = ""


def _tokenize(text: str) -> list[str]:
    text = text.lower()
    tokens: list[str] = []
    for m in re.finditer(r"[\u4e00-\u9fff]+|[a-zA-Z0-9_]+", text):
        w = m.group()
        tokens.append(w)
        if len(w) >= 2 and all("\u4e00" <= c <= "\u9fff" for c in w):
            for i in range(len(w) - 1):
                tokens.append(w[i : i + 2])
    return tokens


def _context_prefix(title: str, piece: str) -> str:
    from .config import rag_contextual_enabled

    if not rag_contextual_enabled():
        return ""
    m = re.match(r"^【(.+?)】\n", piece)
    heading = m.group(1).strip() if m else ""
    title = (title or "").strip()
    if heading and title:
        return f"{title} > {heading}"
    return title or heading


def _embed_text_for_chunk(ch: dict) -> str:
    prefix = str(ch.get("context_prefix") or "").strip()
    text = str(ch.get("text") or "")
    if prefix:
        return f"{prefix}\n{text}"
    return text


def _rrf_fuse(ranked_lists: list[list[str]], k: int) -> dict[str, float]:
    scores: dict[str, float] = {}
    for lst in ranked_lists:
        for rank, cid in enumerate(lst, start=1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    return scores


def _chunk_for_index(text: str, title: str = "") -> list[dict[str, str]]:
    """Return list of {text, parent_text?, parent_id?} for indexing."""
    size, overlap = rag_chunk_params()
    if rag_parent_child_enabled():
        child = rag_child_chunk_size()
        parent_size = max(size, child)
        return chunk_document_parent_child(
            text,
            title=title,
            parent_size=parent_size,
            child_size=child,
            overlap=overlap,
        )
    return [{"text": p} for p in chunk_document(text, title=title, size=size, overlap=overlap)]


def _index_path(root: Path | None = None) -> Path:
    root = root or wiki_root()
    d = root / ".rag"
    d.mkdir(parents=True, exist_ok=True)
    return d / INDEX_FILE


def _invalidate_cache(root: Path | None = None) -> None:
    key = str((root or wiki_root()).resolve())
    _index_cache.pop(key, None)


def _append_chunks(
    store: list[dict],
    *,
    rel_path: str,
    title: str,
    content: str,
    external: bool = False,
    asset_path: str = "",
    tags: list[str] | None = None,
) -> int:
    n = 0
    for i, piece in enumerate(_chunk_for_index(content, title=title)):
        child = str(piece.get("text") or "").strip()
        if not child:
            continue
        tokens = _tokenize(child)
        if not tokens:
            continue
        item: dict = {
            "id": f"{rel_path}#{i}",
            "rel_path": rel_path,
            "title": title,
            "text": child,
            "tokens": tokens,
        }
        parent_text = str(piece.get("parent_text") or "").strip()
        parent_id = str(piece.get("parent_id") or "").strip()
        if parent_text and parent_text != child:
            item["parent_text"] = parent_text
        if parent_id:
            item["parent_id"] = f"{rel_path}#{parent_id}"
        prefix = _context_prefix(title, child)
        if prefix:
            item["context_prefix"] = prefix
        if external:
            item["external"] = True
        if asset_path:
            item["asset_path"] = asset_path
        if tags:
            item["tags"] = tags
        store.append(item)
        n += 1
    return n


def _chunk_dict_to_rag(ch: dict, score: float, retrieval: str) -> RagChunk:
    raw_tags = ch.get("tags") or []
    tags = [str(t) for t in raw_tags] if isinstance(raw_tags, list) else []
    return RagChunk(
        chunk_id=str(ch["id"]),
        rel_path=str(ch["rel_path"]),
        title=str(ch.get("title") or ""),
        text=str(ch.get("text") or ""),
        score=score,
        retrieval=retrieval,
        asset_path=str(ch.get("asset_path") or ""),
        tags=tags,
        parent_id=str(ch.get("parent_id") or ""),
        parent_text=str(ch.get("parent_text") or ""),
    )


def expand_to_parents(chunks: list[RagChunk]) -> list[RagChunk]:
    """Deduplicate by parent_id and prefer parent_text for LLM context."""
    if not chunks:
        return []
    seen: set[str] = set()
    out: list[RagChunk] = []
    for c in chunks:
        key = c.parent_id or c.chunk_id
        if key in seen:
            continue
        seen.add(key)
        if c.parent_text and c.parent_text != c.text:
            out.append(
                RagChunk(
                    chunk_id=c.chunk_id,
                    rel_path=c.rel_path,
                    title=c.title,
                    text=c.parent_text,
                    score=c.score,
                    retrieval=c.retrieval,
                    asset_path=c.asset_path,
                    tags=list(c.tags),
                    parent_id=c.parent_id,
                    parent_text=c.parent_text,
                )
            )
        else:
            out.append(c)
    return out


def _index_extra_dirs(store: list[dict], n: int) -> int:
    from .extract import extract_text as ext_text
    from .media_types import is_supported

    for ext_root in extra_dirs():
        prefix = f"@external:{ext_root.as_posix()}"
        try:
            paths = list(ext_root.rglob("*"))
        except OSError:
            continue
        for path in paths:
            if not path.is_file() or not is_supported(path.suffix):
                continue
            try:
                if path.suffix.lower() in (".md", ".txt"):
                    text = path.read_text(encoding="utf-8")
                    meta, body = parse_frontmatter(text)
                    content = body if meta else text
                    title = str(meta.get("title") or path.stem)
                else:
                    content = ext_text(path)
                    title = path.stem
                if not content.strip():
                    continue
                rel = f"{prefix}/{path.relative_to(ext_root).as_posix()}"
                n += _append_chunks(store, rel_path=rel, title=title, content=content, external=True)
            except OSError:
                continue
    return n


def _extract_external_file(ext_root: Path, path: Path) -> tuple[str, str, str] | None:
    from .extract import extract_text as ext_text
    from .media_types import is_supported

    if not path.is_file() or not is_supported(path.suffix):
        return None
    prefix = f"@external:{ext_root.as_posix()}"
    try:
        if path.suffix.lower() in (".md", ".txt"):
            text = path.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            content = body if meta else text
            title = str(meta.get("title") or path.stem)
        else:
            content = ext_text(path)
            title = path.stem
        if not content.strip():
            return None
        rel = f"{prefix}/{path.relative_to(ext_root).as_posix()}"
        return rel, title, content
    except OSError:
        return None


def reindex_linked_dirs(
    paths: list[Path] | None = None,
    *,
    root: Path | None = None,
    progress: Callable[[str, int, int, str], None] | None = None,
) -> int:
    """Re-index @external chunks for linked dirs with optional progress callback."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from .ingest import _ingest_workers

    root = root or wiki_root()
    ext_roots = list(paths) if paths else extra_dirs()
    if not ext_roots:
        return 0

    prefixes = [f"@external:{r.as_posix()}" for r in ext_roots]

    idx_path = _index_path(root)
    if idx_path.is_file():
        try:
            data = json.loads(idx_path.read_text(encoding="utf-8"))
            store: list[dict] = list(data.get("chunks") or [])
        except (json.JSONDecodeError, OSError):
            store = []
    else:
        return rebuild_index(root)

    store = [
        ch
        for ch in store
        if not any(str(ch.get("rel_path") or "").startswith(p) for p in prefixes)
    ]

    tasks: list[tuple[Path, Path]] = []
    from .media_types import is_supported

    for ext_root in ext_roots:
        if not ext_root.is_dir():
            continue
        try:
            for path in ext_root.rglob("*"):
                if path.is_file() and is_supported(path.suffix):
                    tasks.append((ext_root, path))
        except OSError:
            continue

    total = len(tasks)
    if progress:
        progress("scan", total, 0, "")

    n = len(store)
    done = 0
    workers = _ingest_workers()

    def _one(task: tuple[Path, Path]) -> tuple[str, str, str] | None:
        return _extract_external_file(task[0], task[1])

    if workers <= 1 or total < 2:
        for ext_root, path in tasks:
            row = _extract_external_file(ext_root, path)
            done += 1
            if progress:
                progress("extract", total, done, path.name)
            if row:
                rel, title, content = row
                n += _append_chunks(store, rel_path=rel, title=title, content=content, external=True)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(_one, t): t for t in tasks}
            for fut in as_completed(futs):
                ext_root, path = futs[fut]
                done += 1
                if progress:
                    progress("extract", total, done, path.name)
                try:
                    row = fut.result()
                except Exception:
                    row = None
                if row:
                    rel, title, content = row
                    n += _append_chunks(store, rel_path=rel, title=title, content=content, external=True)

    if progress:
        progress("embed", total, total, "正在写入向量索引…")

    idx_path.write_text(json.dumps({"chunks": store}, ensure_ascii=False, indent=2), encoding="utf-8")
    _invalidate_cache(root)

    from .rag_embed import sync_embeddings

    sync_embeddings(store, root)
    from .rag_fts import ensure_fts_schema, sync_fts_index

    if ensure_fts_schema(root):
        sync_fts_index(store, root)
    return n


def rebuild_index(root: Path | None = None, *, embed_async: bool = False) -> int:
    from .index_writer import with_index_lock

    return with_index_lock(root, lambda: _rebuild_index_unlocked(root, embed_async=embed_async))


def _rebuild_index_unlocked(root: Path | None = None, *, embed_async: bool = False) -> int:
    root = root or wiki_root()
    store: list[dict] = []
    n = 0
    for page in list_pages(root, include_inbox=False):
        full = page.body
        if page.title and page.title not in full[:50]:
            full = f"{page.title}\n{full}"
        n += _append_chunks(
            store,
            rel_path=page.rel_path,
            title=page.title,
            content=full,
            asset_path=page.asset_path,
            tags=page.tags,
        )

    from .assets import list_assets, read_extracted

    for rec in list_assets(root):
        text = read_extracted(rec, root)
        if not text.strip():
            continue
        n += _append_chunks(
            store,
            rel_path=rec.wiki_page or rec.rel_path,
            title=rec.filename,
            content=text,
            asset_path=rec.rel_path,
            tags=[rec.category],
        )

    inbox = root / "inbox"
    if inbox.is_dir():
        from .media_types import is_supported

        for path in inbox.rglob("*"):
            if not path.is_file() or not is_supported(path.suffix):
                continue
            if "inbox-processed" in path.parts:
                continue
            try:
                if path.suffix.lower() in (".md", ".txt"):
                    text = path.read_text(encoding="utf-8")
                    meta, body = parse_frontmatter(text)
                    content = body if meta else text
                else:
                    from .extract import extract_text as ext_text

                    content = ext_text(path)
                rel = path.relative_to(root).as_posix()
                n += _append_chunks(store, rel_path=rel, title=path.stem, content=content)
            except OSError:
                continue

    n = _index_extra_dirs(store, n)

    idx_path = _index_path(root)
    idx_path.write_text(json.dumps({"chunks": store}, ensure_ascii=False, indent=2), encoding="utf-8")
    _invalidate_cache(root)

    if embed_async:
        from .ingest import defer_embedding_sync

        defer_embedding_sync(root)
    else:
        from .rag_embed import sync_embeddings

        sync_embeddings(store, root)
    from .rag_fts import ensure_fts_schema, sync_fts_index

    if ensure_fts_schema(root):
        sync_fts_index(store, root)
    return n


def upsert_page_index(
    page: WikiPage,
    root: Path | None = None,
    *,
    embed_async: bool = False,
) -> int:
    """Incrementally update RAG chunks for one wiki page (fast path after single save)."""
    root = root or wiki_root()
    idx_path = _index_path(root)
    if not idx_path.is_file():
        return rebuild_index(root)

    try:
        data = json.loads(idx_path.read_text(encoding="utf-8"))
        store: list[dict] = list(data.get("chunks") or [])
    except (json.JSONDecodeError, OSError):
        return rebuild_index(root)

    rel = page.rel_path
    store = [ch for ch in store if ch.get("rel_path") != rel]

    full = page.body
    if page.title and page.title not in full[:50]:
        full = f"{page.title}\n{full}"
    n = _append_chunks(
        store,
        rel_path=rel,
        title=page.title,
        content=full,
        asset_path=page.asset_path,
        tags=page.tags,
    )

    idx_path.write_text(
        json.dumps({"chunks": store}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    _invalidate_cache(root)

    if embed_async:
        from .ingest import defer_embedding_sync

        defer_embedding_sync(root)
    else:
        from .rag_embed import sync_embeddings

        sync_embeddings(store, root)
    from .rag_fts import ensure_fts_schema, sync_fts_for_rel_path

    if ensure_fts_schema(root):
        sync_fts_for_rel_path(rel, [ch for ch in store if ch.get("rel_path") == rel], root)
    return n


def remove_page_from_index(rel_path: str, root: Path | None = None) -> int:
    """Remove RAG chunks for a deleted wiki page (fast path; no full rebuild)."""
    root = root or wiki_root()
    rel = rel_path.replace("\\", "/").strip().lstrip("/")
    idx_path = _index_path(root)
    if not idx_path.is_file():
        return 0
    try:
        data = json.loads(idx_path.read_text(encoding="utf-8"))
        store: list[dict] = list(data.get("chunks") or [])
    except (json.JSONDecodeError, OSError):
        return 0
    before = len(store)
    store = [ch for ch in store if ch.get("rel_path") != rel]
    removed = before - len(store)
    if not removed:
        return 0
    idx_path.write_text(
        json.dumps({"chunks": store}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    _invalidate_cache(root)
    try:
        from .rag_embed import sync_embeddings

        sync_embeddings(store, root)
    except Exception:
        pass
    try:
        from .rag_fts import ensure_fts_schema, sync_fts_for_rel_path

        if ensure_fts_schema(root):
            sync_fts_for_rel_path(rel, [], root)
    except Exception:
        pass
    return removed


def _load_index_lazy(root: Path | None = None) -> tuple[list[dict], dict[str, int]]:
    root = root or wiki_root()
    path = _index_path(root)
    if not path.is_file():
        from .index_writer import is_index_building, schedule_index_build

        if not is_index_building(root):
            schedule_index_build(root)
        return [], {}
    mtime = path.stat().st_mtime
    key = str(root.resolve())
    cached = _index_cache.get(key)
    if cached and cached[0] == mtime:
        return cached[1], cached[2]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return [], {}
    chunks: list[dict] = data.get("chunks") or []
    df: dict[str, int] = {}
    for ch in chunks:
        for t in set(ch.get("tokens") or []):
            df[t] = df.get(t, 0) + 1
    _index_cache[key] = (mtime, chunks, df)
    return chunks, df


def _load_index(root: Path | None = None) -> tuple[list[dict], dict[str, int]]:
    return _load_index_lazy(root)


def _rebuild_df(chunks: list[dict]) -> dict[str, int]:
    df: dict[str, int] = {}
    for ch in chunks:
        for t in set(ch.get("tokens") or []):
            df[t] = df.get(t, 0) + 1
    return df


def _normalize_scores(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    vals = list(scores.values())
    lo, hi = min(vals), max(vals)
    if hi <= lo:
        return {k: 1.0 if v > 0 else 0.0 for k, v in scores.items()}
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}


def _keyword_scores(query: str, chunks: list[dict], df: dict[str, int], root: Path | None = None) -> dict[str, float]:
    allowed = {str(ch["id"]) for ch in chunks}
    from .config import rag_coarse_k, rag_fts5_enabled, rag_use_rrf
    from .rag_fts import bm25_scores, fts5_enabled

    use_fts = rag_fts5_enabled() and (rag_use_rrf() or fts5_enabled(root))
    if use_fts:
        fts = bm25_scores(query, root=root, limit=rag_coarse_k(), allowed_ids=allowed)
        if fts:
            return fts
    q_tokens = _tokenize(query)
    if not q_tokens:
        return {}
    N = len(chunks)
    q_set = set(q_tokens)
    out: dict[str, float] = {}
    for ch in chunks:
        tokens = ch.get("tokens") or []
        if not tokens:
            continue
        tf: dict[str, int] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        s = 0.0
        for qt in q_set:
            if qt in tf:
                idf = math.log(1 + N / (1 + df.get(qt, 0)))
                s += (1 + math.log(1 + tf[qt])) * idf
        if s <= 0:
            continue
        title_lower = str(ch.get("title") or "").lower()
        if any(qt in title_lower for qt in q_set):
            s *= 1.35
        text = str(ch.get("text") or "")
        if "分析提炼" in text or "### 核心要点" in text:
            s *= 1.22
        out[str(ch["id"])] = s
    return out


def _vector_scores_for_query(query: str, chunks: list[dict], root: Path | None) -> dict[str, float]:
    from .rag_embed import embed_query, embeddings_available, vector_scores

    if not embeddings_available():
        return {}
    q_vec = embed_query(query, root)
    if not q_vec:
        return {}
    ids = [str(ch["id"]) for ch in chunks]
    return vector_scores(q_vec, ids, root)


def _search_local(
    query: str,
    top_k: int,
    root: Path | None,
    scope_paths: list[str] | None = None,
) -> list[RagChunk]:
    root = root or wiki_root()
    chunks, df = _load_index(root)
    if not chunks:
        return []

    if scope_paths:
        from .rag_scope import filter_index_chunks

        chunks = filter_index_chunks(chunks, scope_paths, root)
        if not chunks:
            return []
        df = _rebuild_df(chunks)

    mode = rag_mode()
    if scope_paths:
        load_dotenv()
        if os.environ.get("MYKNOWLEDGE_SCOPE_KEYWORD_ONLY", "1").strip().lower() not in (
            "0",
            "false",
            "no",
        ):
            mode = "keyword"

    from .config import rag_coarse_k, rag_rrf_k, rag_use_rrf
    from .rag_fts import fts5_enabled

    fetch_k = max(top_k, rag_coarse_k()) if mode == "hybrid" and rag_use_rrf() else top_k
    kw_raw = _keyword_scores(query, chunks, df, root)
    vec_raw: dict[str, float] = {}
    if mode in ("vector", "hybrid"):
        vec_raw = _vector_scores_for_query(query, chunks, root)

    by_id = {str(ch["id"]): ch for ch in chunks}
    used_fts = bool(fts5_enabled(root) and kw_raw)

    def to_chunks(ranked: list[tuple[str, float]], tag: str) -> list[RagChunk]:
        out: list[RagChunk] = []
        for cid, sc in ranked:
            if cid not in by_id:
                continue
            ch = by_id[cid]
            out.append(_chunk_dict_to_rag(ch, sc, tag))
        return out

    if mode == "keyword" or (mode == "hybrid" and not vec_raw):
        ranked = sorted(kw_raw.items(), key=lambda x: -x[1])[:top_k]
        tag = "keyword-fts" if used_fts else "keyword"
        if mode != "keyword":
            tag = f"{tag}-fallback"
        return to_chunks(ranked, tag)

    if mode == "vector":
        ranked = sorted(vec_raw.items(), key=lambda x: -x[1])[:top_k]
        return to_chunks(ranked, "vector")

    if rag_use_rrf() and (kw_raw or vec_raw):
        kw_ranked = [cid for cid, _ in sorted(kw_raw.items(), key=lambda x: -x[1])[:fetch_k]]
        vec_ranked = [cid for cid, _ in sorted(vec_raw.items(), key=lambda x: -x[1])[:fetch_k]]
        lists = [x for x in (kw_ranked, vec_ranked) if x]
        fused = _rrf_fuse(lists, rag_rrf_k())
        ranked = sorted(fused.items(), key=lambda x: -x[1])[:top_k]
        kw_set = set(kw_ranked)
        vec_set = set(vec_ranked)
        out: list[RagChunk] = []
        for cid, sc in ranked:
            if cid not in by_id:
                continue
            ch = by_id[cid]
            text = str(ch.get("text") or "")
            if "分析提炼" in text or "### 核心要点" in text:
                sc *= 1.12
            if cid in kw_set and cid in vec_set:
                tag = "hybrid-rrf"
            elif cid in vec_set:
                tag = "vector"
            else:
                tag = "keyword-fts" if used_fts else "keyword"
            out.append(_chunk_dict_to_rag(ch, sc, tag))
        return out

    kw_w, vec_w = rag_hybrid_weights()
    kw_norm = _normalize_scores(kw_raw)
    vec_norm = _normalize_scores(vec_raw)
    combined: dict[str, float] = {}
    from .config import rag_hybrid_use_max

    use_max = rag_hybrid_use_max()
    for cid in set(kw_norm) | set(vec_norm):
        ks = kw_w * kw_norm.get(cid, 0.0)
        vs = vec_w * vec_norm.get(cid, 0.0)
        combined[cid] = max(ks, vs) if use_max else ks + vs
    ranked = sorted(combined.items(), key=lambda x: -x[1])[:top_k]
    out = []
    for cid, sc in ranked:
        if cid not in by_id:
            continue
        ch = by_id[cid]
        text = str(ch.get("text") or "")
        if "分析提炼" in text or "### 核心要点" in text:
            sc *= 1.12
        if kw_norm.get(cid, 0) and vec_norm.get(cid, 0):
            tag = "hybrid"
        elif vec_norm.get(cid, 0):
            tag = "vector"
        else:
            tag = "keyword-fts" if used_fts else "keyword"
        out.append(_chunk_dict_to_rag(ch, sc, tag))
    return out


def _search_external(query: str, top_k: int) -> list[RagChunk]:
    from .rag_external import external_enabled, vector_search

    if not external_enabled():
        return []
    ext_k = max(1, min(top_k, int(top_k * 0.6) or 1))
    rows = vector_search(query, top_k=ext_k)
    return [
        RagChunk(
            chunk_id=f"ext:{i}:{c.rel_path}",
            rel_path=c.rel_path,
            title=c.title,
            text=c.text,
            score=c.score,
            retrieval="anythingllm",
        )
        for i, c in enumerate(rows)
    ]


def _search_docubrowser(query: str, top_k: int) -> list[RagChunk]:
    from .docubrowser_bridge import docubrowser_augment_enabled, search_documents

    if not docubrowser_augment_enabled():
        return []
    hits = search_documents(query, top_k=top_k)
    out: list[RagChunk] = []
    for i, h in enumerate(hits):
        rel = f"@docubrowser:{h.path}" if h.path else f"@docubrowser:{i}"
        out.append(
            RagChunk(
                chunk_id=f"db:{i}:{rel}",
                rel_path=rel,
                title=h.title,
                text=h.text,
                score=h.score,
                retrieval="docubrowser",
                asset_path=h.path,
                tags=h.tags or [],
            )
        )
    return out


def _merge_chunks(local: list[RagChunk], external: list[RagChunk], top_k: int) -> list[RagChunk]:
    seen: set[str] = set()
    merged: list[RagChunk] = []

    def _key(c: RagChunk) -> str:
        return (c.text[:120] + c.title).lower()

    for group in (local, external):
        for c in group:
            k = _key(c)
            if k in seen:
                continue
            seen.add(k)
            merged.append(c)
    merged.sort(key=lambda x: -x.score)
    return merged[:top_k]


def search(
    query: str,
    top_k: int | None = None,
    root: Path | None = None,
    scope_paths: list[str] | None = None,
) -> list[RagChunk]:
    k = top_k if top_k is not None else rag_top_k("ask")
    if not query.strip():
        return []

    mode = rag_mode()
    from .rag_external import external_enabled

    if mode == "external" and external_enabled() and not scope_paths:
        return _search_external(query, k)

    local = _search_local(query, k, root, scope_paths=scope_paths)
    from .config import anythingllm_config, rag_coarse_k

    cfg = anythingllm_config()
    if cfg.get("augment") and external_enabled() and mode != "external" and not scope_paths:
        ext = _search_external(query, max(2, k // 2))
        local = _merge_chunks(local, ext, max(k, rag_coarse_k()))

    from .docubrowser_bridge import docubrowser_augment_enabled

    if docubrowser_augment_enabled() and mode != "external" and not scope_paths:
        db = _search_docubrowser(query, max(2, k // 2))
        if db:
            local = _merge_chunks(local, db, max(k, rag_coarse_k()))

    if not scope_paths:
        from .rag_graph import expand_with_links

        local = expand_with_links(local, root=root, final_k=max(k, rag_coarse_k()))

    from .rag_rerank import rerank_available, rerank_chunks

    if rerank_available():
        local = rerank_chunks(query, local, top_k=k)
    else:
        local = sorted(local, key=lambda x: -x.score)[:k]

    return local


def format_context(chunks: list[RagChunk]) -> str:
    chunks = expand_to_parents(chunks)
    parts: list[str] = []
    for i, c in enumerate(chunks, 1):
        tag = c.retrieval or "local"
        src = f"路径：{c.rel_path}"
        if c.asset_path:
            src += f"\n原文件：{c.asset_path}"
        parts.append(
            f"--- 片段 {i}（相关度 {c.score:.2f} · {tag}）---\n"
            f"标题：《{c.title}》\n{src}\n内容：\n{c.text}"
        )
    return "\n\n".join(parts)


def rag_status(root: Path | None = None) -> dict:
    root = root or wiki_root()
    from .docubrowser_bridge import status as docubrowser_status
    from .index_writer import is_index_building
    from .rag_embed import embedding_stats
    from .rag_external import external_status

    chunks, _ = _load_index_lazy(root)
    from .rag_fts import fts5_stats
    from .rag_fts_eval import fts5_recommendation

    n = len(chunks)
    fts = fts5_stats(root)
    return {
        "mode": rag_mode(),
        "chunks": n,
        "chunk_size": rag_chunk_params()[0],
        "embeddings": embedding_stats(root),
        "external": external_status(),
        "docubrowser": docubrowser_status(),
        "linked_dirs": len(extra_dirs()),
        "index_building": is_index_building(root),
        "fts5_enabled": bool(fts.get("enabled")),
        "fts5_chunks": fts.get("chunks", 0),
        **fts5_recommendation(n),
    }
