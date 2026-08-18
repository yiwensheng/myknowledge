"""FastAPI backend for Myknowledge Electron GUI."""

from __future__ import annotations

import json
import mimetypes
import shutil
import stat
import sys
import tempfile
import threading
import urllib.error
from pathlib import Path

if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

import anyio  # noqa: E402
from starlette.responses import Response  # noqa: E402
from starlette.staticfiles import StaticFiles as StarletteStaticFiles  # noqa: E402

# 须与 lib.config.ROOT 一致（冻结后端 ≠ __file__ 上级，否则预览/静态资源找不到）
from lib.config import ROOT as _ROOT  # noqa: E402

_ELECTRON_RENDERER = _ROOT / "electron" / "renderer"
_FILE_VIEWER_VENDOR = _ELECTRON_RENDERER / "vendor" / "file-viewer"

# Windows 默认把 .mjs 识别成 text/plain，PDF.js worker 动态 import 会失败
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("text/javascript", ".cjs")
mimetypes.add_type("application/wasm", ".wasm")


class FileViewerStaticFiles(StarletteStaticFiles):
    """Serve File-Viewer assets with JS/WASM MIME types required by workers."""

    _JS_WASM_SUFFIXES = (".mjs", ".cjs", ".js", ".wasm")

    @staticmethod
    def _force_js_wasm_mime(path: str) -> str | None:
        lower = path.lower()
        if lower.endswith((".mjs", ".cjs", ".js")):
            return "text/javascript; charset=utf-8"
        if lower.endswith(".wasm"):
            return "application/wasm"
        return None

    def file_response(self, full_path, stat_result, scope, status_code: int = 200):
        response = super().file_response(full_path, stat_result, scope, status_code)
        media = self._force_js_wasm_mime(str(full_path).lower())
        if media:
            response.headers["content-type"] = media
        return response

    async def get_response(self, path: str, scope):
        lower = path.lower()
        if lower.endswith(self._JS_WASM_SUFFIXES):
            try:
                full_path, stat_result = await anyio.to_thread.run_sync(self.lookup_path, path)
            except OSError:
                return await super().get_response(path, scope)
            if stat_result and stat.S_ISREG(stat_result.st_mode):
                media = self._force_js_wasm_mime(lower)
                headers = {
                    "Accept-Ranges": "none",
                    "Cache-Control": "public, max-age=86400",
                }
                if scope["method"] == "HEAD":
                    return Response(
                        status_code=200,
                        headers={**headers, "content-type": media, "content-length": str(stat_result.st_size)},
                    )
                content = await anyio.to_thread.run_sync(Path(full_path).read_bytes)
                return Response(content=content, media_type=media, headers=headers)
        response = await super().get_response(path, scope)
        media = self._force_js_wasm_mime(lower)
        if media:
            response.headers["content-type"] = media
        return response

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastapi import FastAPI, File, HTTPException, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse  # noqa: E402
from typing import Any  # noqa: E402

from pydantic import BaseModel  # noqa: E402

from lib.assets import delete_asset, list_assets, list_assets_page, rename_asset  # noqa: E402
from lib.config import extra_dirs, load_dotenv, output_dir, wiki_root  # noqa: E402
from lib.ingest import ingest_file, ingest_inbox_bulk, sync_all  # noqa: E402
from lib.docubrowser_bridge import (  # noqa: E402
    bootstrap as docubrowser_bootstrap,
    maybe_defer_rescan,
    open_ui,
    rescan_wiki_assets,
    status as docubrowser_status,
    stop_service as docubrowser_stop,
)
from lib.upload_jobs import enqueue_upload_job, get_job, list_active_jobs  # noqa: E402
from lib.index_jobs import (  # noqa: E402
    get_job as get_index_job,
    list_active_jobs as list_index_jobs,
    start_index_job,
)
from lib.url_jobs import (  # noqa: E402
    get_job as get_url_ingest_job,
    list_active_jobs as list_url_ingest_jobs,
    start_url_ingest_job,
)
from lib.text_ingest import ingest_text  # noqa: E402
from lib.llm import ask, ask_stream, produce, produce_stream, produce_revise, produce_revise_stream, finalize_produce  # noqa: E402
from lib.produce_export import markdown_to_docx_bytes  # noqa: E402
from lib.loop_engine import ensure_loop_scaffold, loop_status, run_loop  # noqa: E402
from lib.memory import (  # noqa: E402
    delete_qa_entry,
    delete_session,
    get_continuity,
    get_evolution,
    get_qa_entry,
    get_session_detail,
    list_audit,
    list_qa_history,
    list_sessions,
    maybe_summarize_session,
    memory_stats,
    new_session_id,
    update_qa_entry_question,
    update_session_meta,
)
from lib.skills import discover_skills, get_skill, load_skill_content, match_skill, run_skill  # noqa: E402
from lib.workflows import (  # noqa: E402
    add_custom_workflow,
    list_all_workflows,
    remove_custom_workflow,
    run_workflow,
)
from lib.rag import search  # noqa: E402
from lib.watcher import WikiWatcher  # noqa: E402
from lib.linked_dir_jobs import (  # noqa: E402
    get_job as get_linked_dir_index_job,
    list_active_jobs as list_linked_dir_index_jobs,
    start_linked_dir_index,
)
from lib.linked_dir_watcher import LinkedDirWatcher  # noqa: E402
from lib.linked_dirs import (  # noqa: E402
    add_linked_dir,
    list_linked_dirs,
    remove_linked_dir,
    set_linked_dir_enabled,
    set_linked_dir_folder_ids,
)
from lib.folders import (  # noqa: E402
    create_folder,
    delete_folder,
    ensure_default_folders,
    list_folders,
    merge_scope_with_folders,
    update_folder,
)
from lib.pick_directory import pick_directory as pick_directory_native  # noqa: E402
from lib.wiki import delete_page, list_pages, read_page, save_page, search_keyword  # noqa: E402
from lib.license_service import (  # noqa: E402
    activate_remote,
    check_license,
    create_order,
    fetch_plans,
    get_device_id,
    license_config,
    poll_order,
    self_unbind_remote,
    try_heartbeat,
)
from lib.writing_style import (  # noqa: E402
    get_style_profile,
    refresh_style_profile,
    style_enabled,
)
from lib.persona_config import (  # noqa: E402
    GENDER_OPTIONS,
    TONE_LABELS,
    PREFERENCE_LABELS,
    apply_preset,
    avatar_file_path,
    list_presets,
    load_persona_config,
    render_persona,
    render_persona_preview,
    reset_persona_config,
    save_persona_config,
)
from lib.settings import get_settings_payload, save_settings  # noqa: E402
from lib.memos import (  # noqa: E402
    collect_memo_tags,
    create_memo,
    list_memo_pages,
    memo_to_dict,
    update_memo,
)
from lib.memo_sync import schedule_memo_rag_refresh  # noqa: E402

