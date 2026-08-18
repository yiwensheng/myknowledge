"""易知授权服务 API."""

from __future__ import annotations

import json
import sys
import urllib.parse
from pathlib import Path

if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from . import db
from . import xunhupay
from .config import (
    admin_key,
    db_path,
    dev_mock_pay,
    feedback_enabled,
    jwt_secret,
    plan_prices,
    port,
    product_title_prefix,
)
from .jwt_utils import make_license_token

app = FastAPI(title="易知/周易 License API", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


PLAN_PATTERN = "^(month|year|lifetime)$"
PRODUCT_PATTERN = "^(yizhi|zhouyi)$"


class CreateOrderBody(BaseModel):
    plan: str = Field(..., pattern=PLAN_PATTERN)
    device_id: str = Field(..., min_length=8, max_length=64)
    product: str = Field(default="yizhi", pattern=PRODUCT_PATTERN)
    channel_code: str = Field(default="", max_length=40)


class ActivateBody(BaseModel):
    device_id: str = Field(..., min_length=8, max_length=64)
    order_id: str = ""
    code: str = ""


class HeartbeatBody(BaseModel):
    token: str
    device_id: str


class SelfUnbindBody(BaseModel):
    token: str
    device_id: str


class AdminMarkPaidBody(BaseModel):
    admin_key: str
    order_id: str


class AdminUnbindBody(BaseModel):
    admin_key: str
    license_id: str = ""
    device_id: str = ""


class AdminCreateCodeBody(BaseModel):
    admin_key: str
    plan: str = Field(..., pattern=PLAN_PATTERN)


class AdminPromoterBody(BaseModel):
    admin_key: str
    code: str = Field(..., min_length=4, max_length=40)
    name: str = ""
    commission_rate: float = Field(default=0.2, ge=0, le=1)
    note: str = ""


class FeedbackBody(BaseModel):
    html: str = Field(..., min_length=1, max_length=200_000)
    subject: str = Field(default="", max_length=200)
    contact: str = Field(default="", max_length=200)
    app_version: str = Field(default="", max_length=40)
    device_id: str = Field(default="", max_length=64)


_feedback_hits: dict[str, list[float]] = {}


def _feedback_rate_ok(ip: str, limit: int = 8, window: float = 3600.0) -> bool:
    import time

    now = time.time()
    bucket = _feedback_hits.setdefault(ip or "unknown", [])
    _feedback_hits[ip or "unknown"] = [t for t in bucket if now - t < window]
    if len(_feedback_hits[ip or "unknown"]) >= limit:
        return False
    _feedback_hits[ip or "unknown"].append(now)
    return True


def _require_admin(key: str) -> None:
    if not key or key != admin_key():
        raise HTTPException(403, "invalid admin key")


def _token_for_license(lic: dict) -> str:
    return make_license_token(
        license_id=lic["id"],
        device_id=lic["device_id"],
        plan=lic["plan"],
        expires_at=db.license_expires_ts(lic),
        secret=jwt_secret(),
    )


def _order_response(order: dict) -> dict:
    lic = db.get_license_by_id_for_order(order["id"])
    out = {
        "order_id": order["id"],
        "plan": order["plan"],
        "amount": order["amount"],
        "status": order["status"],
        "qr_url": order.get("qr_url") or "",
        "activation_code": order.get("activation_code") or "",
        "device_id": order.get("device_id") or "",
        "product": order.get("product") or "yizhi",
        "channel_code": order.get("channel_code") or "",
        "created_at": order.get("created_at") or "",
        "paid_at": order.get("paid_at") or "",
    }
    if lic:
        out["license_id"] = lic["id"]
        out["expires_at"] = lic["expires_at"]
        out["token"] = _token_for_license(lic)
    return out


@app.get("/health")
def health():
    from .feedback_mail import mail_ready

    fb: dict = {"disabled": True}
    if feedback_enabled():
        fb = mail_ready()
        try:
            from .feedback_store import list_unmailed

            fb["unmailed"] = len(list_unmailed(limit=200))
        except Exception:
            fb["unmailed"] = -1
    return {
        "ok": True,
        "mock_pay": dev_mock_pay(),
        "feedback": fb,
    }


@app.get("/license/plans")
def api_plans(product: str = "yizhi"):
    prod = (product or "yizhi").strip().lower()
    if prod not in ("yizhi", "zhouyi"):
        raise HTTPException(400, "invalid product")
    prices = plan_prices(prod)
    return {
        "product": prod,
        "plans": [
            {"id": "month", "name": "月付", "days": 30, "price": prices["month"]},
            {"id": "year", "name": "年付", "days": 365, "price": prices["year"]},
            {
                "id": "lifetime",
                "name": "终身",
                "days": 0,
                "price": prices["lifetime"],
                "lifetime": True,
            },
        ],
    }


@app.post("/license/create-order")
def api_create_order(body: CreateOrderBody):
    try:
        order = db.create_order(
            body.plan,
            body.device_id,
            product=body.product,
            channel_code=body.channel_code or "",
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    title = f"{product_title_prefix(body.product)}订阅-{body.plan}"
    try:
        pay = xunhupay.create_payment(order["id"], float(order["amount"]), title)
        db.set_order_qr(order["id"], pay["qr_url"], pay.get("trade_no", ""))
        order = db.get_order(order["id"]) or order
    except RuntimeError as e:
        if not dev_mock_pay():
            raise HTTPException(502, str(e)) from e

    return _order_response(order)


@app.get("/license/order/{order_id}")
def api_get_order(order_id: str):
    order = db.get_order(order_id)
    if not order:
        raise HTTPException(404, "order not found")
    return _order_response(order)


@app.post("/license/activate")
def api_activate(body: ActivateBody):
    try:
        if body.code.strip():
            lic = db.activate_with_code(body.code.strip(), body.device_id)
            if not lic:
                raise HTTPException(400, "invalid activation code")
        elif body.order_id.strip():
            lic = db.activate_order(body.order_id.strip(), body.device_id)
        else:
            raise HTTPException(400, "order_id or code required")
    except ValueError as e:
        code = str(e)
        msgs = {
            "order_not_found": "订单不存在",
            "order_not_paid": "订单未支付",
            "device_mismatch": "与下单设备不一致",
            "already_bound_other": "已在其他电脑激活",
            "device_conflict": "该设备已有有效授权",
            "issue_failed": "签发授权失败",
            "unbind_limit_exceeded": "本年度换机次数已用完，请联系客服",
        }
        raise HTTPException(400, msgs.get(code, code)) from e

    return {
        "ok": True,
        "license_id": lic["id"],
        "plan": lic["plan"],
        "expires_at": lic["expires_at"],
        "token": _token_for_license(lic),
    }


@app.post("/license/heartbeat")
def api_heartbeat(body: HeartbeatBody):
    from .jwt_utils import verify_token

    payload = verify_token(body.token, jwt_secret())
    if not payload:
        raise HTTPException(401, "invalid token")
    license_id = str(payload.get("sub") or "")
    if payload.get("device_id") != body.device_id:
        raise HTTPException(403, "device mismatch")
    try:
        lic = db.heartbeat(license_id, body.device_id)
    except ValueError as e:
        raise HTTPException(402, str(e)) from e
    return {
        "ok": True,
        "expires_at": lic["expires_at"],
        "token": _token_for_license(lic),
    }


@app.post("/license/self-unbind")
def api_self_unbind(body: SelfUnbindBody):
    from .jwt_utils import verify_token

    payload = verify_token(body.token, jwt_secret())
    if not payload:
        raise HTTPException(401, "invalid token")
    license_id = str(payload.get("sub") or "")
    if payload.get("device_id") != body.device_id:
        raise HTTPException(403, "device mismatch")
    try:
        db.self_unbind(license_id, body.device_id)
    except ValueError as e:
        msgs = {
            "license_not_found": "授权不存在",
            "unbind_limit_exceeded": "本年度换机次数已用完，请联系客服",
        }
        raise HTTPException(400, msgs.get(str(e), str(e))) from e
    return {"ok": True}


@app.post("/pay/xunhupay/notify")
async def xunhupay_notify(request: Request):
    try:
        form = await _read_notify_form(request)
    except Exception as exc:
        try:
            db.log_event("notify_parse_error", str(exc))
        except Exception:
            pass
        return PlainTextResponse("fail", status_code=400)

    try:
        db.log_event("notify_hit", form.get("trade_order_id", "")[:32])
    except Exception:
        pass

    if not xunhupay.verify_notify(form):
        try:
            db.log_event("notify_verify_fail", form.get("trade_order_id", "")[:32])
        except Exception:
            pass
        return PlainTextResponse("fail")

    parsed = xunhupay.parse_notify(form)
    if parsed["paid"] and parsed["order_id"]:
        db.mark_order_paid(parsed["order_id"], parsed.get("trade_no", ""))
        try:
            db.log_event("notify_paid", parsed["order_id"])
        except Exception:
            pass
    return PlainTextResponse("success")


async def _read_notify_form(request: Request) -> dict[str, str]:
    """Parse xunhupay notify body without python-multipart."""
    ctype = (request.headers.get("content-type") or "").lower()
    body = await request.body()
    text = body.decode(errors="replace")
    if "application/json" in ctype:
        data = json.loads(text or "{}")
        return {str(k): str(v) for k, v in data.items()}
    parsed = urllib.parse.parse_qs(text, keep_blank_values=True)
    return {k: (v[0] if v else "") for k, v in parsed.items()}


@app.post("/feedback")
async def api_feedback(body: FeedbackBody, request: Request):
    if not feedback_enabled():
        raise HTTPException(503, "feedback disabled")
    html = (body.html or "").strip()
    plain = (
        html.replace("<br>", "\n")
        .replace("<br/>", "\n")
        .replace("<br />", "\n")
        .replace("&nbsp;", " ")
    )
    import re

    plain = re.sub(r"<[^>]+>", "", plain).strip()
    if len(plain) < 5:
        raise HTTPException(400, "反馈内容过短")
    client_ip = request.client.host if request.client else ""
    if not _feedback_rate_ok(client_ip):
        raise HTTPException(429, "提交过于频繁，请稍后再试")

    from .feedback_store import save_feedback, try_mail_item, update_mail_status

    subject = (body.subject or "").strip() or "易知用户反馈"
    item = save_feedback(
        html=html,
        subject=subject,
        contact=(body.contact or "").strip(),
        app_version=(body.app_version or "").strip(),
        device_id=(body.device_id or "").strip(),
        client_ip=client_ip or "",
    )
    # 先落盘再发信（限时），避免网关 502 / 客户端长时间挂起
    ok, method, err = try_mail_item(item, timeout_sec=18.0)
    if ok:
        update_mail_status(item["id"], mailed=True, method=method)
    else:
        update_mail_status(item["id"], mailed=False, error=err)
    return {
        "ok": True,
        "id": item["id"],
        "stored": True,
        "mailed": ok,
        "method": method if ok else "",
        "mail_error": "" if ok else err,
        "to": "ywsay@126.com",
    }


@app.post("/admin/mark-paid")
def admin_mark_paid(body: AdminMarkPaidBody):
    _require_admin(body.admin_key)
    order = db.mark_order_paid(body.order_id)
    if not order:
        raise HTTPException(404, "order not found")
    lic = db.get_license_by_id_for_order(body.order_id)
    return {"ok": True, "order": _order_response(order), "license": lic}


@app.post("/admin/mark-free")
def admin_mark_free(body: AdminMarkPaidBody):
    _require_admin(body.admin_key)
    try:
        order = db.mark_order_free(body.order_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if not order:
        raise HTTPException(404, "order not found")
    lic = db.get_license_by_id_for_order(body.order_id)
    return {"ok": True, "order": _order_response(order), "license": lic}


@app.post("/admin/cancel-order")
def admin_cancel_order(body: AdminMarkPaidBody):
    _require_admin(body.admin_key)
    try:
        ok = db.delete_order(body.order_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if not ok:
        raise HTTPException(404, "order not found")
    return {"ok": True, "deleted": body.order_id}


@app.post("/admin/unbind")
def admin_unbind(body: AdminUnbindBody):
    _require_admin(body.admin_key)
    ok = db.unbind_license(body.license_id, body.device_id)
    if not ok:
        raise HTTPException(404, "license not found")
    return {"ok": True}


@app.post("/admin/create-code")
def admin_create_code(body: AdminCreateCodeBody):
    _require_admin(body.admin_key)
    code = db.create_activation_code(body.plan)
    return {"ok": True, "code": code, "plan": body.plan}


@app.get("/admin/stats")
def admin_stats(
    admin_key: str = "",
    period: str = "month",
    active_days: int = 30,
):
    _require_admin(admin_key)
    if period not in ("day", "week", "month", "quarter", "year"):
        raise HTTPException(400, "invalid period")
    if active_days < 1 or active_days > 365:
        raise HTTPException(400, "active_days out of range")
    from .stats import compute_stats

    return compute_stats(
        str(db_path()),
        period=period,
        active_days=active_days,
    )


@app.get("/admin/orders")
def admin_orders(
    admin_key: str = "",
    product: str = "",
    status: str = "",
    channel_code: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 50,
    offset: int = 0,
):
    _require_admin(admin_key)
    rows, total = db.list_orders(
        product=product,
        status=status,
        channel_code=channel_code,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "orders": [_order_response(r) for r in rows],
    }


@app.get("/admin/channels")
def admin_channels(
    admin_key: str = "",
    product: str = "",
    status: str = "paid",
):
    _require_admin(admin_key)
    return {"channels": db.channel_summaries(product=product, status=status)}


@app.get("/admin/promoters")
def admin_list_promoters(admin_key: str = ""):
    _require_admin(admin_key)
    return {"promoters": db.list_promoters()}


@app.get("/admin/feedback")
def admin_list_feedback(
    admin_key: str = "",
    limit: int = 50,
    offset: int = 0,
    mailed: str = "",
):
    """运营台：查看已固化的用户反馈。"""
    _require_admin(admin_key)
    mailed_flag: int | None = None
    if mailed.strip() in ("0", "1"):
        mailed_flag = int(mailed.strip())
    # 顺带把历史 inbox json 导入库（幂等）
    try:
        from .feedback_store import inbox_dir

        for path in inbox_dir().glob("*.json"):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            fid = str(item.get("id") or path.stem)
            if db.get_feedback(fid):
                continue
            created = item.get("created_at")
            if isinstance(created, (int, float)):
                from datetime import datetime, timedelta, timezone

                beijing = timezone(timedelta(hours=8))
                created = datetime.fromtimestamp(created, tz=beijing).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            db.insert_feedback(
                feedback_id=fid,
                html=str(item.get("html") or ""),
                subject=str(item.get("subject") or ""),
                contact=str(item.get("contact") or ""),
                app_version=str(item.get("app_version") or ""),
                device_id=str(item.get("device_id") or ""),
                client_ip=str(item.get("client_ip") or ""),
                created_at=str(created or ""),
            )
            if item.get("mailed"):
                db.update_feedback_mail(
                    fid,
                    mailed=True,
                    method=str(item.get("mail_method") or ""),
                    error="",
                )
    except Exception:
        pass
    return db.list_feedback(limit=limit, offset=offset, mailed=mailed_flag)


@app.post("/admin/promoters")
def admin_upsert_promoter(body: AdminPromoterBody):
    _require_admin(body.admin_key)
    try:
        row = db.upsert_promoter(
            body.code,
            name=body.name,
            commission_rate=body.commission_rate,
            note=body.note,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, "promoter": row}


@app.get("/admin/ui")
@app.get("/admin/ui/")
def admin_ui():
    from fastapi.responses import FileResponse

    path = Path(__file__).resolve().parent / "static" / "admin" / "index.html"
    if not path.is_file():
        raise HTTPException(404, "admin ui missing")
    return FileResponse(path, media_type="text/html; charset=utf-8")


@app.on_event("startup")
def _startup_seed() -> None:
    try:
        db.ensure_default_promoters()
    except Exception:
        pass
    try:
        from .feedback_store import start_feedback_mail_flusher

        start_feedback_mail_flusher()
    except Exception:
        pass


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=port(), log_level="info")


if __name__ == "__main__":
    main()
