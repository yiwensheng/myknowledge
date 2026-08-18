"""Read-only license DB analytics for admin CLI and API."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

BEIJING = timezone(timedelta(hours=8))

PLAN_LABELS = {
    "month": "月付",
    "year": "年付",
    "lifetime": "终身",
}

ALL_TABLES = ("orders", "licenses", "activation_codes", "events")

PERIOD_SQL = {
    "day": "date(paid_at)",
    "week": "strftime('%Y-W%W', paid_at)",
    "month": "strftime('%Y-%m', paid_at)",
    "quarter": (
        "strftime('%Y', paid_at) || '-Q' || "
        "((CAST(strftime('%m', paid_at) AS INTEGER) - 1) / 3 + 1)"
    ),
    "year": "strftime('%Y', paid_at)",
}


def _now_str() -> str:
    return datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M:%S")


def _plan_label(plan: str) -> str:
    return PLAN_LABELS.get(plan, plan)


def open_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def licenses_has_last_seen(conn: sqlite3.Connection) -> bool:
    if not table_exists(conn, "licenses"):
        return False
    cols = {r[1] for r in conn.execute("PRAGMA table_info(licenses)").fetchall()}
    return "last_seen_at" in cols


def active_subscriptions(conn: sqlite3.Connection) -> tuple[list[dict[str, Any]], int]:
    now = _now_str()
    rows = conn.execute(
        """
        SELECT plan, COUNT(*) AS count
        FROM licenses
        WHERE status = 'active'
          AND device_id != ''
          AND expires_at > ?
        GROUP BY plan
        ORDER BY plan
        """,
        (now,),
    ).fetchall()
    items = [
        {
            "plan": r["plan"],
            "plan_label": _plan_label(r["plan"]),
            "count": int(r["count"]),
        }
        for r in rows
    ]
    total = sum(x["count"] for x in items)
    return items, total


def pending_orders(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT plan, COUNT(*) AS count, COALESCE(SUM(amount), 0) AS amount
        FROM orders
        WHERE status = 'pending'
        GROUP BY plan
        """
    ).fetchall()
    by_plan = [
        {
            "plan": r["plan"],
            "plan_label": _plan_label(r["plan"]),
            "count": int(r["count"]),
            "amount": float(r["amount"]),
        }
        for r in rows
    ]
    return {
        "count": sum(x["count"] for x in by_plan),
        "amount": round(sum(x["amount"] for x in by_plan), 2),
        "by_plan": by_plan,
    }


def revenue_by_period(
    conn: sqlite3.Connection,
    period: str,
) -> list[dict[str, Any]]:
    if period not in PERIOD_SQL:
        raise ValueError(f"invalid period: {period}")
    expr = PERIOD_SQL[period]
    rows = conn.execute(
        f"""
        SELECT {expr} AS period, plan,
               COUNT(*) AS orders, COALESCE(SUM(amount), 0) AS revenue
        FROM orders
        WHERE status = 'paid' AND paid_at != ''
        GROUP BY period, plan
        ORDER BY period DESC, plan
        """
    ).fetchall()
    return [
        {
            "period": r["period"],
            "plan": r["plan"],
            "plan_label": _plan_label(r["plan"]),
            "orders": int(r["orders"]),
            "revenue": round(float(r["revenue"]), 2),
        }
        for r in rows
    ]


