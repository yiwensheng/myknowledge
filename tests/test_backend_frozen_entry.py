"""Frozen backend entry smoke tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_frozen_main_exports_run():
    from backend.__frozen_main__ import run_backend

    assert callable(run_backend)


def test_frozen_main_resolves_app_import():
    from backend.__frozen_main__ import get_asgi_app

    app = get_asgi_app()
    assert app is not None
    assert hasattr(app, "router") or callable(app)
