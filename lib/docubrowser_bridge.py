"""Bundled DocuBrowser integration for 易知 (GPL-3.0 sidecar, subprocess only)."""

from __future__ import annotations

import atexit
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .config import ROOT, docubrowser_config, load_dotenv, wiki_root

_server_proc: subprocess.Popen | None = None
_server_log = None
_start_lock = threading.Lock()
_managed_by_yizhi = False


@dataclass
class DocuBrowserHit:
    title: str
    path: str
    text: str
    score: float
    author: str = ""
    tags: list[str] | None = None


def bundled_root() -> Path | None:
    p = ROOT / "third_party" / "DocuBrowser"
    return p if (p / "docubrowser.py").is_file() else None


def bundled_available() -> bool:
    return bundled_root() is not None


def _work_dir(root: Path | None = None) -> Path:
    d = (root or wiki_root()) / ".docubrowser"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_file(root: Path | None = None) -> Path:
    return _work_dir(root) / "docubrowse.config"


def ensure_config(root: Path | None = None) -> Path:
    """Write docubrowse.config pointing at wiki assets and local DB."""
    root = root or wiki_root()
    cfg = docubrowser_config()
    work = _work_dir(root)
    assets = root / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    port = int(cfg.get("port") or 18766)
    db_path = work / "du-docs.db"
    text = (
        "# 易知内置 DocuBrowser 配置（自动生成）\n"
        f"doc_dir  = {assets}\n"
        f"db_path  = {db_path}\n"
        f"port     = {port}\n"
        f"work_dir = {work}\n"
    )
    path = config_file(root)
    if not path.is_file() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")
    return path


def docubrowser_enabled() -> bool:
    cfg = docubrowser_config()
    return bool(cfg.get("enabled"))


def docubrowser_augment_enabled() -> bool:
    cfg = docubrowser_config()
    return bool(cfg.get("enabled") and cfg.get("augment"))


def _resolve_cli() -> str:
    cfg = docubrowser_config()
    cli = str(cfg.get("cli") or "").strip()
    if cli and cli.lower() not in ("docubrowser", "auto", "bundled"):
        return cli
    bundled = bundled_root()
    if bundled:
        return str(bundled / "docubrowser.py")
    return cli or "docubrowser"


def _http_get(path: str, params: dict | None = None, timeout: int | None = None) -> dict:
    cfg = docubrowser_config()
    base = str(cfg.get("url") or "http://127.0.0.1:18766").rstrip("/")
    t = timeout if timeout is not None else int(cfg.get("timeout") or 30)
    q = urllib.parse.urlencode(params or {})
    url = f"{base}{path}" + (f"?{q}" if q else "")
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    with urllib.request.urlopen(req, timeout=t) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}


def service_reachable() -> bool:
    try:
        _http_get("/api/stats", timeout=3)
        return True
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return False


def cli_available() -> bool:
    cli = _resolve_cli()
    if cli.lower().endswith(".py"):
        return Path(cli).is_file()
    return shutil.which(cli) is not None


def _cli_cmd(extra: list[str], root: Path | None = None) -> list[str]:
    cli = _resolve_cli()
    cfg_path = ensure_config(root)
    if cli.lower().endswith(".py"):
        cmd = [sys.executable, cli, "--config", str(cfg_path), *extra]
    else:
        cmd = [cli, "--config", str(cfg_path), *extra]
    return cmd


def _ensure_db(db_path: Path) -> None:
    bundled = bundled_root()
    if not bundled:
        return
    if db_path.is_file():
        return
    sys.path.insert(0, str(bundled))
    try:
        from docubrowse_db import ensure_db  # type: ignore

        ensure_db(str(db_path))
    finally:
        if str(bundled) in sys.path:
            sys.path.remove(str(bundled))


def start_service(root: Path | None = None, *, wait: bool = True) -> bool:
    """Start bundled doc_search.py (keyword search works without Ollama)."""
    global _server_proc, _server_log, _managed_by_yizhi

    if not docubrowser_enabled():
        return False
    if not bundled_available():
        return False

    with _start_lock:
        if service_reachable():
            return True
        if _server_proc and _server_proc.poll() is None:
            return True

        root = root or wiki_root()
        ensure_config(root)
        cfg = docubrowser_config()
        bundled = bundled_root()
        assert bundled is not None

        work = _work_dir(root)
        db_path = work / "du-docs.db"
        port = int(cfg.get("port") or 18766)
        _ensure_db(db_path)

        log_path = work / "docubrowser-server.log"
        _server_log = open(log_path, "a", encoding="utf-8")  # noqa: SIM115
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]

        _server_proc = subprocess.Popen(
            [sys.executable, str(bundled / "doc_search.py"), str(db_path), str(port)],
            cwd=str(bundled),
            stdout=_server_log,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )
        _managed_by_yizhi = True

        if not wait:
            return True

        for _ in range(20):
            time.sleep(0.25)
            if service_reachable():
                return True
            if _server_proc.poll() is not None:
                break
        return service_reachable()


def stop_service() -> None:
    global _server_proc, _server_log, _managed_by_yizhi

    proc = _server_proc
    _server_proc = None
    _managed_by_yizhi = False
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            try:
                proc.kill()
            except OSError:
                pass
    if _server_log:
        try:
            _server_log.close()
        except OSError:
            pass
        _server_log = None


def ensure_service(root: Path | None = None) -> bool:
    if not docubrowser_enabled():
        return False
    if service_reachable():
        return True
    return start_service(root)