def revenue_totals(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT COUNT(*) AS orders, COALESCE(SUM(amount), 0) AS revenue
        FROM orders WHERE status = 'paid'
        """
    ).fetchone()
    by_plan_rows = conn.execute(
        """
        SELECT plan, COUNT(*) AS orders, COALESCE(SUM(amount), 0) AS revenue
        FROM orders WHERE status = 'paid'
        GROUP BY plan ORDER BY plan
        """
    ).fetchall()
    by_product_rows = conn.execute(
        """
        SELECT COALESCE(NULLIF(product, ''), 'yizhi') AS product,
               COUNT(*) AS orders, COALESCE(SUM(amount), 0) AS revenue
        FROM orders WHERE status = 'paid'
        GROUP BY COALESCE(NULLIF(product, ''), 'yizhi')
        ORDER BY product
        """
    ).fetchall()
    product_labels = {"yizhi": "易知", "zhouyi": "周易卦象"}
    return {
        "orders": int(row["orders"]),
        "revenue": round(float(row["revenue"]), 2),
        "by_plan": [
            {
                "plan": r["plan"],
                "plan_label": _plan_label(r["plan"]),
                "orders": int(r["orders"]),
                "revenue": round(float(r["revenue"]), 2),
            }
            for r in by_plan_rows
        ],
        "by_product": [
            {
                "product": r["product"],
                "product_label": product_labels.get(r["product"], r["product"]),
                "orders": int(r["orders"]),
                "revenue": round(float(r["revenue"]), 2),
            }
            for r in by_product_rows
        ],
    }


def pending_orders_by_product(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    product_labels = {"yizhi": "易知", "zhouyi": "周易卦象"}
    rows = conn.execute(
        """
        SELECT COALESCE(NULLIF(product, ''), 'yizhi') AS product,
               COUNT(*) AS count, COALESCE(SUM(amount), 0) AS amount
        FROM orders WHERE status = 'pending'
        GROUP BY COALESCE(NULLIF(product, ''), 'yizhi')
        ORDER BY product
        """
    ).fetchall()
    return [
        {
            "product": r["product"],
            "product_label": product_labels.get(r["product"], r["product"]),
            "count": int(r["count"]),
            "amount": round(float(r["amount"]), 2),
        }
        for r in rows
    ]


def new_licenses_by_month(conn: sqlite3.Connection, limit: int = 12) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT strftime('%Y-%m', starts_at) AS month, plan, COUNT(*) AS count
        FROM licenses
        WHERE starts_at != ''
        GROUP BY month, plan
        ORDER BY month DESC, plan
        LIMIT ?
        """,
        (limit * 3,),
    ).fetchall()
    return [
        {
            "month": r["month"],
            "plan": r["plan"],
            "plan_label": _plan_label(r["plan"]),
            "count": int(r["count"]),
        }
        for r in rows
    ]


def active_devices(conn: sqlite3.Connection, days: int) -> dict[str, Any]:
    """Devices with heartbeat within N days (requires last_seen_at column)."""
    if not licenses_has_last_seen(conn):
        return {
            "available": False,
            "days": days,
            "count": 0,
            "note": "数据库尚无 last_seen_at，请部署新版授权服务并重启后再统计",
        }
    cutoff = (datetime.now(BEIJING) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT device_id) AS count
        FROM licenses
        WHERE status = 'active'
          AND device_id != ''
          AND last_seen_at != ''
          AND last_seen_at >= ?
        """,
        (cutoff,),
    ).fetchone()
    never = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM licenses
        WHERE status = 'active'
          AND device_id != ''
          AND (last_seen_at IS NULL OR last_seen_at = '')
        """
    ).fetchone()
    return {
        "available": True,
        "days": days,
        "count": int(row["count"]),
        "active_bound_never_seen": int(never["count"]),
    }


