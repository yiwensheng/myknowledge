"""Ingest URL into Myknowledge wiki (fetch + localize + RAG)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from .config import wiki_root
from .document_analysis import analyze_document, build_source_wiki_body, merge_tags
from .ingest import defer_wiki_index_update
from .rag import upsert_page_index
from .url_fetch import _normalize_url, fetch_url
from .wiki import save_page, slugify, today_beijing

CACHE_FILE = ".wiki-cache.json"


def _load_cache(root: Path) -> dict:
    p = root / CACHE_FILE
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_cache(root: Path, cache: dict) -> None:
    (root / CACHE_FILE).write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _url_cache_key(url: str) -> str:
    return f"url:{url.strip()}"


def _domain_slug(url: str) -> str:
    host = urlparse(url).netloc or "web"
    return re.sub(r"[^a-zA-Z0-9.-]", "-", host)


def validate_url_page_quality(page) -> dict[str, str | bool]:
    """Return quality hints after fetch (WeChat shell-page detection)."""
    title = str(getattr(page, "title", "") or "")
    md = str(getattr(page, "markdown", "") or "")
    bad_title = title.lower() in ("mp.weixin.qq.com", "weixin.qq.com", "") or title == "mp.weixin.qq.com"
    shell = md.count("微信扫一扫") >= 2 or (len(md) < 150 and "mp.weixin.qq.com" in md)
    ok = not bad_title and not shell and len(md.strip()) >= 80
    warning = ""
    if not ok:
        warning = "抓取内容可能不完整（仅壳页或标题无效），建议安装 bun 后重试或使用「粘贴文本」"
    return {"quality_ok": ok, "quality_warning": warning}


def ingest_url(
    url: str,
    root: Path | None = None,
    force: bool = False,
    progress: Callable[[str, str], None] | None = None,
) -> dict:
    """
    Fetch URL, save localized copy under assets/documents/urls/, create sources/ page, rebuild RAG.
    Returns result dict with wiki_page, title, method, duplicate flag.
    """
    root = root or wiki_root()
    url_norm = _normalize_url(url.strip())
    if progress:
        progress("cache", "检查是否已保存…")
    cache = _load_cache(root)
    key = _url_cache_key(url_norm)
    if not force and key in cache:
        existing = cache[key].get("path", "")
        if existing and (root / existing).is_file():
            return {
                "url": url_norm,
                "title": cache[key].get("title", ""),
                "wiki_page": existing,
                "method": cache[key].get("fetch_method", "cache"),
                "duplicate": True,
                "localized": cache[key].get("localized", ""),
            }

    if progress:
        progress("fetch", "正在抓取网页…")
    page = fetch_url(url_norm, progress=progress)
    quality = validate_url_page_quality(page)
    key = _url_cache_key(page.url)
    digest = hashlib.sha256(page.url.encode("utf-8")).hexdigest()[:16]
    urls_dir = root / "assets" / "documents" / "urls"
    urls_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(page.title)[:60] or digest
    local_name = f"{digest}-{_domain_slug(page.url)}-{slug}.md"
    local_path = urls_dir / local_name
    local_path.write_text(page.markdown, encoding="utf-8")
    local_rel = local_path.relative_to(root).as_posix()

    if progress:
        progress("analyze", "正在分析文档…")
    analysis = analyze_document(
        page.markdown,
        title=page.title,
        source_kind="url",
        source_url=page.url,
    )
    source_lines = [
        f"- URL: {page.url}",
        f"- 抓取方式: {page.method}",
        f"- 本地化文件: `{local_rel}`",
        f"- 存档日期: {today_beijing()}",
    ]
    body = build_source_wiki_body(
        title=page.title,
        source_lines=source_lines,
        raw_content=page.markdown,
        analysis=analysis,
    )

    host_tag = _domain_slug(page.url).replace(".", "-")
    if progress:
        progress("save", "正在保存笔记…")
    wiki_page = save_page(
        page_type=analysis.wiki_type if analysis.method == "llm" else "source",
        title=page.title,
        body=body,
        tags=merge_tags(["web", host_tag, "url-import"], analysis),
        status="draft",
        source_url=page.url,
        asset_path=local_rel,
        asset_mime="text/markdown",
        root=root,
    )

    cache[key] = {
        "sha256": hashlib.sha256(page.markdown.encode("utf-8")).hexdigest(),
        "path": wiki_page.rel_path,
        "key": key,
        "title": page.title,
        "fetch_method": page.method,
        "localized": local_rel,
    }
    _save_cache(root, cache)
    if progress:
        progress("index", "正在写入检索库…")
    chunks = upsert_page_index(wiki_page, root, embed_async=True)
    defer_wiki_index_update(root)

    return {
        "url": page.url,
        "title": page.title,
        "wiki_page": wiki_page.rel_path,
        "localized": local_rel,
        "method": page.method,
        "duplicate": False,
        "rag_chunks": chunks,
        "analysis_method": analysis.method,
        **quality,
    }


def _excerpt(md: str, max_len: int = 400) -> str:
    """Legacy excerpt helper (prefer document_analysis.analyze_document)."""
    from .document_analysis import excerpt_fallback

    return excerpt_fallback(md, max_len).summary
