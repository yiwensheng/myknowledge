"""Optional cross-encoder rerank via OpenAI-compatible API."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request

from .config import rag_rerank_config
from .rag import RagChunk


def rerank_available() -> bool:
    cfg = rag_rerank_config()
    return bool(cfg.get("enabled") and cfg.get("url") and cfg.get("api_key"))


def rerank_chunks(query: str, chunks: list[RagChunk], *, top_k: int | None = None) -> list[RagChunk]:
    if not chunks or not rerank_available():
        return chunks[: top_k or len(chunks)]
    cfg = rag_rerank_config()
    docs = [f"{c.title}\n{c.text}"[:2000] for c in chunks]
    url = str(cfg["url"])
    if not url.endswith("/rerank"):
        url = f"{url.rstrip('/')}/rerank"
    body = json.dumps(
        {"model": cfg["model"], "query": query, "documents": docs, "top_n": top_k or len(chunks)},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg['api_key']}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60, context=ssl.create_default_context()) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError):
        return chunks[: top_k or len(chunks)]

    results = data.get("results") or data.get("data") or []
    if not results:
        return chunks[: top_k or len(chunks)]

    out: list[RagChunk] = []
    for item in results:
        idx = item.get("index")
        if idx is None or idx < 0 or idx >= len(chunks):
            continue
        ch = chunks[int(idx)]
        score = float(item.get("relevance_score") or item.get("score") or ch.score)
        out.append(
            RagChunk(
                chunk_id=ch.chunk_id,
                rel_path=ch.rel_path,
                title=ch.title,
                text=ch.text,
                score=score,
                retrieval="rerank",
                asset_path=ch.asset_path,
                tags=ch.tags,
            )
        )
        if top_k and len(out) >= top_k:
            break
    return out or chunks[: top_k or len(chunks)]