def activation_codes_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT plan,
               SUM(CASE WHEN used = 0 THEN 1 ELSE 0 END) AS unused,
               SUM(CASE WHEN used = 1 THEN 1 ELSE 0 END) AS used
        FROM activation_codes
        GROUP BY plan
        """
    ).fetchall()
    by_plan = [
        {
            "plan": r["plan"],
            "plan_label": _plan_label(r["plan"]),
            "unused": int(r["unused"]),
            "used": int(r["used"]),
        }
        for r in rows
    ]
    return {
        "unused": sum(x["unused"] for x in by_plan),
        "used": sum(x["used"] for x in by_plan),
        "by_plan": by_plan,
    }


def compute_stats(
    db_path: str,
    *,
    period: str = "month",
    active_days: int = 30,
) -> dict[str, Any]:
    from .db import ensure_db_schema_at

    ensure_db_schema_at(db_path)
    conn = open_db(db_path)
    try:
        subs, subs_total = active_subscriptions(conn)
        stats = {
            "generated_at": _now_str(),
            "db_path": db_path,
            "active_subscriptions": {
                "total": subs_total,
                "by_plan": subs,
            },
            "pending_orders": pending_orders(conn),
            "pending_orders_by_product": pending_orders_by_product(conn),
            "revenue_total": revenue_totals(conn),
            "revenue_by_period": {
                "period": period,
                "rows": revenue_by_period(conn, period),
            },
            "new_licenses_by_month": new_licenses_by_month(conn),
            "activation_codes": activation_codes_summary(conn),
            "active_devices": {
                "7d": active_devices(conn, 7),
                "30d": active_devices(conn, active_days),
            },
        }
        if period != "month":
            stats["revenue_by_month"] = {
                "period": "month",
                "rows": revenue_by_period(conn, "month"),
            }
        return stats
    finally:
        conn.close()


def format_stats_text(stats: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"易知授权统计  （生成于 {stats['generated_at']} 北京时间）")
    lines.append("")

    subs = stats["active_subscriptions"]
    lines.append(f"【有效订阅】合计 {subs['total']} 个（已绑设备且未过期）")
    for item in subs["by_plan"]:
        lines.append(f"  · {item['plan_label']} ({item['plan']}): {item['count']}")
    if subs["total"] == 0:
        lines.append("  （无）")

    pending = stats["pending_orders"]
    lines.append("")
    lines.append(f"【待支付订单】{pending['count']} 笔，合计 ¥{pending['amount']:.2f}")

    rev = stats["revenue_total"]
    lines.append("")
    lines.append(f"【累计收入（已支付）】¥{rev['revenue']:.2f}，共 {rev['orders']} 笔")
    for item in rev["by_plan"]:
        lines.append(
            f"  · {item['plan_label']}: {item['orders']} 笔 / ¥{item['revenue']:.2f}"
        )

    rb = stats["revenue_by_period"]
    period_label = {
        "day": "日",
        "week": "周",
        "month": "月",
        "quarter": "季",
        "year": "年",
    }.get(rb["period"], rb["period"])
    lines.append("")
    lines.append(f"【按{period_label}收入】")
    if not rb["rows"]:
        lines.append("  （无已支付订单）")
    else:
        current_period = None
        period_total = 0.0
        period_orders = 0
        for row in rb["rows"]:
            if row["period"] != current_period:
                if current_period is not None:
                    lines.append(
                        f"  小计 {current_period}: {period_orders} 笔 / ¥{period_total:.2f}"
                    )
                    lines.append("")
                current_period = row["period"]
                period_total = 0.0
                period_orders = 0
            lines.append(
                f"  {row['period']}  {row['plan_label']}: "
                f"{row['orders']} 笔 / ¥{row['revenue']:.2f}"
            )
            period_total += row["revenue"]
            period_orders += row["orders"]
        if current_period is not None:
            lines.append(
                f"  小计 {current_period}: {period_orders} 笔 / ¥{period_total:.2f}"
            )

    lines.append("")
    lines.append("【近月新增授权】")
    month_rows = stats.get("new_licenses_by_month") or []
    if not month_rows:
        lines.append("  （无）")
    else:
        current_month = None
        for row in month_rows[:15]:
            if row["month"] != current_month:
                if current_month is not None:
                    lines.append("")
                lines.append(f"  {row['month']}")
                current_month = row["month"]
            lines.append(f"    {row['plan_label']}: +{row['count']}")

    codes = stats["activation_codes"]
    lines.append("")
    lines.append(
        f"【激活码】未使用 {codes['unused']} / 已使用 {codes['used']}"
    )

    ad7 = stats["active_devices"]["7d"]
    ad30 = stats["active_devices"]["30d"]
    lines.append("")
    lines.append("【活跃设备（heartbeat 联网）】")
    for label, block in (("7 天内", ad7), ("30 天内", ad30)):
        if not block.get("available"):
            lines.append(f"  {label}: {block.get('note', '不可用')}")
        else:
            lines.append(f"  {label}: {block['count']} 台")
    if ad30.get("available") and ad30.get("active_bound_never_seen"):
        lines.append(
            f"  已绑设备但从未 heartbeat: {ad30['active_bound_never_seen']} 台"
        )

    return "\n".join(lines)


def export_table_rows(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    if table not in ALL_TABLES:
        raise ValueError(f"unknown table: {table}")
    if not table_exists(conn, table):
        return []
    return [dict(r) for r in conn.execute(f"SELECT * FROM {table}")]


def export_all_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for table in ALL_TABLES:
        for row in export_table_rows(conn, table):
            tagged = {"_table": table, **row}
            rows.append(tagged)
    return rows
