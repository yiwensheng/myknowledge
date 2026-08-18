"""Optional external RAG via AnythingLLM Developer API (vector-search / query chat)."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass

from .config import anythingllm_config, load_dotenv


@dataclass
class ExternalChunk:
    title: str
    rel_path: str
    text: str
    score: float
    source: str = "anythingllm"


def external_enabled() -> bool:
    cfg = anythingllm_config()
    return bool(cfg.get("enabled") and cfg.get("url") and cfg.get("api_key") and cfg.get("workspace"))


def _request(method: str, path: str, body: dict | None = None, timeout: int = 60) -> dict:
    cfg = anythingllm_config()
    url = f"{cfg['url'].rstrip('/')}{path}"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg['api_key']}",
            "Accept": "application/json",
        },
        method=method,
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        raw = resp.read().decode("utf-8")
        if not raw.strip():
            return {}
        return json.loads(raw)


def vector_search(query: str, top_k: int = 4, score_threshold: float | None = None) -> list[ExternalChunk]:
    """POST /api/v1/workspace/{slug}/vector-search"""
    if not external_enabled() or not query.strip():
        return []
    cfg = anythingllm_config()
    slug = str(cfg["workspace"])
    threshold = score_threshold if score_threshold is not None else float(cfg.get("score_threshold") or 0.2)
    try:
        data = _request(
            "POST",
            f"/api/v1/workspace/{slug}/vector-search",
            {"query": query, "topN": max(1, min(20, top_k)), "scoreThreshold": threshold},
        )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, KeyError):
        return []

    results = data.get("results") or data.get("context") or data.get("documents") or []
    if isinstance(results, dict):
        results = results.get("results") or []
    out: list[ExternalChunk] = []
    for i, item in enumerate(results):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("pageContent") or item.get("content") or "").strip()
        if not text:
            continue
        meta = item.get("metadata") or item.get("meta") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                meta = {}
        title = str(meta.get("title") or item.get("title") or f"外部片段{i + 1}")
        src = str(meta.get("source") or meta.get("url") or meta.get("docSource") or "anythingllm")
        rel = f"@anythingllm:{slug}/{src}"
        score = float(item.get("score") or item.get("similarity") or item.get("distance") or 0.0)
        if score > 1.0:
            score = min(1.0, 1.0 / (1.0 + score))
        out.append(ExternalChunk(title=title, rel_path=rel, text=text, score=score))
    return out


def workspace_query_chat(question: str) -> dict | None:
    """POST /api/v1/workspace/{slug}/chat with mode=query."""
    if not external_enabled() or not question.strip():
        return None
    cfg = anythingllm_config()
    slug = str(cfg["workspace"])
    try:
        return _request(
            "POST",
            f"/api/v1/workspace/{slug}/chat",
            {"message": question, "mode": "query"},
            timeout=180,
        )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def external_status() -> dict:
    load_dotenv()
    cfg = anythingllm_config()
    return {
        "enabled": external_enabled(),
        "url": cfg.get("url") or "",
        "workspace": cfg.get("workspace") or "",
        "augment": bool(cfg.get("augment")),
        "chat_fallback": bool(cfg.get("chat_fallback")),
    }