load_dotenv()
app = FastAPI(title="易知 API", version="2.5.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def allow_private_network_access(request, call_next):
    """Electron loads UI via file:// then fetch() to 127.0.0.1 — Chromium Private
    Network Access sends OPTIONS with Access-Control-Request-Private-Network.
    Without Allow-Private-Network on the response, POST streams fail as
    TypeError: Failed to fetch (GET may still work).
    """
    response = await call_next(request)
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


_watcher = WikiWatcher()
_linked_watcher = LinkedDirWatcher()

_LICENSE_EXEMPT = (
    "/api/health",
    "/api/license/status",
    "/api/license/plans",
    "/api/license/device-id",
    "/api/license/create-order",
    "/api/license/order/",
    "/api/license/activate",
    "/api/license/heartbeat",
    "/api/license/mock-pay",
    "/api/license/self-unbind",
    "/api/style/profile",
    "/api/style/refresh",
    "/api/persona",
    "/api/capabilities",
    "/api/capabilities/setup-tools",
    "/api/update/check",
    "/api/commercial/links",
    "/api/settings",
    "/api/wiki/reset",
    "/api/memos",
    "/api/linked-dirs",
    "/api/url",
    "/api/workflows",
    "/api/upload/jobs",
    "/api/feedback",
)


def _license_exempt(path: str) -> bool:
    return any(path.startswith(p) for p in _LICENSE_EXEMPT)


_license_cache: dict[str, object] = {"ts": 0.0, "status": None}
_LICENSE_CACHE_TTL = 60.0


def _cached_license_status() -> dict:
    import time

    now = time.time()
    cached = _license_cache.get("status")
    if cached and now - float(_license_cache.get("ts") or 0) < _LICENSE_CACHE_TTL:
        return cached  # type: ignore[return-value]
    status = check_license()
    _license_cache["ts"] = now
    _license_cache["status"] = status
    return status


@app.middleware("http")
async def license_gate_middleware(request, call_next):
    path = request.url.path
    if path.startswith("/api/") and not _license_exempt(path):
        status = _cached_license_status()
        if not status.get("licensed"):
            return JSONResponse(
                status_code=402,
                content={"detail": status.get("reason", "no_license"), "license": status},
            )
    return await call_next(request)


class PageCreate(BaseModel):
    type: str = "note"
    title: str
    body: str = ""
    tags: list[str] = []
    status: str = "draft"
    links: list[str] = []
    folder_ids: list[str] = []


class PageUpdate(BaseModel):
    type: str | None = None
    title: str | None = None
    body: str | None = None
    tags: list[str] | None = None
    status: str | None = None
    links: list[str] | None = None
    folder_ids: list[str] | None = None


class AskBody(BaseModel):
    question: str
    top_k: int = 0  # 0 = 使用 .env MYKNOWLEDGE_RAG_TOP_ASK（默认 6）
    session_id: str = ""
    remember: bool | None = None
    auto_archive: bool | None = None
    scope_paths: list[str] = []
    folder_ids: list[str] = []


class ProduceBody(BaseModel):
    topic: str
    top_k: int = 0  # 0 = 按体例默认或 .env MYKNOWLEDGE_RAG_TOP_PRODUCE
    save: bool = True
    save_to_wiki: bool = False  # 默认不定稿；由 /api/produce/finalize 写入
    genre: str = "article"
    brief: str = ""
    first_principles_review: bool = False  # 默认关；启用则注入第一性原理+对抗式审查
    scope_paths: list[str] = []
    folder_ids: list[str] = []


class ProduceReviseBody(BaseModel):
    content: str
    instruction: str
    topic: str = ""
    genre: str = "article"
    brief: str = ""
    use_rag: bool = False
    first_principles_review: bool = False
    top_k: int = 0
    scope_paths: list[str] = []
    folder_ids: list[str] = []


class ProduceFinalizeBody(BaseModel):
    content: str
    topic: str
    genre: str = "article"
    title: str = ""
    tags: list[str] = []
    wiki_page: str = ""
    wiki_type: str = ""


class FeedbackSubmitBody(BaseModel):
    html: str
    subject: str = ""
    contact: str = ""


class DeduceBody(BaseModel):
    query: str
    top_k: int = 0
    scope_paths: list[str] = []
    folder_ids: list[str] = []


class DeduceExportBody(BaseModel):
    content: str
    title: str = "推演"
    graph_png: str = ""


class PodcastAudioBody(BaseModel):
    content: str
    title: str = "播客"


class YizhiPromoAudioBody(BaseModel):
    title: str = "易知宣传"
    rewrite: bool = True


class ProduceExportBody(BaseModel):
    content: str
    title: str = "产出"


class LoopRunBody(BaseModel):
    level: int | None = None
    dry_run: bool = False


class HistoryRenameBody(BaseModel):
    question: str


class LicenseCreateOrderBody(BaseModel):
    plan: str


class LicenseActivateBody(BaseModel):
    order_id: str = ""
    code: str = ""


class LicenseMockPayBody(BaseModel):
    order_id: str


class PersonaOwnerBody(BaseModel):
    real_name: str = ""
    gender: str = ""
    nickname: str = ""
    phone: str = ""
    email: str = ""
    wechat: str = ""
    avatar: str = ""
    organization: str = ""
    job_title: str = ""
    aliases: str = ""
    bio: str = ""


class PersonaBody(BaseModel):
    enabled: bool = False
    owner: PersonaOwnerBody = PersonaOwnerBody()
    preset: str = "curator"
    role_name: str = ""
    role_intro: str = ""
    audience: str = ""
    tones: list[str] = []
    domain: str = ""
    preferences: list[str] = []
    custom_notes: str = ""
    keep_grounded_rules: bool = True


class SettingsBody(BaseModel):
    values: dict[str, Any] = {}


class WikiResetBody(BaseModel):
    confirm: str = ""
    acknowledged: bool = False


class ServiceLoopPatchBody(BaseModel):
    dismissed_bar: bool | None = None
    scenario: str | None = None
    tasks: dict[str, Any] | None = None
    weeks: dict[str, Any] | None = None


class ServiceLoopTemplateRunBody(BaseModel):
    values: dict[str, Any] = {}


class ServiceLoopTemplateCommitBody(BaseModel):
    title: str = ""
    markdown: str = ""


class TTSPreviewBody(BaseModel):
    voice: str
    provider: str = ""
    text: str = ""


class MemoCreateBody(BaseModel):
    content: str
    folder_ids: list[str] = []


class MemoUpdateBody(BaseModel):
    content: str | None = None
    pinned: bool | None = None
    folder_ids: list[str] | None = None


class LinkedDirBody(BaseModel):
    path: str
    label: str = ""
    folder_ids: list[str] = []


class LinkedDirEnableBody(BaseModel):
    enabled: bool = True


class LinkedDirFoldersBody(BaseModel):
    folder_ids: list[str] = []


class FolderCreateBody(BaseModel):
    name: str


class FolderUpdateBody(BaseModel):
    name: str


class AssetFoldersBody(BaseModel):
    folder_ids: list[str] = []


class AssetRenameBody(BaseModel):
    filename: str


class OutputRuleBody(BaseModel):
    rule: str
    question: str = ""


class OutputRulePatchBody(BaseModel):
    text: str | None = None
    enabled: bool | None = None
    question: str | None = None


class SessionPatchBody(BaseModel):
    title: str | None = None
    summary: str | None = None


@app.on_event("startup")
async def _quiet_win_connection_reset_on_startup() -> None:
    """Suppress noisy ConnectionResetError when browsers abort audio range requests."""
    if sys.platform != "win32":
        return
    import asyncio

    loop = asyncio.get_running_loop()
    default = loop.get_exception_handler()

    def handler(loop: asyncio.AbstractEventLoop, context: dict) -> None:
        exc = context.get("exception")
        if isinstance(exc, ConnectionResetError):
            return
        if default:
            default(loop, context)
        else:
            loop.default_exception_handler(context)

    loop.set_exception_handler(handler)


@app.on_event("startup")
def startup() -> None:
    root = wiki_root()
    (root / "inbox").mkdir(exist_ok=True)
    (root / "assets").mkdir(exist_ok=True)
    ensure_loop_scaffold(root)
    try:
        from lib.distill import ensure_distill_skeleton

        ensure_distill_skeleton(root)
    except Exception:
        pass
    try:
        lic = check_license(force_online=False)
    except Exception:
        # 授权心跳/验签异常不得阻止后端启动（否则安装版整窗失败）
        lic = {"licensed": False}
    if lic.get("licensed"):
        _watcher.start()
        _linked_watcher.start()
    # DocuBrowser 子进程在冻结 exe 下可能较慢；勿阻塞 /api/health，否则 Electron 超时失败
    def _boot_docubrowser() -> None:
        try:
            docubrowser_bootstrap(root)
        except Exception:
            pass

    try:
        import threading

        threading.Thread(target=_boot_docubrowser, name="docubrowser-bootstrap", daemon=True).start()
    except Exception:
        _boot_docubrowser()
    try:
        from lib.feedback import start_feedback_flusher

        start_feedback_flusher()
    except Exception:
        pass


@app.on_event("shutdown")
def shutdown() -> None:
    _watcher.stop()
    _linked_watcher.stop()
    try:
        docubrowser_stop()
    except Exception:
        pass


@app.get("/api/update/check")
def api_update_check(app_version: str = ""):
    from lib.update_check import check_for_update

    return check_for_update(app_version)


@app.get("/api/commercial/links")
def api_commercial_links():
    from lib.commercial_links import commercial_links

    return commercial_links()


@app.get("/api/health")
def health(detail: int = 0):
    """Lightweight readiness probe (Electron polls this while splash is up).

    Heavy rag/license work must NOT run on the default path — otherwise each
    ~250ms poll blocks the worker for seconds and the GUI appears stuck after
    `QUIET_LAUNCH=false`.
    """
    body = {
        "ok": True,
        "wiki_root": str(wiki_root()),
        "version": "2.5.0",
        "capabilities": [
            "ask_stream",
            "memory",
            "skills",
            "loop",
            "url",
            "rag_hybrid",
            "rag_external",
            "docubrowser",
            "license",
            "file_viewer_local",
        ],
        "file_viewer": {
            "ready": _FILE_VIEWER_VENDOR.is_dir()
            and (_FILE_VIEWER_VENDOR / "flyfish-file-viewer-web-full.iife.js").is_file(),
            "vendor_path": str(_FILE_VIEWER_VENDOR),
        },
    }
    if detail:
        from lib.rag import rag_status

        body["rag"] = rag_status()
        body["license"] = check_license()
    return body


@app.get("/api/license/status")
def api_license_status():
    return check_license(force_online=False)


@app.get("/api/license/device-id")
def api_license_device_id():
    return {"device_id": get_device_id()}


@app.get("/api/license/plans")
def api_license_plans():
    try:
        return fetch_plans()
    except Exception as e:
        raise HTTPException(502, str(e)) from e


@app.post("/api/license/create-order")
def api_license_create_order(body: LicenseCreateOrderBody):
    if body.plan not in ("month", "year", "lifetime"):
        raise HTTPException(400, "plan must be month, year, or lifetime")
    try:
        return create_order(body.plan)
    except Exception as e:
        raise HTTPException(502, str(e)) from e


@app.get("/api/license/order/{order_id}")
def api_license_poll_order(order_id: str):
    try:
        return poll_order(order_id)
    except Exception as e:
        raise HTTPException(502, str(e)) from e


@app.post("/api/license/mock-pay")
def api_license_mock_pay(body: LicenseMockPayBody):
    """Dev helper when license server runs in mock pay mode."""
    cfg = license_config()
    server = str(cfg.get("server") or "")
    if not server:
        raise HTTPException(400, "license server not configured")
    import json as _json
    import urllib.request as _ur

    admin = __import__("os").environ.get("MYKNOWLEDGE_LICENSE_ADMIN_KEY", "dev-admin")
    req = _ur.Request(
        f"{server}/admin/mark-paid",
        data=_json.dumps({"admin_key": admin, "order_id": body.order_id}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with _ur.urlopen(req, timeout=15) as resp:
            return _json.loads(resp.read().decode())
    except Exception as e:
        raise HTTPException(502, str(e)) from e


def _invalidate_license_cache() -> None:
    _license_cache["ts"] = 0.0
    _license_cache["status"] = None


@app.post("/api/license/activate")
def api_license_activate(body: LicenseActivateBody):
    try:
        result = activate_remote(order_id=body.order_id, code=body.code)
        _invalidate_license_cache()
        if check_license().get("licensed"):
            _watcher.start()
        return result
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(502, str(e)) from e


@app.post("/api/license/heartbeat")
def api_license_heartbeat():
    ok = try_heartbeat()
    return {"ok": ok, **check_license(force_online=False)}


@app.post("/api/license/self-unbind")
def api_license_self_unbind():
    try:
        result = self_unbind_remote()
        _invalidate_license_cache()
        return result
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(502, str(e)) from e


@app.get("/api/style/profile")
def api_style_profile():
    if not style_enabled():
        return {"enabled": False, "profile": {}}
    profile = get_style_profile()
    return {
        "enabled": True,
        "sample_count": profile.get("sample_count", 0),
        "updated_at": profile.get("updated_at", ""),
        "heuristic_summary": profile.get("heuristic_summary", ""),
        "llm_summary": profile.get("llm_summary", ""),
        "sample_titles": profile.get("sample_titles", []),
    }


@app.post("/api/style/refresh")
def api_style_refresh():
    if not style_enabled():
        raise HTTPException(400, "writing style learning disabled")
    try:
        profile = refresh_style_profile(force=True, include_llm=True)
        return {"ok": True, "updated_at": profile.get("updated_at"), "sample_count": profile.get("sample_count")}
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.get("/api/persona")
def api_persona_get():
    cfg = load_persona_config()
    preview = render_persona_preview(cfg)
    return {
        "config": cfg,
        "presets": list_presets(),
        "gender_options": list(GENDER_OPTIONS),
        "tone_options": [{"id": k, "label": v} for k, v in TONE_LABELS.items()],
        "preference_options": [{"id": k, "label": v} for k, v in PREFERENCE_LABELS.items()],
        "rendered": preview,
        "using_custom": bool(cfg.get("enabled")),
        "has_owner_profile": bool((cfg.get("owner") or {}).get("real_name") or (cfg.get("owner") or {}).get("nickname")),
        "avatar_url": "/api/persona/avatar" if avatar_file_path() else "",
    }


@app.get("/api/persona/preset/{preset_id}")
def api_persona_preset(preset_id: str):
    return {"config": apply_preset(preset_id)}


@app.post("/api/persona/preview")
def api_persona_preview(body: PersonaBody):
    return {"rendered": render_persona_preview(body.model_dump())}


@app.put("/api/persona")
def api_persona_save(body: PersonaBody):
    cfg = save_persona_config(body.model_dump())
    preview = render_persona_preview(cfg)
    return {
        "ok": True,
        "config": cfg,
        "rendered": preview,
        "avatar_url": "/api/persona/avatar" if avatar_file_path() else "",
    }


@app.get("/api/persona/avatar")
def api_persona_avatar():
    path = avatar_file_path()
    if not path:
        raise HTTPException(404, detail="未设置头像")
    return FileResponse(path)


@app.post("/api/persona/avatar")
async def api_persona_avatar_upload(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, detail="请选择图片")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        raise HTTPException(400, detail="仅支持 jpg/png/webp/gif")
    data = await file.read()
    if len(data) > 2 * 1024 * 1024:
        raise HTTPException(400, detail="头像不能超过 2MB")
    cfg = load_persona_config()
    rel = ".config/owner-avatar.jpg"
    suffix = Path(file.filename).suffix.lower()
    if suffix in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        rel = f".config/owner-avatar{'.jpg' if suffix == '.jpeg' else suffix}"
    root = wiki_root()
    dest = root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    owner = dict(cfg.get("owner") or {})
    owner["avatar"] = rel.replace("\\", "/")
    cfg["owner"] = owner
    save_persona_config(cfg)
    return {"ok": True, "avatar": owner["avatar"], "avatar_url": "/api/persona/avatar"}


@app.post("/api/persona/reset")
def api_persona_reset():
    cfg = reset_persona_config()
    return {"ok": True, "config": cfg}


@app.get("/api/output-rules")
def api_output_rules_get():
    from lib.output_rules import get_rules_payload

    return get_rules_payload()


@app.post("/api/output-rules")
def api_output_rules_append(body: OutputRuleBody):
    from lib.output_rules import append_rule

    try:
        return append_rule(body.rule, question=body.question)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.patch("/api/output-rules/{rule_id}")
def api_output_rules_patch(rule_id: str, body: OutputRulePatchBody):
    from lib.output_rules import update_rule

    try:
        return update_rule(
            rule_id,
            text=body.text,
            enabled=body.enabled,
            question=body.question,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.delete("/api/output-rules/{rule_id}")
def api_output_rules_delete(rule_id: str):
    from lib.output_rules import delete_rule

    try:
        return delete_rule(rule_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/settings")
def api_settings_get():
    return get_settings_payload()


@app.put("/api/settings")
def api_settings_save(body: SettingsBody):
    from lib.rag import _invalidate_cache

    payload = save_settings(body.values or {})
    _invalidate_cache()
    return {"ok": True, **payload}


@app.get("/api/wiki/reset/preview")
def api_wiki_reset_preview():
    from lib.wiki_reset import preview_wiki_reset

    return preview_wiki_reset()


@app.post("/api/wiki/reset")
def api_wiki_reset(body: WikiResetBody):
    from lib.wiki_reset import reset_wiki_knowledge

    if not body.acknowledged:
        raise HTTPException(
            400,
            "请先勾选风险确认（已阅读免责并知悉外联外部文件不会被删除）。",
        )
    result = reset_wiki_knowledge(confirm=body.confirm or "")
    if not result.get("ok"):
        raise HTTPException(400, result.get("error") or "清空失败")
    return result


@app.post("/api/llm/probe")
def api_llm_probe():
    from lib.llm import probe_llm

    return probe_llm()


@app.get("/api/service-loop")
def api_service_loop_get():
    from lib.service_loop import get_status

    return get_status()


@app.patch("/api/service-loop")
def api_service_loop_patch(body: ServiceLoopPatchBody):
    from lib.service_loop import patch_state

    updates: dict[str, Any] = {}
    if body.dismissed_bar is not None:
        updates["dismissed_bar"] = body.dismissed_bar
    if body.scenario is not None:
        updates["scenario"] = body.scenario
    if body.tasks is not None:
        updates["tasks"] = body.tasks
    if body.weeks is not None:
        updates["weeks"] = body.weeks
    return patch_state(updates)


@app.get("/api/service-loop/assets")
def api_service_loop_assets():
    from lib.service_loop import collect_assets

    return collect_assets()


@app.get("/api/service-loop/templates")
def api_service_loop_templates():
    from lib.service_loop import list_templates

    return {"templates": list_templates()}


@app.post("/api/service-loop/templates/{template_id}/run")
def api_service_loop_template_run(template_id: str, body: ServiceLoopTemplateRunBody):
    from lib.service_loop import run_template

    result = run_template(template_id, body.values or {})
    if not result.get("ok"):
        raise HTTPException(400, result.get("error") or "生成失败")
    return result


@app.post("/api/service-loop/templates/{template_id}/commit")
def api_service_loop_template_commit(template_id: str, body: ServiceLoopTemplateCommitBody):
    from lib.service_loop import commit_template

    result = commit_template(
        template_id, title=body.title or "", markdown=body.markdown or ""
    )
    if not result.get("ok"):
        raise HTTPException(400, result.get("error") or "写入失败")
    return result


@app.get("/api/memos")
def api_memos_list(
    tag: str | None = None,
    date: str | None = None,
    flash_only: bool = True,
    page: int = 1,
    size: int = 50,
):
    from lib.memos import today_beijing_date
    from lib.paging import paginate

    day = (date or today_beijing_date()).strip()[:10]
    all_pages = list_memo_pages(tag=tag, date=day, flash_only=flash_only)
    tags = collect_memo_tags(list_memo_pages(flash_only=flash_only))
    data = [memo_to_dict(p) for p in all_pages]
    result = paginate(data, page, size, max_size=200)
    result["tags"] = tags
    result["date"] = day
    result["flash_only"] = flash_only
    result["total_for_day"] = len(all_pages)
    return result


@app.post("/api/memos")
def api_memos_create(body: MemoCreateBody):
    page = create_memo(body.content.strip(), folder_ids=body.folder_ids or [])
    schedule_memo_rag_refresh()
    return {**memo_to_dict(page), "indexing": True}


@app.patch("/api/memos")
def api_memos_update(path: str, body: MemoUpdateBody):
    try:
        page = update_memo(
            path,
            content=body.content,
            pinned=body.pinned,
            folder_ids=body.folder_ids,
        )
    except FileNotFoundError:
        raise HTTPException(404, "memo not found") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if body.content is not None:
        schedule_memo_rag_refresh()
    return {**memo_to_dict(page), "indexing": body.content is not None}


@app.get("/api/folders")
def api_folders_list():
    ensure_default_folders()
    return {"items": list_folders()}


@app.post("/api/folders")
def api_folders_create(body: FolderCreateBody):
    try:
        item = create_folder(body.name)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, "item": item, "items": list_folders()}


@app.patch("/api/folders")
def api_folders_update(id: str, body: FolderUpdateBody):
    try:
        item = update_folder(id, name=body.name)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, "item": item, "items": list_folders()}


@app.delete("/api/folders")
def api_folders_delete(id: str):
    try:
        delete_folder(id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    return {"ok": True, "items": list_folders()}


@app.get("/api/linked-dirs")
def api_linked_dirs_list():
    return list_linked_dirs()


@app.post("/api/pick-directory")
async def api_pick_directory():
    """Open native folder picker on the machine running the backend (local desktop)."""
    import asyncio

    path = await asyncio.to_thread(pick_directory_native, "选择外联文档目录")
    if not path:
        return {"ok": True, "canceled": True, "path": ""}
    return {"ok": True, "canceled": False, "path": path}


@app.post("/api/linked-dirs")
def api_linked_dirs_add(body: LinkedDirBody):
    try:
        payload = add_linked_dir(body.path, body.label, folder_ids=body.folder_ids or None)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except OSError as e:
        raise HTTPException(
            500,
            f"无法保存外联配置（请确认知识库目录可写）：{e}",
        ) from e
    try:
        _linked_watcher.refresh_fingerprints()
        _linked_watcher.start()
    except Exception:
        # 登记成功优先；监视器失败不阻断添加
        pass
    resolved = str(Path(body.path.strip()).expanduser().resolve())
    for item in payload.get("items") or []:
        if item.get("path") == resolved or Path(str(item.get("path") or "")).resolve() == Path(resolved):
            resolved = str(item.get("path") or resolved)
            break
    try:
        job_info = start_linked_dir_index([resolved])
    except Exception as e:
        return {
            "ok": True,
            **payload,
            "indexing": False,
            "index_error": f"外联已登记，但后台索引启动失败：{e}",
        }
    return {"ok": True, **payload, "indexing": True, **job_info}


@app.delete("/api/linked-dirs")
def api_linked_dirs_remove(path: str):
    payload = remove_linked_dir(path)
    _linked_watcher.refresh_fingerprints()
    sync_all()
    return {"ok": True, **payload}


@app.patch("/api/linked-dirs")
def api_linked_dirs_enable(path: str, body: LinkedDirEnableBody):
    payload = set_linked_dir_enabled(path, body.enabled)
    _linked_watcher.refresh_fingerprints()
    if body.enabled:
        _linked_watcher.start()
        job_info = start_linked_dir_index([path.strip()])
        return {"ok": True, **payload, "indexing": True, **job_info}
    sync_all()
    return {"ok": True, **payload}


@app.put("/api/linked-dirs/folders")
def api_linked_dirs_folders(path: str, body: LinkedDirFoldersBody):
    try:
        payload = set_linked_dir_folder_ids(path, body.folder_ids)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    return {"ok": True, **payload}


@app.post("/api/linked-dirs/reindex")
def api_linked_dirs_reindex():
    _linked_watcher.refresh_fingerprints()
    job_info = start_linked_dir_index()
    return {"ok": True, "indexing": True, **job_info}


@app.get("/api/linked-dirs/jobs/active")
def api_linked_dir_index_jobs_active():
    return {"jobs": list_linked_dir_index_jobs()}


@app.get("/api/linked-dirs/jobs/{job_id}")
def api_linked_dir_index_job(job_id: str):
    job = get_linked_dir_index_job(job_id)
    if not job:
        raise HTTPException(404, detail="任务不存在或已过期")
    return job


@app.get("/api/rag/status")
def api_rag_status():
    from lib.rag import rag_status

    return rag_status()


@app.get("/api/pages")
def api_list_pages(type: str | None = None, page: int = 1, size: int = 30):
    from lib.paging import paginate

    pages = list_pages(type_filter=type, include_inbox=False)
    data = [p.to_dict() for p in pages]
    return paginate(data, page, size, max_size=200)


@app.get("/api/pages/content")
def api_get_page(path: str):
    p = wiki_root() / path
    if not p.is_file():
        raise HTTPException(404, "page not found")
    page = read_page(p)
    return {**page.to_dict(), "body": page.body}


def _refresh_page_index_fast(page) -> None:
    """单篇保存后增量更新检索；勿用 sync_all（全库重建会卡死保存按钮）。"""
    from lib.ingest import defer_wiki_index_update
    from lib.rag import upsert_page_index

    try:
        upsert_page_index(page, embed_async=True)
    except Exception:
        pass
    try:
        defer_wiki_index_update()
    except Exception:
        pass


@app.post("/api/pages")
def api_create_page(body: PageCreate):
    page = save_page(
        page_type=body.type,
        title=body.title,
        body=body.body,
        tags=body.tags,
        status=body.status,
        links=body.links,
        extra_meta={"folder_ids": body.folder_ids or []} if body.folder_ids is not None else None,
    )
    _refresh_page_index_fast(page)
    return page.to_dict()


@app.put("/api/pages")
def api_update_page(path: str, body: PageUpdate):
    p = wiki_root() / path
    if not p.is_file():
        raise HTTPException(404, "page not found")
    old = read_page(p)
    extra = None
    if body.folder_ids is not None:
        from lib.folders import normalize_folder_ids

        extra = {"folder_ids": normalize_folder_ids(body.folder_ids)}
    page = save_page(
        page_type=body.type or old.type,
        title=body.title or old.title,
        body=body.body if body.body is not None else old.body,
        tags=body.tags if body.tags is not None else old.tags,
        status=body.status or old.status,
        links=body.links if body.links is not None else old.links,
        rel_path=path,
        asset_path=old.asset_path,
        asset_mime=old.asset_mime,
        extra_meta=extra,
    )
    _refresh_page_index_fast(page)
    return page.to_dict()


@app.delete("/api/pages")
def api_delete_page(path: str):
    norm = path.replace("\\", "/").strip().lstrip("/")
    if not delete_page(norm):
        raise HTTPException(404, f"page not found: {norm}")
    try:
        from lib.rag import remove_page_from_index

        remove_page_from_index(norm)
    except Exception:
        pass
    try:
        from lib.ingest import defer_wiki_index_update

        defer_wiki_index_update()
    except Exception:
        pass
    return {"deleted": norm}


@app.post("/api/ask")
def api_ask(body: AskBody):
    kwargs: dict = {
        "question": body.question,
        "session_id": body.session_id,
        "remember": body.remember,
        "auto_archive": body.auto_archive,
        "scope_paths": merge_scope_with_folders(body.scope_paths, body.folder_ids),
    }
    if body.top_k > 0:
        kwargs["top_k"] = body.top_k
    return ask(**kwargs)


@app.post("/api/ask/stream")
def api_ask_stream(body: AskBody):
    def event_gen():
        kwargs: dict = {
            "question": body.question,
            "session_id": body.session_id,
            "remember": body.remember,
            "auto_archive": body.auto_archive,
            "scope_paths": merge_scope_with_folders(body.scope_paths, body.folder_ids),
        }
        if body.top_k > 0:
            kwargs["top_k"] = body.top_k
        for ev in ask_stream(**kwargs):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/query")
def api_query(q: str = "", rag: bool = False, type: str | None = None, top: int = 15, page: int = 1, size: int = 0):
    from lib.paging import paginate

    page_size = size if size > 0 else top
    if rag:
        from lib.rag_agent import search_enhanced

        chunks = search_enhanced(q, top_k=max(page * page_size, page_size))
        data = [
            {
                "title": c.title,
                "path": c.rel_path,
                "score": c.score,
                "text": c.text,
                "asset_path": c.asset_path,
                "tags": c.tags,
            }
            for c in chunks
        ]
        return {"mode": "rag", **paginate(data, page, page_size, max_size=50)}
    pages = search_keyword(q, type_filter=type, limit=500)
    data = [p.to_dict() for p in pages]
    return {"mode": "keyword", **paginate(data, page, page_size, max_size=50)}


@app.get("/api/produce/genres")
def api_produce_genres():
    from lib.produce_genres import list_genres

    return {"genres": list_genres(), "default": "article"}


@app.post("/api/produce")
def api_produce(body: ProduceBody):
    kwargs: dict = {
        "topic": body.topic,
        "save_to_wiki": body.save_to_wiki,
        "genre": body.genre or "article",
        "brief": body.brief or "",
        "first_principles_review": bool(body.first_principles_review),
        "scope_paths": merge_scope_with_folders(body.scope_paths, body.folder_ids),
    }
    if body.top_k > 0:
        kwargs["top_k"] = body.top_k
    result = produce(**kwargs)
    if body.save and not body.save_to_wiki:
        out_root = output_dir()
        out_root.mkdir(parents=True, exist_ok=True)
        from lib.wiki import slugify, today_beijing

        out = out_root / f"{slugify(body.topic)}-{today_beijing()}.md"
        out.write_text(result["content"], encoding="utf-8")
        result["saved_to"] = str(out)
    return result


@app.post("/api/produce/stream")
def api_produce_stream(body: ProduceBody):
    def event_gen():
        kwargs: dict = {
            "topic": body.topic,
            "save_to_wiki": body.save_to_wiki,
            "genre": body.genre or "article",
            "brief": body.brief or "",
            "first_principles_review": bool(body.first_principles_review),
            "scope_paths": merge_scope_with_folders(body.scope_paths, body.folder_ids),
        }
        if body.top_k > 0:
            kwargs["top_k"] = body.top_k
        try:
            for ev in produce_stream(**kwargs):
                if ev.get("type") == "done" and body.save and not body.save_to_wiki:
                    out_root = output_dir()
                    out_root.mkdir(parents=True, exist_ok=True)
                    from lib.wiki import slugify, today_beijing

                    out = out_root / f"{slugify(body.topic)}-{today_beijing()}.md"
                    out.write_text(ev.get("content") or "", encoding="utf-8")
                    ev["saved_to"] = str(out)
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'text': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Private-Network": "true",
        },
    )


@app.post("/api/produce/revise")
def api_produce_revise(body: ProduceReviseBody):
    if not (body.content or "").strip():
        raise HTTPException(400, "当前正文为空")
    if not (body.instruction or "").strip():
        raise HTTPException(400, "请填写改稿要求")
    kwargs: dict = {
        "content": body.content,
        "instruction": body.instruction,
        "topic": body.topic or "改稿",
        "genre": body.genre or "article",
        "brief": body.brief or "",
        "use_rag": bool(body.use_rag),
        "first_principles_review": bool(body.first_principles_review),
        "scope_paths": merge_scope_with_folders(body.scope_paths, body.folder_ids),
    }
    if body.top_k > 0:
        kwargs["top_k"] = body.top_k
    return produce_revise(**kwargs)


@app.post("/api/produce/revise/stream")
def api_produce_revise_stream(body: ProduceReviseBody):
    if not (body.content or "").strip():
        raise HTTPException(400, "当前正文为空")
    if not (body.instruction or "").strip():
        raise HTTPException(400, "请填写改稿要求")

    def event_gen():
        kwargs: dict = {
            "content": body.content,
            "instruction": body.instruction,
            "topic": body.topic or "改稿",
            "genre": body.genre or "article",
            "brief": body.brief or "",
            "use_rag": bool(body.use_rag),
            "first_principles_review": bool(body.first_principles_review),
            "scope_paths": merge_scope_with_folders(body.scope_paths, body.folder_ids),
        }
        if body.top_k > 0:
            kwargs["top_k"] = body.top_k
        try:
            for ev in produce_revise_stream(**kwargs):
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'text': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Private-Network": "true",
        },
    )


