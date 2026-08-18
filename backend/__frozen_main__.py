"""Entry for PyInstaller / Nuitka frozen backend (same behavior as `python -m backend`).

When DocuBrowser (or other sidecars) spawn ``yizhi-backend.exe script.py ...``,
``sys.executable`` is this frozen binary. We must run the script, not start a
second FastAPI instance — otherwise install-time startup hangs and storms.
"""

from __future__ import annotations

import os
import runpy
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path


def _boot_log(msg: str) -> None:
    try:
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        log_dir = Path(local) / "Yizhi"
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "frozen-boot.log").open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} {msg}\n")
    except Exception:
        pass


def _ensure_stdio() -> None:
    """runw / windowsHide 可能留下 stdout/stderr=None；uvicorn ColourizedFormatter 会崩。"""
    if sys.stdout is not None and sys.stderr is not None:
        return
    sink = None
    try:
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        log_dir = Path(local) / "Yizhi"
        log_dir.mkdir(parents=True, exist_ok=True)
        sink = open(log_dir / "backend-console.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
    except Exception:
        try:
            sink = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
        except Exception:
            import io

            sink = io.StringIO()
    if sys.stdout is None:
        sys.stdout = sink
    if sys.stderr is None:
        sys.stderr = sink


# 尽早修补：避免 import uvicorn 路径上已有空 stdio
_ensure_stdio()


def get_asgi_app():
    from backend.server import app

    return app


def run_backend() -> None:
    """Start uvicorn via the same path as backend.server.main()."""
    _ensure_stdio()
    from backend.server import main

    main()


def _looks_like_script(arg: str) -> bool:
    a = (arg or "").strip().replace("\\", "/")
    if not a:
        return False
    lower = a.lower()
    return lower.endswith(".py") or lower.endswith(".pyw")


def _run_sidecar_script(script: str, script_argv: list[str]) -> None:
    path = Path(script).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"sidecar script not found: {script}")
    # Match ``python script.py a b``: script dir must be on sys.path for sibling imports
    # (e.g. DocuBrowser doc_search.py → docubrowse_db). run_path under frozen often omits it.
    script_dir = str(path.parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    sys.argv = [str(path), *script_argv]
    _boot_log(f"frozen sidecar run_path={path} argv={sys.argv!r} path0={script_dir}")
    runpy.run_path(str(path), run_name="__main__")


def main() -> None:
    _ensure_stdio()
    _boot_log(f"frozen main start argv={sys.argv!r} frozen={getattr(sys, 'frozen', False)}")
    try:
        args = sys.argv[1:]
        if args and _looks_like_script(args[0]):
            _run_sidecar_script(args[0], args[1:])
            return
        run_backend()
    except Exception:
        _boot_log("FATAL:\n" + traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
