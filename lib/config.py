"""Paths and environment for Myknowledge."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def _resolve_package_root() -> Path:
    """应用安装/源码树根（skills、prompts、third_party）。不等于用户 wiki 数据目录。"""
    for key in ("MYK_ROOT", "YIZHI_APP_ROOT", "YIZHI_INSTALL_ROOT"):
        env = (os.environ.get(key) or "").strip()
        if env:
            return Path(env).expanduser().resolve()
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        # 安装布局：{app}/runtime/yizhi-backend.exe
        if exe.parent.name.lower() == "runtime":
            return exe.parent.parent
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            p = Path(meipass).resolve()
            # onedir: {app}/runtime/_internal
            if p.name.lower() == "_internal" and p.parent.name.lower() == "runtime":
                return p.parent.parent
            if p.parent.name.lower() == "runtime":
                return p.parent.parent
        return exe.parent
    return Path(__file__).resolve().parent.parent


ROOT = _resolve_package_root()
RAG_DIR = ROOT / ".rag"
ENV_FILE = ROOT / ".env"


def output_dir() -> Path:
    """Writable output directory (follows user wiki root when installed)."""
    return wiki_root() / "output"


# Backward-compatible alias; prefer output_dir() for runtime paths.
OUTPUT_DIR = ROOT / "output"

CONTENT_DIRS = (
    "concepts",
    "entities",
    "sources",
    "comparisons",
    "notes",
    "archive",
    "distill",
)
SCAN_DIRS = CONTENT_DIRS + ("inbox",)
WATCH_DIRS = ("inbox", "assets") + CONTENT_DIRS

TYPE_TO_DIR = {
    "concept": "concepts",
    "entity": "entities",
    "source": "sources",
    "comparison": "comparisons",
    "note": "notes",
}


def extra_dirs() -> list[Path]:
    """Read-only external folders indexed into RAG (managed via linked-dirs.json + .env)."""
    from .linked_dirs import linked_dir_paths

    return linked_dir_paths()


def wiki_root() -> Path:
    env = os.environ.get("WIKI_ROOT") or os.environ.get("MYKNOWLEDGE_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    if os.environ.get("YIZHI_INSTALLED", "").strip().lower() in ("1", "true", "yes"):
        return _installed_user_data_dir()
    return ROOT.resolve()


def _installed_user_data_dir() -> Path:
    """Writable per-user data dir when app is installed under Program Files."""
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if local:
        return (Path(local) / "Yizhi").resolve()
    return (Path.home() / "AppData" / "Local" / "Yizhi").resolve()


def env_file_path() -> Path:
    """Primary .env location: user data dir when installed/portable wiki root is set."""
    wr = os.environ.get("WIKI_ROOT") or os.environ.get("MYKNOWLEDGE_ROOT")
    if wr:
        return Path(wr).expanduser().resolve() / ".env"
    if os.environ.get("YIZHI_INSTALLED", "").strip().lower() in ("1", "true", "yes"):
        return _installed_user_data_dir() / ".env"
    return ENV_FILE


def _dotenv_paths() -> list[Path]:
    seen: set[Path] = set()
    paths: list[Path] = []
    for candidate in (ENV_FILE, env_file_path()):
        resolved = candidate.resolve()
        if resolved not in seen:
            seen.add(resolved)
            paths.append(resolved)
    return paths


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _apply_dotenv_file(path: Path) -> None:
    for line in _read_text(path).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if not key:
            continue
        existing = os.environ.get(key, "")
        if key.startswith("MYKNOWLEDGE_") and val:
            os.environ[key] = val
        elif key not in os.environ or not str(existing).strip():
            os.environ[key] = val


def load_dotenv() -> None:
    for path in _dotenv_paths():
        if path.is_file():
            _apply_dotenv_file(path)


def llm_config() -> dict[str, str | float]:
    load_dotenv()
    key = (
        os.environ.get("MYKNOWLEDGE_LLM_API_KEY")
        or os.environ.get("LLM_API_KEY")
        or os.environ.get("DEEPSEEK_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or ""
    ).strip()
    base = (
        os.environ.get("MYKNOWLEDGE_LLM_API_BASE")
        or os.environ.get("LLM_BASE_URL")
        or os.environ.get("DEEPSEEK_API_BASE")
        or os.environ.get("OPENAI_API_BASE")
        or ""
    ).strip().rstrip("/")
    model = (
        os.environ.get("MYKNOWLEDGE_LLM_MODEL")
        or os.environ.get("LLM_MODEL")
        or os.environ.get("DEEPSEEK_MODEL")
        or os.environ.get("OPENAI_MODEL")
        or ""
    ).strip()
    if base.endswith("/v1"):
        chat_url = f"{base}/chat/completions"
    else:
        chat_url = f"{base}/v1/chat/completions"
    return {"api_key": key, "chat_url": chat_url, "model": model}


def rag_top_k(kind: str = "ask") -> int:
    """Default RAG snippet count for ask / produce."""
    load_dotenv()
    env_key = "MYKNOWLEDGE_RAG_TOP_ASK" if kind == "ask" else "MYKNOWLEDGE_RAG_TOP_PRODUCE"
    default = 6 if kind == "ask" else 8
    try:
        return max(1, min(20, int(os.environ.get(env_key, str(default)))))
    except ValueError:
        return default


def rag_mode() -> str:
    """keyword | vector | hybrid | external"""
    load_dotenv()
    raw = os.environ.get("MYKNOWLEDGE_RAG_MODE", "hybrid").strip().lower()
    if raw in ("keyword", "vector", "hybrid", "external"):
        return raw
    return "hybrid"


def rag_hybrid_use_max() -> bool:
    """Hybrid merge: max(keyword, vector) per chunk (DocuBrowser-style) vs weighted sum."""
    load_dotenv()
    return os.environ.get("MYKNOWLEDGE_RAG_HYBRID_MAX", "0").strip().lower() in ("1", "true", "yes")


def rag_hybrid_weights() -> tuple[float, float]:
    """(keyword_weight, vector_weight) normalized."""
    load_dotenv()
    try:
        kw = float(os.environ.get("MYKNOWLEDGE_RAG_HYBRID_KEYWORD", "0.35"))
    except ValueError:
        kw = 0.35
    try:
        vec = float(os.environ.get("MYKNOWLEDGE_RAG_HYBRID_VECTOR", "0.65"))
    except ValueError:
        vec = 0.65
    total = kw + vec
    if total <= 0:
        return 0.35, 0.65
    return kw / total, vec / total


def rag_chunk_params() -> tuple[int, int]:
    load_dotenv()
    try:
        size = int(os.environ.get("MYKNOWLEDGE_RAG_CHUNK_SIZE", "520"))
    except ValueError:
        size = 520
    try:
        overlap = int(os.environ.get("MYKNOWLEDGE_RAG_CHUNK_OVERLAP", "80"))
    except ValueError:
        overlap = 80
    return max(200, min(2000, size)), max(0, min(400, overlap))


def rag_parent_child_enabled() -> bool:
    load_dotenv()
    raw = os.environ.get("MYKNOWLEDGE_RAG_PARENT_CHILD", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def rag_child_chunk_size() -> int:
    load_dotenv()
    parent, _ = rag_chunk_params()
    try:
        child = int(os.environ.get("MYKNOWLEDGE_RAG_CHILD_SIZE", str(max(200, parent // 2))))
    except ValueError:
        child = max(200, parent // 2)
    return max(120, min(parent, child))


def rag_conflict_prompt_enabled() -> bool:
    load_dotenv()
    raw = os.environ.get("MYKNOWLEDGE_RAG_CONFLICT_PROMPT", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def rag_hyde_enabled() -> bool:
    load_dotenv()
    raw = os.environ.get("MYKNOWLEDGE_RAG_HYDE", "0").strip().lower()
    return raw in ("1", "true", "yes")


def contrarian_enabled() -> bool:
    """When on, ingest writes assumptions; contradiction scan is available in UI."""
    load_dotenv()
    raw = os.environ.get("MYKNOWLEDGE_CONTRARIAN", "0").strip().lower()
    return raw in ("1", "true", "yes")


def rag_fts5_enabled() -> bool:
    load_dotenv()
    raw = os.environ.get("MYKNOWLEDGE_FTS5", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def rag_use_rrf() -> bool:
    load_dotenv()
    raw = os.environ.get("MYKNOWLEDGE_RAG_RRF", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def rag_rrf_k() -> int:
    load_dotenv()
    try:
        return max(1, int(os.environ.get("MYKNOWLEDGE_RAG_RRF_K", "60")))
    except ValueError:
        return 60


def rag_coarse_k() -> int:
    load_dotenv()
    try:
        return max(5, min(50, int(os.environ.get("MYKNOWLEDGE_RAG_COARSE_K", "20"))))
    except ValueError:
        return 20


def rag_contextual_enabled() -> bool:
    load_dotenv()
    raw = os.environ.get("MYKNOWLEDGE_RAG_CONTEXTUAL", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def rag_rerank_config() -> dict[str, str | bool]:
    load_dotenv()
    embed = rag_embedding_config()
    model = os.environ.get("MYKNOWLEDGE_RERANK_MODEL", "bge-reranker-v2-m3").strip()
    url = os.environ.get("MYKNOWLEDGE_RERANK_URL", "").strip().rstrip("/")
    if not url and embed.get("api_base"):
        url = str(embed["api_base"]).strip().rstrip("/")
    flag = os.environ.get("MYKNOWLEDGE_RERANK", "").strip().lower()
    if flag in ("0", "false", "no", "off"):
        enabled = False
    elif flag in ("1", "true", "yes"):
        enabled = bool(url)
    else:
        enabled = bool(url and embed.get("api_key"))
    key = (
        os.environ.get("MYKNOWLEDGE_RERANK_API_KEY")
        or os.environ.get("MYKNOWLEDGE_EMBEDDING_API_KEY")
        or os.environ.get("MYKNOWLEDGE_LLM_API_KEY")
        or str(embed.get("api_key") or "")
    ).strip()
    return {"enabled": enabled and bool(url and key), "url": url, "model": model, "api_key": key}


def rag_graph_expand_enabled() -> bool:
    load_dotenv()
    raw = os.environ.get("MYKNOWLEDGE_GRAPH_EXPAND", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def rag_graph_max_hops() -> int:
    load_dotenv()
    try:
        return max(0, min(3, int(os.environ.get("MYKNOWLEDGE_GRAPH_MAX_HOPS", "2"))))
    except ValueError:
        return 2


def rag_agent_enabled() -> bool:
    load_dotenv()
    raw = os.environ.get("MYKNOWLEDGE_RAG_AGENT", "0").strip().lower()
    return raw in ("1", "true", "yes")


def rag_agent_score_threshold() -> float:
    load_dotenv()
    try:
        return float(os.environ.get("MYKNOWLEDGE_RAG_AGENT_MIN_SCORE", "0.08"))
    except ValueError:
        return 0.08


def rag_embedding_config() -> dict[str, str | bool]:
    load_dotenv()
    llm = llm_config()
    mode = rag_mode()
    enabled = mode in ("vector", "hybrid")
    base = (
        os.environ.get("MYKNOWLEDGE_EMBEDDING_API_BASE")
        or os.environ.get("MYKNOWLEDGE_LLM_API_BASE")
        or str(llm.get("chat_url", "")).replace("/chat/completions", "")
        or ""
    ).strip().rstrip("/")
    if base.endswith("/chat/completions"):
        base = base[: -len("/chat/completions")]
    key = (
        os.environ.get("MYKNOWLEDGE_EMBEDDING_API_KEY")
        or os.environ.get("MYKNOWLEDGE_LLM_API_KEY")
        or str(llm.get("api_key") or "")
    ).strip()
    model = os.environ.get("MYKNOWLEDGE_EMBEDDING_MODEL", "text-embedding-3-small").strip()
    return {
        "enabled": enabled,
        "api_base": base,
        "api_key": key,
        "model": model,
    }


def anythingllm_config() -> dict[str, str | float | bool]:
    load_dotenv()
    url = os.environ.get("MYKNOWLEDGE_ANYTHINGLLM_URL", "").strip().rstrip("/")
    key = os.environ.get("MYKNOWLEDGE_ANYTHINGLLM_API_KEY", "").strip()
    workspace = os.environ.get("MYKNOWLEDGE_ANYTHINGLLM_WORKSPACE", "").strip()
    augment = os.environ.get("MYKNOWLEDGE_ANYTHINGLLM_AUGMENT", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    chat_fallback = os.environ.get("MYKNOWLEDGE_ANYTHINGLLM_CHAT_FALLBACK", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    try:
        threshold = float(os.environ.get("MYKNOWLEDGE_ANYTHINGLLM_SCORE_THRESHOLD", "0.2"))
    except ValueError:
        threshold = 0.2
    enabled = bool(url and key and workspace)
    return {
        "enabled": enabled,
        "url": url,
        "api_key": key,
        "workspace": workspace,
        "augment": augment,
        "chat_fallback": chat_fallback,
        "score_threshold": threshold,
    }


def docubrowser_config() -> dict[str, str | int | bool]:
    load_dotenv()
    bundled = (ROOT / "third_party" / "DocuBrowser" / "docubrowser.py").is_file()
    raw_enabled = os.environ.get("MYKNOWLEDGE_DOCUBROWSER_ENABLED", "").strip().lower()
    if raw_enabled in ("0", "false", "no"):
        enabled = False
    elif raw_enabled in ("1", "true", "yes"):
        enabled = True
    else:
        enabled = bundled
    augment = os.environ.get("MYKNOWLEDGE_DOCUBROWSER_AUGMENT", "1").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    try:
        timeout = int(os.environ.get("MYKNOWLEDGE_DOCUBROWSER_TIMEOUT", "30"))
    except ValueError:
        timeout = 30
    try:
        port = int(os.environ.get("MYKNOWLEDGE_DOCUBROWSER_PORT", "18766"))
    except ValueError:
        port = 18766
    cli = os.environ.get("MYKNOWLEDGE_DOCUBROWSER_CLI", "auto").strip()
    url = os.environ.get("MYKNOWLEDGE_DOCUBROWSER_URL", f"http://127.0.0.1:{port}").strip().rstrip("/")
    return {
        "enabled": enabled,
        "augment": augment,
        "bundled": bundled,
        "url": url,
        "port": port,
        "cli": cli,
        "timeout": max(5, min(300, timeout)),
    }