@app.post("/api/produce/finalize")
def api_produce_finalize(body: ProduceFinalizeBody):
    try:
        return finalize_produce(
            content=body.content,
            topic=body.topic,
            genre=body.genre or "article",
            title=body.title or None,
            tags=body.tags or None,
            wiki_page=body.wiki_page or None,
            wiki_type=body.wiki_type or None,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/feedback")
def api_feedback_submit(body: FeedbackSubmitBody):
    from lib.feedback import enqueue_feedback
    import re

    html = (body.html or "").strip()
    plain = re.sub(r"<[^>]+>", "", html.replace("&nbsp;", " ")).strip()
    if len(plain) < 5:
        raise HTTPException(400, "请填写反馈内容（至少几个字）")
    return enqueue_feedback(html=html, subject=body.subject or "", contact=body.contact or "")


@app.get("/api/feedback/pending")
def api_feedback_pending():
    from lib.feedback import flush_pending, pending_count

    return {"pending": pending_count(), **flush_pending(limit=5)}


@app.post("/api/deduce/stream")
def api_deduce_stream(body: DeduceBody):
    def event_gen():
        from lib.deduce import deduce_stream

        kwargs: dict = {
            "query": body.query,
            "scope_paths": merge_scope_with_folders(body.scope_paths, body.folder_ids),
        }
        if body.top_k > 0:
            kwargs["top_k"] = body.top_k
        for ev in deduce_stream(**kwargs):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/deduce/export/docx")
def api_deduce_export_docx(body: DeduceExportBody):
    from urllib.parse import quote

    from lib.deduce_export import deduce_to_docx_bytes
    from lib.wiki import slugify

    content = body.content.strip()
    if not content:
        raise HTTPException(400, "content required")
    title = body.title.strip() or "推演"
    data = deduce_to_docx_bytes(content, title=title, graph_png_b64=body.graph_png or "")
    filename = f"{slugify(title)[:60] or 'deduce'}.docx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": (
                f'attachment; filename="deduce.docx"; filename*=UTF-8\'\'{quote(filename)}'
            )
        },
    )


