"""SQLite persistence for license server."""

from __future__ import annotations

import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import db_path, plan_prices, unbind_per_year

BEIJING = timezone(timedelta(hours=8))

LIFETIME_PLAN = "lifetime"
LIFETIME_EXPIRES_AT = "2099-12-31 23:59:59"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
  id TEXT PRIMARY KEY,
  plan TEXT NOT NULL,
  amount REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  device_id TEXT NOT NULL DEFAULT '',
  product TEXT NOT NULL DEFAULT 'yizhi',
  pay_trade_no TEXT NOT NULL DEFAULT '',
  qr_url TEXT NOT NULL DEFAULT '',
  activation_code TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  paid_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS licenses (
  id TEXT PRIMARY KEY,
  order_id TEXT NOT NULL DEFAULT '',
  device_id TEXT NOT NULL DEFAULT '',
  plan TEXT NOT NULL,
  starts_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  unbind_count INTEGER NOT NULL DEFAULT 0,
  unbind_year INTEGER NOT NULL DEFAULT 0,
  last_seen_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS activation_codes (
  code TEXT PRIMARY KEY,
  plan TEXT NOT NULL,
  used INTEGER NOT NULL DEFAULT 0,
  license_id TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,
  detail TEXT NOT NULL DEFAULT '',
  at TEXT NOT NULL
);
"""


def _now_str() -> str:
    return datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M:%S")


def _now_ts() -> int:
    return int(datetime.now(BEIJING).timestamp())


def _plan_days(plan: str) -> int:
    if plan == "year":
        return 365
    if plan == "month":
        return 30
    raise ValueError(f"invalid plan for days: {plan}")


def compute_expires_at(plan: str, starts: datetime) -> datetime:
    if plan == LIFETIME_PLAN:
        return datetime.strptime(LIFETIME_EXPIRES_AT, "%Y-%m-%d %H:%M:%S").replace(tzinfo=BEIJING)
    return starts + timedelta(days=_plan_days(plan))


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    lic_cols = {r[1] for r in conn.execute("PRAGMA table_info(licenses)").fetchall()}
    if "last_seen_at" not in lic_cols:
        conn.execute(
            "ALTER TABLE licenses ADD COLUMN last_seen_at TEXT NOT NULL DEFAULT ''"
        )
    order_cols = {r[1] for r in conn.execute("PRAGMA table_info(orders)").fetchall()}
    if "product" not in order_cols:
        conn.execute(
            "ALTER TABLE orders ADD COLUMN product TEXT NOT NULL DEFAULT 'yizhi'"
        )
    if "channel_code" not in order_cols:
        conn.execute(
            "ALTER TABLE orders ADD COLUMN channel_code TEXT NOT NULL DEFAULT ''"
        )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS promoters (
          code TEXT PRIMARY KEY,
          name TEXT NOT NULL DEFAULT '',
          commission_rate REAL NOT NULL DEFAULT 0.2,
          note TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_orders_channel ON orders(channel_code)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_orders_product_status ON orders(product, status)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback (
          id TEXT PRIMARY KEY,
          created_at TEXT NOT NULL DEFAULT '',
          subject TEXT NOT NULL DEFAULT '',
          contact TEXT NOT NULL DEFAULT '',
          html TEXT NOT NULL DEFAULT '',
          app_version TEXT NOT NULL DEFAULT '',
          device_id TEXT NOT NULL DEFAULT '',
          client_ip TEXT NOT NULL DEFAULT '',
          mailed INTEGER NOT NULL DEFAULT 0,
          mail_method TEXT NOT NULL DEFAULT '',
          mail_error TEXT NOT NULL DEFAULT '',
          mailed_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback(created_at DESC)"
    )


def ensure_db_schema_at(path: str | Path) -> None:
    """Idempotent schema patch for CLI stats/export against LICENSE_DB file."""
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        _ensure_schema(conn)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def connect():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        _ensure_schema(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def log_event(kind: str, detail: str = "") -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO events (kind, detail, at) VALUES (?, ?, ?)",
            (kind, detail[:2000], _now_str()),
        )


def create_order(
    plan: str,
    device_id: str,
    product: str = "yizhi",
    channel_code: str = "",
) -> dict[str, Any]:
    prod = (product or "yizhi").strip().lower()
    if prod not in ("yizhi", "zhouyi"):
        raise ValueError(f"invalid product: {product}")
    prices = plan_prices(prod)
    if plan not in prices:
        raise ValueError(f"invalid plan: {plan}")
    ch = _normalize_channel_code(channel_code)
    order_id = uuid.uuid4().hex[:16]
    code = secrets.token_hex(4).upper()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO orders
              (id, plan, amount, status, device_id, product, activation_code,
               created_at, channel_code)
            VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?)
            """,
            (order_id, plan, prices[plan], device_id, prod, code, _now_str(), ch),
        )
    return get_order(order_id) or {}