def setup_bundled() -> bool:
    """Clone/install DocuBrowser into third_party if missing."""
    if bundled_available():
        return True
    script = ROOT / "scripts" / "setup_docubrowser.py"
    if not script.is_file():
        return False
    try:
        subprocess.run(
            [sys.executable, str(script)],
            cwd=str(ROOT),
            timeout=600,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return bundled_available()


def bootstrap(root: Path | None = None) -> dict:
    """Called on 易知 startup: install if needed, write config, start server."""
    load_dotenv()
    if not docubrowser_enabled():
        return {"enabled": False, "reason": "disabled"}

    ok_setup = setup_bundled()
    if not ok_setup:
        return {"enabled": True, "bundled": False, "reason": "setup_failed"}

    ensure_config(root)
    started = start_service(root)
    st = status()
    st["bootstrap_started"] = started
    return st


def status() -> dict:
    load_dotenv()
    cfg = docubrowser_config()
    bundled = bundled_root()
    out = {
        "enabled": bool(cfg.get("enabled")),
        "augment": bool(cfg.get("augment")),
        "bundled": bundled is not None,
        "bundled_path": str(bundled) if bundled else "",
        "config_path": str(config_file()),
        "url": cfg.get("url") or "",
        "port": cfg.get("port"),
        "cli": _resolve_cli(),
        "service_up": False,
        "cli_ok": cli_available(),
        "managed_by_yizhi": _managed_by_yizhi,
        "stats": {},
    }
    if service_reachable():
        out["service_up"] = True
        try:
            out["stats"] = _http_get("/api/stats", timeout=5)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
            out["stats"] = {}
    return out


def search_documents(query: str, top_k: int = 8, mode: str = "both") -> list[DocuBrowserHit]:
    if not query.strip():
        return []
    if not ensure_service():
        return []
    try:
        data = _http_get(
            "/api/search",
            {"q": query, "mode": mode, "offset": "0"},
            timeout=int(docubrowser_config().get("timeout") or 30),
        )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return []

    docs = data.get("documents") or []
    out: list[DocuBrowserHit] = []
    for item in docs[: max(1, min(50, top_k))]:
        if not isinstance(item, dict):
            continue
        text = str(item.get("description") or item.get("content_snippet") or item.get("subject") or "").strip()
        title = str(item.get("title") or item.get("name") or Path(str(item.get("path") or "")).stem or "文档")
        path = str(item.get("path") or "")
        if not text and path:
            text = f"{title} ({path})"
        score = float(item.get("score") or 0.0)
        tags_raw = item.get("tags") or []
        tags = [str(t) for t in tags_raw] if isinstance(tags_raw, list) else []
        out.append(
            DocuBrowserHit(
                title=title,
                path=path,
                text=text,
                score=score,
                author=str(item.get("author") or ""),
                tags=tags,
            )
        )
    return out


_rescan_lock = threading.Lock()
_rescan_scheduled = False


def auto_rescan_enabled() -> bool:
    load_dotenv()
    if not docubrowser_augment_enabled():
        return False
    raw = os.environ.get("MYKNOWLEDGE_DOCUBROWSER_AUTO_RESCAN", "1").strip().lower()
    return raw not in ("0", "false", "no")


def maybe_defer_rescan(root: Path | None = None, *, no_embed: bool | None = None) -> None:
    """Background index assets/ for RAG augment; coalesced, silent on failure."""
    if not auto_rescan_enabled():
        return
    if no_embed is None:
        no_embed = os.environ.get("MYKNOWLEDGE_DOCUBROWSER_RESCAN_EMBED", "0").strip().lower() not in (
            "1",
            "true",
            "yes",
        )

    global _rescan_scheduled
    with _rescan_lock:
        if _rescan_scheduled:
            return
        _rescan_scheduled = True
    root = root or wiki_root()

    def job() -> None:
        global _rescan_scheduled
        try:
            ensure_config(root)
            ensure_service(root)
            rescan_wiki_assets(root, no_embed=no_embed)
        except Exception:
            pass
        finally:
            with _rescan_lock:
                _rescan_scheduled = False

    threading.Thread(target=job, daemon=True, name="docubrowser-rescan").start()


def rescan_wiki_assets(root: Path | None = None, *, no_embed: bool = False) -> dict:
    if not docubrowser_enabled():
        raise RuntimeError("DocuBrowser 未启用")
    if not ensure_service(root):
        if not cli_available():
            raise RuntimeError("内置 DocuBrowser 未安装，请重启易知或运行 python scripts/setup_docubrowser.py")
        raise RuntimeError("DocuBrowser 服务未能启动")

    root = root or wiki_root()
    assets = root / "assets"
    if not assets.is_dir():
        raise RuntimeError(f"资料目录不存在: {assets}")

    args = ["rescan", "--doc-dir", str(assets)]
    if no_embed:
        args.append("--no-embed")

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env.setdefault("DOCUBROWSER_NONINTERACTIVE", "1")

    try:
        proc = subprocess.run(
            _cli_cmd(args, root),
            capture_output=True,
            text=True,
            timeout=7200,
            encoding="utf-8",
            errors="replace",
            env=env,
            cwd=str(bundled_root() or ROOT),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("DocuBrowser 扫描超时（>2h）") from exc

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        if "ollama" in err.lower() or "Ollama" in err:
            raise RuntimeError(
                "DocuBrowser 扫描需要 Ollama（语义索引）。可先安装 Ollama 并拉取 nomic-embed-text，"
                "或使用 rescan --no-embed 仅关键词索引。"
            )
        raise RuntimeError(f"DocuBrowser 扫描失败: {err[:500]}")

    st = status()
    return {
        "ok": True,
        "assets_dir": str(assets),
        "stdout_tail": (proc.stdout or "")[-800:],
        "stats": st.get("stats") or {},
    }


def open_ui() -> str:
    cfg = docubrowser_config()
    ensure_service()
    return str(cfg.get("url") or "http://127.0.0.1:18766").rstrip("/") + "/"


atexit.register(stop_service)