@app.get("/api/tts/status")
def api_tts_status():
    from lib.tts import tts_status

    return tts_status()


@app.get("/api/tts/voices")
def api_tts_voices(provider: str = "", current: str = ""):
    from lib.config import llm_config, load_dotenv
    from lib.tts import PROVIDERS, _resolve_tts_provider, voice_options_for_provider

    load_dotenv()
    explicit = provider.strip().lower()
    if explicit and explicit in PROVIDERS:
        prov = explicit
    else:
        prov, _ = _resolve_tts_provider(llm_config())
    return {"provider": prov, "options": voice_options_for_provider(prov, current=current)}


@app.post("/api/tts/preview")
def api_tts_preview(body: TTSPreviewBody):
    from lib.tts import preview_tts_voice

    voice = (body.voice or "").strip()
    if not voice:
        raise HTTPException(400, "voice required")
    prov = (body.provider or "").strip().lower() or None
    try:
        result = preview_tts_voice(voice, provider=prov, text=body.text or None)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except RuntimeError as e:
        raise HTTPException(502, str(e)) from e
    media = "audio/wav" if result.format == "wav" else "audio/mpeg"
    return Response(
        content=result.audio,
        media_type=media,
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/produce/podcast-audio")
def api_produce_podcast_audio(body: PodcastAudioBody):
    from lib.podcast import synthesize_podcast

    try:
        return synthesize_podcast(body.content, title=body.title or "播客")
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except RuntimeError as e:
        raise HTTPException(502, str(e)) from e
    except OSError as e:
        raise HTTPException(500, f"无法写入播客文件（请检查用户数据目录权限）：{e}") from e
    except Exception as e:
        raise HTTPException(500, f"播客合成失败：{e}") from e


@app.post("/api/produce/yizhi-promo-audio")
def api_yizhi_promo_audio(body: YizhiPromoAudioBody):
    """Single-voice long narration from bundled 宣传文案.docx (not podcast dialogue)."""
    from lib.yizhi_narration import synthesize_yizhi_promo_audio

    try:
        return synthesize_yizhi_promo_audio(
            rewrite=bool(body.rewrite),
            title=(body.title or "易知宣传").strip() or "易知宣传",
        )
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except RuntimeError as e:
        raise HTTPException(502, str(e)) from e
    except OSError as e:
        raise HTTPException(500, f"无法写入音频文件：{e}") from e
    except Exception as e:
        raise HTTPException(500, f"宣传语音合成失败：{e}") from e


@app.get("/api/podcast/audio")
def api_podcast_audio_file(path: str):
    from lib.config import output_dir

    safe = path.replace("\\", "/").strip().lstrip("/")
    if ".." in safe.split("/"):
        raise HTTPException(403, "invalid path")
    base = output_dir().resolve()
    p = (base / safe).resolve()
    try:
        p.relative_to(base)
    except ValueError as e:
        raise HTTPException(403, "invalid path") from e
    if not p.is_file():
        raise HTTPException(404, "file not found")
    ext = p.suffix.lower()
    media = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
    }.get(ext, "application/octet-stream")
    return FileResponse(
        p,
        media_type=media,
        filename=p.name,
        headers={"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"},
    )