def _normalize_channel_code(raw: str) -> str:
    import re

    code = (raw or "").strip().upper()
    if not code:
        return ""
    if not re.match(r"^P_[A-Z0-9_]{2,32}$", code):
        raise ValueError("invalid channel_code")
    return code


def list_orders(
    *,
    product: str = "",
    status: str = "",
    channel_code: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    where: list[str] = []
    args: list[Any] = []
    prod = (product or "").strip().lower()
    if prod in ("yizhi", "zhouyi"):
        where.append("product = ?")
        args.append(prod)
    st = (status or "").strip().lower()
    if st in ("pending", "paid", "free"):
        where.append("status = ?")
        args.append(st)
    ch = (channel_code or "").strip().upper()
    if ch == "__NONE__":
        where.append("(channel_code IS NULL OR channel_code = '')")
    elif ch:
        where.append("channel_code = ?")
        args.append(ch)
    if date_from.strip():
        where.append("created_at >= ?")
        args.append(date_from.strip())
    if date_to.strip():
        where.append("created_at <= ?")
        args.append(date_to.strip() + (" 23:59:59" if len(date_to.strip()) == 10 else ""))
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    lim = max(1, min(int(limit), 500))
    off = max(0, int(offset))
    with connect() as conn:
        total = int(conn.execute(f"SELECT COUNT(*) FROM orders{clause}", args).fetchone()[0])
        rows = conn.execute(
            f"SELECT * FROM orders{clause} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [*args, lim, off],
        ).fetchall()
    return [dict(r) for r in rows], total


def channel_summaries(
    *,
    product: str = "",
    status: str = "paid",
) -> list[dict[str, Any]]:
    where = ["channel_code IS NOT NULL", "channel_code != ''"]
    args: list[Any] = []
    prod = (product or "").strip().lower()
    if prod in ("yizhi", "zhouyi"):
        where.append("product = ?")
        args.append(prod)
    st = (status or "").strip().lower()
    if st in ("pending", "paid"):
        where.append("status = ?")
        args.append(st)
    clause = " WHERE " + " AND ".join(where)
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT channel_code AS code,
                   COUNT(*) AS orders,
                   COALESCE(SUM(amount), 0) AS revenue,
                   SUM(CASE WHEN product = 'yizhi' THEN 1 ELSE 0 END) AS yizhi_orders,
                   SUM(CASE WHEN product = 'zhouyi' THEN 1 ELSE 0 END) AS zhouyi_orders,
                   COALESCE(SUM(CASE WHEN product = 'yizhi' THEN amount ELSE 0 END), 0) AS yizhi_revenue,
                   COALESCE(SUM(CASE WHEN product = 'zhouyi' THEN amount ELSE 0 END), 0) AS zhouyi_revenue
            FROM orders
            {clause}
            GROUP BY channel_code
            ORDER BY revenue DESC
            """,
            args,
        ).fetchall()
        promoters = {
            r["code"]: dict(r)
            for r in conn.execute("SELECT * FROM promoters").fetchall()
        }
    out: list[dict[str, Any]] = []
    for r in rows:
        code = str(r["code"])
        p = promoters.get(code) or {}
        rate = float(p.get("commission_rate") if p else 0.2)
        if rate < 0:
            rate = 0.0
        if rate > 1:
            rate = 1.0
        revenue = float(r["revenue"])
        out.append(
            {
                "code": code,
                "name": str(p.get("name") or ""),
                "commission_rate": rate,
                "orders": int(r["orders"]),
                "revenue": round(revenue, 2),
                "commission": round(revenue * rate, 2),
                "yizhi_orders": int(r["yizhi_orders"]),
                "zhouyi_orders": int(r["zhouyi_orders"]),
                "yizhi_revenue": round(float(r["yizhi_revenue"]), 2),
                "zhouyi_revenue": round(float(r["zhouyi_revenue"]), 2),
                "note": str(p.get("note") or ""),
            }
        )
    return out


def list_promoters() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM promoters ORDER BY code"
        ).fetchall()
    return [dict(r) for r in rows]


def upsert_promoter(
    code: str,
    *,
    name: str = "",
    commission_rate: float = 0.2,
    note: str = "",
) -> dict[str, Any]:
    c = _normalize_channel_code(code)
    if not c:
        raise ValueError("invalid channel_code")
    rate = float(commission_rate)
    if rate < 0 or rate > 1:
        raise ValueError("commission_rate must be 0..1")
    with connect() as conn:
        existing = conn.execute(
            "SELECT code FROM promoters WHERE code = ?", (c,)
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE promoters
                SET name = ?, commission_rate = ?, note = ?
                WHERE code = ?
                """,
                (name.strip(), rate, note.strip(), c),
            )
        else:
            conn.execute(
                """
                INSERT INTO promoters (code, name, commission_rate, note, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (c, name.strip(), rate, note.strip(), _now_str()),
            )
        row = conn.execute("SELECT * FROM promoters WHERE code = ?", (c,)).fetchone()
    return dict(row) if row else {"code": c, "name": name, "commission_rate": rate, "note": note}


def ensure_default_promoters() -> None:
    """幂等预置已知推广人。"""
    defaults = (
        ("P_ZHANGWENBO", "张文波", 0.2, "周易线下推广"),
        ("P_HUJIABING", "胡家兵", 0.2, "周易线下推广"),
    )
    with connect() as conn:
        for code, name, rate, note in defaults:
            row = conn.execute(
                "SELECT code FROM promoters WHERE code = ?", (code,)
            ).fetchone()
            if row:
                continue
            conn.execute(
                """
                INSERT INTO promoters (code, name, commission_rate, note, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (code, name, rate, note, _now_str()),
            )


def insert_feedback(
    *,
    feedback_id: str,
    html: str,
    subject: str = "",
    contact: str = "",
    app_version: str = "",
    device_id: str = "",
    client_ip: str = "",
    created_at: str | None = None,
) -> dict[str, Any]:
    fid = (feedback_id or "").strip() or uuid.uuid4().hex
    at = (created_at or "").strip() or _now_str()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO feedback (
              id, created_at, subject, contact, html,
              app_version, device_id, client_ip,
              mailed, mail_method, mail_error, mailed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, '', '', '')
            ON CONFLICT(id) DO UPDATE SET
              subject = excluded.subject,
              contact = excluded.contact,
              html = excluded.html,
              app_version = excluded.app_version,
              device_id = excluded.device_id,
              client_ip = excluded.client_ip
            """,
            (
                fid,
                at,
                (subject or "易知用户反馈")[:200],
                (contact or "")[:200],
                html or "",
                (app_version or "")[:40],
                (device_id or "")[:64],
                (client_ip or "")[:64],
            ),
        )
    return get_feedback(fid) or {"id": fid}


def get_feedback(feedback_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM feedback WHERE id = ?", (feedback_id,)
        ).fetchone()
    return _row_feedback(row) if row else None


def _row_feedback(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "created_at": row["created_at"] or "",
        "subject": row["subject"] or "",
        "contact": row["contact"] or "",
        "html": row["html"] or "",
        "app_version": row["app_version"] or "",
        "device_id": row["device_id"] or "",
        "client_ip": row["client_ip"] or "",
        "mailed": bool(row["mailed"]),
        "mail_method": row["mail_method"] or "",
        "mail_error": row["mail_error"] or "",
        "mailed_at": row["mailed_at"] or "",
    }


def update_feedback_mail(
    feedback_id: str,
    *,
    mailed: bool,
    method: str = "",
    error: str = "",
) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE feedback
            SET mailed = ?, mail_method = ?, mail_error = ?, mailed_at = ?
            WHERE id = ?
            """,
            (
                1 if mailed else 0,
                (method or "")[:40],
                (error or "")[:500],
                _now_str() if mailed else "",
                feedback_id,
            ),
        )