@app.post("/api/produce/export/docx")
def api_produce_export_docx(body: ProduceExportBody):
    from urllib.parse import quote

    from lib.wiki import slugify

    content = body.content.strip()
    if not content:
        raise HTTPException(400, "content required")
    title = body.title.strip() or "产出"
    data = markdown_to_docx_bytes(content, title=title)
    filename = f"{slugify(title)[:60] or 'produce'}.docx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": (
                f'attachment; filename="produce.docx"; filename*=UTF-8\'\'{quote(filename)}'
            )
        },
    )


@app.get("/api/assets")
def api_assets(page: int = 1, size: int = 20):
    return list_assets_page(page=page, size=size)


@app.get("/api/library/assets")
def api_library_assets(page: int = 1, size: int = 20, q: str = ""):
    from lib.paging import paginate

    items = [a.__dict__ for a in list_assets()]
    if q.strip():
        needle = q.strip().lower()
        items = [
            a
            for a in items
            if needle in (a.get("filename") or "").lower()
            or needle in (a.get("rel_path") or "").lower()
            or needle in (a.get("category") or "").lower()
        ]
    items.sort(key=lambda x: (x.get("updated") or "", x.get("filename") or ""), reverse=True)
    return paginate(items, page, size)


@app.get("/api/library/rag")
def api_library_rag(page: int = 1, size: int = 20, q: str = ""):
    from lib.library import list_rag_library

    return list_rag_library(page=page, size=size, q=q)


@app.patch("/api/library/assets/{asset_id}")
def api_library_asset_rename(asset_id: str, body: AssetRenameBody):
    try:
        rec = rename_asset(asset_id, body.filename.strip())
        sync_all()
        return rec.__dict__
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.put("/api/library/assets/{asset_id}/folders")
def api_library_asset_folders(asset_id: str, body: AssetFoldersBody):
    from lib.assets import set_asset_folder_ids

    try:
        rec = set_asset_folder_ids(asset_id, body.folder_ids)
        return {"ok": True, **rec.__dict__}
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@app.delete("/api/library/assets/{asset_id}")
def api_library_asset_delete(asset_id: str):
    try:
        result = delete_asset(asset_id)
        sync_all()
        return result
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e


@app.get("/api/assets/file")
def api_asset_file(path: str, inline: bool = False):
    from urllib.parse import quote

    from lib.media_types import MIME_MAP

    p = wiki_root() / path
    if not p.is_file():
        raise HTTPException(404, "file not found")

    media_type = MIME_MAP.get(p.suffix.lower())
    if not media_type and "-" in p.name:
        tail = p.name.split("-", 1)[1]
        media_type = MIME_MAP.get(Path(tail).suffix.lower())
    if not media_type:
        import mimetypes

        media_type = mimetypes.guess_type(p.name)[0] or "application/octet-stream"

    disp = "inline" if inline else "attachment"
    return FileResponse(
        p,
        media_type=media_type,
        headers={"Content-Disposition": f"{disp}; filename*=UTF-8''{quote(p.name)}"},
    )