def list_feedback(
    *,
    limit: int = 50,
    offset: int = 0,
    mailed: int | None = None,
) -> dict[str, Any]:
    limit = max(1, min(200, int(limit)))
    offset = max(0, int(offset))
    where = ""
    params: list[Any] = []
    if mailed is not None:
        where = "WHERE mailed = ?"
        params.append(1 if mailed else 0)
    with connect() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM feedback {where}", params
        ).fetchone()["n"]
        rows = conn.execute(
            f"""
            SELECT * FROM feedback {where}
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
    return {
        "total": total,
        "items": [_row_feedback(r) for r in rows],
        "limit": limit,
        "offset": offset,
    }


def get_order(order_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    return dict(row) if row else None


def set_order_qr(order_id: str, qr_url: str, pay_trade_no: str = "") -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE orders SET qr_url = ?, pay_trade_no = ? WHERE id = ?",
            (qr_url, pay_trade_no, order_id),
        )


def mark_order_paid(order_id: str, pay_trade_no: str = "") -> dict[str, Any] | None:
    order = get_order(order_id)
    if not order or order["status"] == "paid":
        return order
    with connect() as conn:
        conn.execute(
            "UPDATE orders SET status = 'paid', paid_at = ?, pay_trade_no = COALESCE(NULLIF(?, ''), pay_trade_no) WHERE id = ?",
            (_now_str(), pay_trade_no, order_id),
        )
    log_event("order_paid", order_id)
    issue_license_for_order(order_id)
    return get_order(order_id)


def mark_order_free(order_id: str) -> dict[str, Any] | None:
    """待付订单改为免费：金额 0、状态 free，并发放授权。"""
    order = get_order(order_id)
    if not order:
        return None
    if order["status"] == "free":
        return order
    if order["status"] != "pending":
        raise ValueError("only pending orders can be marked free")
    with connect() as conn:
        conn.execute(
            """
            UPDATE orders
            SET status = 'free', amount = 0, paid_at = ?
            WHERE id = ? AND status = 'pending'
            """,
            (_now_str(), order_id),
        )
    log_event("order_free", order_id)
    issue_license_for_order(order_id)
    return get_order(order_id)


def delete_order(order_id: str) -> bool:
    """取消订单：删除记录（仅待付）。"""
    order = get_order(order_id)
    if not order:
        return False
    if order["status"] != "pending":
        raise ValueError("only pending orders can be cancelled")
    with connect() as conn:
        conn.execute("DELETE FROM orders WHERE id = ? AND status = 'pending'", (order_id,))
        deleted = conn.total_changes > 0
    if deleted:
        log_event("order_cancelled", order_id)
    return deleted


def get_active_license(device_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM licenses
            WHERE device_id = ? AND status = 'active'
            ORDER BY expires_at DESC LIMIT 1
            """,
            (device_id,),
        ).fetchone()
    if not row:
        return None
    exp = datetime.strptime(row["expires_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=BEIJING)
    if exp.timestamp() < _now_ts():
        return None
    return dict(row)


def get_license_by_id(license_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM licenses WHERE id = ?", (license_id,)).fetchone()
    return dict(row) if row else None


def issue_license_for_order(order_id: str) -> dict[str, Any] | None:
    order = get_order(order_id)
    if not order or order["status"] not in ("paid", "free"):
        return None
    device_id = order["device_id"]
    plan = order["plan"]
    existing = get_active_license(device_id)
    starts = datetime.now(BEIJING)
    if existing and existing["device_id"] == device_id:
        base = datetime.strptime(existing["expires_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=BEIJING)
        if base.timestamp() > _now_ts():
            starts = base
    expires = compute_expires_at(plan, starts)
    license_id = uuid.uuid4().hex[:16]
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO licenses (id, order_id, device_id, plan, starts_at, expires_at, status)
            VALUES (?, ?, ?, ?, ?, ?, 'active')
            """,
            (
                license_id,
                order_id,
                device_id,
                plan,
                starts.strftime("%Y-%m-%d %H:%M:%S"),
                expires.strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
    log_event("license_issued", f"{license_id} device={device_id}")
    return get_license_by_id(license_id)


def activate_with_code(code: str, device_id: str) -> dict[str, Any] | None:
    code = code.strip().upper()
    conflict = get_active_license(device_id)
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM activation_codes WHERE code = ? AND used = 0",
            (code,),
        ).fetchone()
    if not row:
        return None
    plan = row["plan"]
    if conflict and conflict.get("device_id") == device_id:
        starts = datetime.now(BEIJING)
        base = datetime.strptime(conflict["expires_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=BEIJING)
        if base.timestamp() > _now_ts():
            starts = base
    else:
        starts = datetime.now(BEIJING)
    expires = compute_expires_at(plan, starts)
    license_id = uuid.uuid4().hex[:16]
    with connect() as conn:
        conn.execute(
            "UPDATE activation_codes SET used = 1, license_id = ? WHERE code = ?",
            (license_id, code),
        )
        conn.execute(
            """
            INSERT INTO licenses (id, order_id, device_id, plan, starts_at, expires_at, status)
            VALUES (?, '', ?, ?, ?, ?, 'active')
            """,
            (
                license_id,
                device_id,
                plan,
                starts.strftime("%Y-%m-%d %H:%M:%S"),
                expires.strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
    return get_license_by_id(license_id)


def activate_order(order_id: str, device_id: str) -> dict[str, Any]:
    order = get_order(order_id)
    if not order:
        raise ValueError("order_not_found")
    if order["status"] != "paid":
        raise ValueError("order_not_paid")
    if order["device_id"] and order["device_id"] != device_id:
        raise ValueError("device_mismatch")
    lic = get_license_by_id_for_order(order_id)
    if lic:
        if lic["device_id"] != device_id:
            raise ValueError("already_bound_other")
        return lic
    active = get_active_license(device_id)
    if active and active.get("order_id") != order_id:
        raise ValueError("device_conflict")
    with connect() as conn:
        bound = conn.execute(
            "SELECT device_id FROM licenses WHERE order_id = ? AND status = 'active'",
            (order_id,),
        ).fetchone()
    if bound and bound["device_id"] != device_id:
        raise ValueError("already_bound_other")
    if not order["device_id"]:
        with connect() as conn:
            conn.execute("UPDATE orders SET device_id = ? WHERE id = ?", (device_id, order_id))
    issued = issue_license_for_order(order_id)
    if not issued:
        raise ValueError("issue_failed")
    return issued


def get_license_by_id_for_order(order_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM licenses WHERE order_id = ? AND status = 'active' ORDER BY expires_at DESC LIMIT 1",
            (order_id,),
        ).fetchone()
    return dict(row) if row else None


def heartbeat(license_id: str, device_id: str) -> dict[str, Any]:
    lic = get_license_by_id(license_id)
    if not lic or lic["status"] != "active":
        raise ValueError("license_revoked")
    if lic["device_id"] != device_id:
        raise ValueError("device_mismatch")
    exp = datetime.strptime(lic["expires_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=BEIJING)
    if exp.timestamp() < _now_ts():
        raise ValueError("expired")
    now = _now_str()
    with connect() as conn:
        conn.execute(
            "UPDATE licenses SET last_seen_at = ? WHERE id = ?",
            (now, license_id),
        )
    updated = get_license_by_id(license_id)
    return updated or lic


def unbind_license(license_id: str = "", device_id: str = "") -> bool:
    with connect() as conn:
        if license_id:
            row = conn.execute("SELECT * FROM licenses WHERE id = ?", (license_id,)).fetchone()
        elif device_id:
            row = conn.execute(
                "SELECT * FROM licenses WHERE device_id = ? AND status = 'active' ORDER BY expires_at DESC LIMIT 1",
                (device_id,),
            ).fetchone()
        else:
            return False
        if not row:
            return False
        conn.execute(
            "UPDATE licenses SET status = 'revoked', device_id = '' WHERE id = ?",
            (row["id"],),
        )
    log_event("license_unbound", row["id"])
    return True


def self_unbind(license_id: str, device_id: str) -> bool:
    """Allow user to unbind once per calendar year (for device change)."""
    lic = get_license_by_id(license_id)
    if not lic or lic["status"] != "active" or lic["device_id"] != device_id:
        raise ValueError("license_not_found")
    year = datetime.now(BEIJING).year
    used = int(lic.get("unbind_count") or 0)
    unbind_year = int(lic.get("unbind_year") or 0)
    limit = unbind_per_year()
    if unbind_year == year and used >= limit:
        raise ValueError("unbind_limit_exceeded")
    with connect() as conn:
        count = used + 1 if unbind_year == year else 1
        conn.execute(
            """
            UPDATE licenses
            SET status = 'revoked', device_id = '', unbind_count = ?, unbind_year = ?
            WHERE id = ?
            """,
            (count, year, license_id),
        )
    log_event("license_self_unbound", f"{license_id} count={count}")
    return True


def create_activation_code(plan: str) -> str:
    code = secrets.token_hex(4).upper()
    with connect() as conn:
        conn.execute(
            "INSERT INTO activation_codes (code, plan, created_at) VALUES (?, ?, ?)",
            (code, plan, _now_str()),
        )
    return code


def license_expires_ts(lic: dict[str, Any]) -> int:
    exp = datetime.strptime(lic["expires_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=BEIJING)
    return int(exp.timestamp())