@app.get("/api/assets/extract-text")
def api_asset_extract_text(path: str):
    """Return cached or live text extraction for preview fallback."""
    from lib.extract import extract_text

    root = wiki_root()
    p = root / path
    if not p.is_file():
        raise HTTPException(404, "file not found")

    digest = p.name.split("-", 1)[0] if "-" in p.name else p.stem
    cached = root / "assets" / ".extracted" / f"{digest}.txt"
    if cached.is_file():
        text = cached.read_text(encoding="utf-8", errors="replace")
        return {"text": text, "source": "cache"}
    return {"text": extract_text(p), "source": "live"}


@app.post("/api/editor/media")
async def api_editor_media(file: UploadFile = File(...)):
    """Save inline image for memo/note rich editor."""
    from uuid import uuid4

    root = wiki_root()
    suffix = Path(file.filename or "image.png").suffix.lower()
    allowed = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}
    if suffix not in allowed:
        raise HTTPException(400, detail="仅支持图片格式")
    dest_dir = root / "assets" / "images" / "editor"
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = f"{uuid4().hex[:12]}{suffix}"
    dest = dest_dir / name
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    rel = f"assets/images/editor/{name}"
    from urllib.parse import quote

    url = f"/api/assets/file?path={quote(rel)}&inline=1"
    return {"url": url, "path": rel, "filename": name}


@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...), target: str = "inbox"):
    root = wiki_root()
    suffix = Path(file.filename or "upload.bin").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)
    try:
        job_id = enqueue_upload_job([(tmp_path, file.filename)], root=root)
        return {
            "job_id": job_id,
            "total": 1,
            "async": True,
            "uploaded": file.filename or tmp_path.name,
        }
    except Exception as e:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise HTTPException(500, detail=str(e)) from e


@app.post("/api/upload/batch")
async def api_upload_batch(files: list[UploadFile] = File(...)):
    root = wiki_root()
    if not files:
        raise HTTPException(400, detail="请选择至少一个文件")
    specs: list[tuple[Path, str | None]] = []
    try:
        for file in files:
            suffix = Path(file.filename or "upload.bin").suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                shutil.copyfileobj(file.file, tmp)
                specs.append((Path(tmp.name), file.filename))
        job_id = enqueue_upload_job(specs, root=root)
        return {"job_id": job_id, "total": len(specs), "async": True}
    except Exception as e:
        for path, _ in specs:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise HTTPException(500, detail=str(e)) from e


@app.get("/api/upload/jobs/active")
def api_upload_jobs_active():
    return {"jobs": list_active_jobs()}


@app.get("/api/upload/jobs/{job_id}")
def api_upload_job(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, detail="任务不存在或已过期")
    return job


class UrlImport(BaseModel):
    url: str
    force: bool = False


class TextImport(BaseModel):
    text: str
    title: str = ""


@app.post("/api/url")
def api_url(body: UrlImport):
    try:
        job_info = start_url_ingest_job(body.url, force=body.force)
        return {"ok": True, **job_info}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/url/jobs/active")
def api_url_ingest_jobs_active():
    return {"jobs": list_url_ingest_jobs()}


@app.get("/api/url/jobs/{job_id}")
def api_url_ingest_job(job_id: str):
    job = get_url_ingest_job(job_id)
    if not job:
        raise HTTPException(404, detail="任务不存在或已过期")
    return job


@app.post("/api/text")
def api_text(body: TextImport):
    try:
        result = ingest_text(body.text, title=body.title or None)
        maybe_defer_rescan()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/api/ingest")
def api_ingest():
    result = ingest_inbox_bulk()
    maybe_defer_rescan()
    return result


@app.get("/api/docubrowser/status")
def api_docubrowser_status():
    return docubrowser_status()


@app.post("/api/docubrowser/rescan")
def api_docubrowser_rescan(no_embed: bool = False):
    try:
        return rescan_wiki_assets(no_embed=no_embed)
    except RuntimeError as e:
        msg = str(e)
        if not no_embed and ("ollama" in msg.lower() or "Ollama" in msg):
            try:
                return rescan_wiki_assets(no_embed=True)
            except RuntimeError as e2:
                raise HTTPException(status_code=400, detail=str(e2)) from e2
        raise HTTPException(status_code=400, detail=msg) from e


@app.get("/api/docubrowser/open-url")
def api_docubrowser_open_url():
    return {"url": open_ui()}


@app.post("/api/index")
def api_index(async_mode: bool = True):
    if async_mode:
        job_info = start_index_job()
        return {"ok": True, "indexing": True, **job_info}
    from lib.index_writer import run_sync_now

    n = run_sync_now()
    maybe_defer_rescan()
    return {"rag_chunks": n}


@app.get("/api/index/jobs/active")
def api_index_jobs_active():
    return {"jobs": list_index_jobs()}


@app.get("/api/index/jobs/{job_id}")
def api_index_job(job_id: str):
    job = get_index_job(job_id)
    if not job:
        raise HTTPException(404, detail="任务不存在或已过期")
    return job


@app.get("/api/capabilities")
def api_capabilities():
    from lib.capabilities import list_capabilities

    return list_capabilities()


@app.post("/api/capabilities/setup-tools")
def api_setup_optional_tools():
    import subprocess
    import sys

    root = wiki_root()
    script = root / "scripts" / "setup_optional_tools.py"
    if not script.is_file():
        raise HTTPException(404, detail="setup_optional_tools.py not found")
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(504, detail="安装超时，请稍后重试") from exc
    from lib.capabilities import list_capabilities

    caps = list_capabilities()
    output = (proc.stdout or "") + (proc.stderr or "")
    return {
        "ok": proc.returncode == 0,
        "output": output[-8000:] if len(output) > 8000 else output,
        "capabilities": caps,
    }


@app.get("/api/maintenance/drafts")
def api_maintenance_drafts(limit: int = 30):
    from lib.maintenance import list_draft_summary

    return list_draft_summary(limit=limit)


class MaintenanceRefineBody(BaseModel):
    paths: list[str] = []
    all_drafts: bool = False
    limit: int = 0


@app.post("/api/maintenance/refine")
def api_maintenance_refine(body: MaintenanceRefineBody):
    from lib.maintenance import mark_all_drafts_refined, mark_pages_refined

    if body.all_drafts:
        return mark_all_drafts_refined(limit=body.limit)
    if not body.paths:
        raise HTTPException(400, "请指定 paths 或 all_drafts")
    return mark_pages_refined(body.paths)


@app.get("/api/library/external")
def api_library_external(page: int = 1, size: int = 40, q: str = ""):
    from lib.maintenance import list_external_rag_chunks

    return list_external_rag_chunks(page=page, size=size, q=q)


class SkillRunBody(BaseModel):
    name: str
    params: dict = {}


class SkillMatchBody(BaseModel):
    text: str
    params: dict = {}


class WorkflowCreateBody(BaseModel):
    label: str
    skill: str
    params: dict = {}


class WorkflowRunBody(BaseModel):
    name: str
    params: dict = {}


@app.get("/api/skills")
def api_skills_list(page: int = 1, size: int = 30, runnable_only: bool = True):
    from lib.paging import paginate

    data = [s.to_dict() for s in discover_skills(runnable_only=runnable_only)]
    return paginate(data, page, size)


@app.get("/api/skills/content")
def api_skills_content(name: str):
    try:
        return {"name": name, "content": load_skill_content(name)}
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@app.post("/api/skills/run")
def api_skills_run(body: SkillRunBody):
    return run_skill(body.name, body.params)


@app.post("/api/skills/match")
def api_skills_match(body: SkillMatchBody):
    skill = match_skill(body.text)
    if not skill:
        return {"ok": False, "error": "未匹配到 Skill"}
    result = run_skill(skill.name, body.params or {"text": body.text})
    result["matched_skill"] = skill.name
    return result


@app.get("/api/workflows")
def api_workflows_list():
    return list_all_workflows()


@app.post("/api/workflows")
def api_workflows_create(body: WorkflowCreateBody):
    try:
        return add_custom_workflow(body.label, body.skill, body.params)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.delete("/api/workflows")
def api_workflows_delete(id: str):
    return remove_custom_workflow(id)


@app.post("/api/workflows/run")
def api_workflows_run(body: WorkflowRunBody):
    return run_workflow(body.name, body.params)


@app.get("/api/loop/status")
def api_loop_status():
    return loop_status()


@app.post("/api/loop/run")
def api_loop_run(body: LoopRunBody):
    return run_loop(level=body.level, dry_run=body.dry_run)


@app.get("/api/memory/sessions")
def api_memory_sessions():
    return list_sessions()


@app.get("/api/memory/session")
def api_memory_session(session_id: str):
    if not session_id.strip():
        raise HTTPException(400, "session_id required")
    return get_session_detail(session_id.strip())


@app.patch("/api/memory/session/{session_id}")
def api_memory_session_patch(session_id: str, body: SessionPatchBody):
    try:
        return update_session_meta(
            session_id.strip(),
            title=body.title,
            summary=body.summary,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.delete("/api/memory/session/{session_id}")
def api_memory_session_delete(session_id: str):
    if not delete_session(session_id.strip()):
        raise HTTPException(404, "session not found")
    return {"ok": True, "id": session_id}


@app.post("/api/memory/session/{session_id}/summarize")
def api_memory_session_summarize(session_id: str):
    summary = maybe_summarize_session(session_id.strip())
    return get_session_detail(session_id.strip()) | {"forced_summary": summary}


@app.get("/api/memory/continuity")
def api_memory_continuity():
    return get_continuity()


@app.get("/api/memory/fortune")
def api_memory_fortune(record: int = 1):
    from lib.fortune import fortune_bundle

    return fortune_bundle(record=bool(record))


@app.post("/api/memory/fortune/checkin")
def api_memory_fortune_checkin():
    from lib.fortune import daily_slip, record_slip

    slip = daily_slip()
    return record_slip(slip)


@app.get("/api/memory/fortune/checklist")
def api_memory_fortune_checklist():
    from lib.fortune import produce_checklist

    return produce_checklist()


@app.get("/api/memory/evolution")
def api_memory_evolution(refresh: int = 0):
    return get_evolution(refresh=bool(refresh))


@app.get("/api/memory/audit")
def api_memory_audit(limit: int = 50, offset: int = 0):
    return list_audit(limit=limit, offset=offset)


@app.get("/api/memory/contrarian/assumptions")
def api_contrarian_assumptions(limit: int = 80):
    from lib.contrarian import collect_assumptions

    rows = collect_assumptions(limit=max(1, min(200, limit)))
    return {"count": len(rows), "items": rows}


class ContrarianScanBody(BaseModel):
    write_draft: bool = True


@app.post("/api/memory/contrarian/scan")
def api_contrarian_scan(body: ContrarianScanBody | None = None):
    from lib.contrarian import scan_contradictions

    opts = body or ContrarianScanBody()
    return scan_contradictions(write_draft=bool(opts.write_draft))


@app.get("/api/memory/history")
def api_memory_history(limit: int = 20, session_id: str = "", offset: int = 0, page: int = 0):
    page_size = max(1, min(limit, 100))
    if page > 0:
        offset = (page - 1) * page_size
    data = list_qa_history(limit=page_size, session_id=session_id.strip(), offset=max(0, offset))
    total = data.get("total", 0)
    pages = max(1, (total + page_size - 1) // page_size) if total else 1
    current_page = page if page > 0 else (offset // page_size + 1)
    return {**data, "page": current_page, "size": page_size, "pages": pages}


@app.patch("/api/memory/history/{qa_id}")
def api_memory_history_rename(qa_id: int, body: HistoryRenameBody):
    question = body.question.strip()
    if not question:
        raise HTTPException(400, "question required")
    if not update_qa_entry_question(qa_id, question):
        raise HTTPException(404, "entry not found")
    return {"ok": True, "id": qa_id, "question": question}


@app.delete("/api/memory/history/{qa_id}")
def api_memory_history_delete(qa_id: int):
    if not delete_qa_entry(qa_id):
        raise HTTPException(404, "entry not found")
    return {"ok": True, "id": qa_id}


@app.get("/api/memory/history/{qa_id}/export/docx")
def api_memory_history_export_docx(qa_id: int):
    from urllib.parse import quote

    from lib.wiki import slugify

    entry = get_qa_entry(qa_id)
    if not entry:
        raise HTTPException(404, "entry not found")
    title = str(entry.get("question") or "对话记录")[:80]
    content = f"## 问\n\n{entry.get('question') or ''}\n\n## 答\n\n{entry.get('answer') or ''}"
    data = markdown_to_docx_bytes(content, title=title)
    filename = f"{slugify(title)[:60] or 'history'}.docx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": (
                f'attachment; filename="history.docx"; filename*=UTF-8\'\'{quote(filename)}'
            )
        },
    )


@app.get("/api/memory/stats")
def api_memory_stats():
    return memory_stats()


@app.get("/api/memory/new-session")
def api_new_session():
    return {"session_id": new_session_id()}


@app.get("/api/stats")
def api_stats():
    pages = list_pages(include_inbox=False)
    assets = list_assets()
    from collections import Counter

    style_profile = get_style_profile(refresh_if_stale=False) if style_enabled() else {}
    return {
        "pages": len(pages),
        "assets": len(assets),
        "by_type": dict(Counter(p.type for p in pages)),
        "by_status": dict(Counter(p.status for p in pages)),
        "extra_dirs": [str(p) for p in extra_dirs()],
        "memory": memory_stats(),
        "writing_style": {
            "enabled": style_enabled(),
            "updated_at": style_profile.get("updated_at", ""),
            "sample_count": style_profile.get("sample_count", 0),
        },
    }


@app.get("/viewer", response_class=HTMLResponse)
def viewer_page():
    p = _ELECTRON_RENDERER / "viewer.html"
    if not p.is_file():
        raise HTTPException(404, "viewer not found")
    return HTMLResponse(p.read_text(encoding="utf-8"))


if _FILE_VIEWER_VENDOR.is_dir():
    app.mount(
        "/app-static/file-viewer",
        FileViewerStaticFiles(directory=str(_FILE_VIEWER_VENDOR)),
        name="file-viewer-static",
    )


def main() -> None:
    import sys

    import uvicorn

    if sys.platform == "win32":
        import asyncio

        # Avoid noisy ConnectionResetError when browsers abort audio range requests.
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    port = int(__import__("os").environ.get("MYKNOWLEDGE_PORT", "18765"))
    # 冻结 / 无控制台：显式 use_colors=False，避免 ColourizedFormatter 走 None.isatty。
    # 勿对 logging.Formatter 传 use_colors——uvicorn 会把 kwargs 注入 formatters 字典。
    need_safe_log = getattr(sys, "frozen", False) or sys.stdout is None or sys.stderr is None
    log_config = None
    if need_safe_log:
        log_config = {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "()": "uvicorn.logging.DefaultFormatter",
                    "fmt": "%(levelprefix)s %(message)s",
                    "use_colors": False,
                },
                "access": {
                    "()": "uvicorn.logging.AccessFormatter",
                    "fmt": '%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
                    "use_colors": False,
                },
            },
            "handlers": {
                "default": {
                    "formatter": "default",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stderr",
                },
                "access": {
                    "formatter": "access",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stderr",
                },
            },
            "loggers": {
                "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
                "uvicorn.error": {"handlers": ["default"], "level": "INFO", "propagate": False},
                "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
            },
        }
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info", log_config=log_config)


if __name__ == "__main__":
    main()
