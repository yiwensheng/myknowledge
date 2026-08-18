#!/usr/bin/env python3
"""易知授权服务管理 CLI（运维本地使用）."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
LICENSE_SERVER = ROOT / "license-server"
if str(LICENSE_SERVER) not in sys.path:
    sys.path.insert(0, str(LICENSE_SERVER))

from app.stats import (  # noqa: E402
    ALL_TABLES,
    compute_stats,
    export_all_rows,
    export_table_rows,
    format_stats_text,
    open_db,
)


def _post(server: str, path: str, body: dict) -> dict:
    url = f"{server.rstrip('/')}{path}"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get(server: str, path: str) -> dict:
    url = f"{server.rstrip('/')}{path}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _resolve_db_path(explicit: str) -> str:
    return explicit or os.environ.get("LICENSE_DB", str(ROOT / "license-server" / "license.db"))


def _write_csv(path: str, rows: list[dict]) -> None:
    if not rows:
        return
    fieldnames = sorted({k for r in rows for k in r.keys()})
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def cmd_export_csv(args: argparse.Namespace) -> int:
    db_path = _resolve_db_path(args.db)
    if not os.path.isfile(db_path):
        print(f"数据库不存在: {db_path}", file=sys.stderr)
        return 1
    from app.db import ensure_db_schema_at

    ensure_db_schema_at(db_path)
    conn = open_db(db_path)
    try:
        if args.split:
            out_dir = Path(args.split)
            out_dir.mkdir(parents=True, exist_ok=True)
            total = 0
            for table in ALL_TABLES:
                rows = export_table_rows(conn, table)
                if not rows:
                    continue
                out_path = out_dir / f"{table}.csv"
                _write_csv(str(out_path), rows)
                total += len(rows)
                print(f"  {table}: {len(rows)} 行 → {out_path}")
            if total == 0:
                print("无数据可导出", file=sys.stderr)
                return 1
            print(f"已分表导出 {total} 行 → {out_dir}")
            return 0

        rows = export_all_rows(conn)
    finally:
        conn.close()
    if not rows:
        print("无数据可导出", file=sys.stderr)
        return 1
    _write_csv(args.out, rows)
    print(f"已导出 {len(rows)} 行（含 events）→ {args.out}")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    db_path = _resolve_db_path(args.db)
    if not os.path.isfile(db_path):
        print(f"数据库不存在: {db_path}", file=sys.stderr)
        return 1
    stats = compute_stats(db_path, period=args.period, active_days=args.active_days)
    if args.format == "json":
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        print(format_stats_text(stats))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="易知授权管理")
    parser.add_argument(
        "--server",
        default=os.environ.get("MYKNOWLEDGE_LICENSE_SERVER", "http://127.0.0.1:18888"),
    )
    parser.add_argument("--admin-key", default=os.environ.get("LICENSE_ADMIN_KEY", "dev-admin"))
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_paid = sub.add_parser("mark-paid", help="标记订单已支付（联调）")
    p_paid.add_argument("order_id")

    p_unbind = sub.add_parser("unbind", help="解绑设备")
    p_unbind.add_argument("--license-id", default="")
    p_unbind.add_argument("--device-id", default="")

    p_code = sub.add_parser("create-code", help="生成离线激活码")
    p_code.add_argument("plan", choices=["month", "year", "lifetime"])

    sub.add_parser("health", help="健康检查")
    sub.add_parser("plans", help="查看套餐")

    p_export = sub.add_parser("export-csv", help="导出 license.db 为 CSV")
    p_export.add_argument("--out", default="license-export.csv", help="合并导出文件路径")
    p_export.add_argument(
        "--split",
        default="",
        help="分表导出到目录（orders/licenses/activation_codes/events 各一份）",
    )
    p_export.add_argument(
        "--db",
        default="",
        help="license.db 路径（默认 license-server/license.db 或 LICENSE_DB）",
    )

    p_stats = sub.add_parser("stats", help="订阅、收入与活跃设备统计")
    p_stats.add_argument(
        "--period",
        choices=["day", "week", "month", "quarter", "year"],
        default="month",
        help="收入分组粒度（默认 month）",
    )
    p_stats.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="输出格式",
    )
    p_stats.add_argument(
        "--active-days",
        type=int,
        default=30,
        help="活跃设备统计天数（默认 30）",
    )
    p_stats.add_argument("--db", default="", help="license.db 路径")

    args = parser.parse_args()
    server = args.server

    try:
        if args.cmd == "health":
            print(json.dumps(_get(server, "/health"), ensure_ascii=False, indent=2))
        elif args.cmd == "plans":
            print(json.dumps(_get(server, "/license/plans"), ensure_ascii=False, indent=2))
        elif args.cmd == "mark-paid":
            r = _post(server, "/admin/mark-paid", {"admin_key": args.admin_key, "order_id": args.order_id})
            print(json.dumps(r, ensure_ascii=False, indent=2))
        elif args.cmd == "unbind":
            if not args.license_id and not args.device_id:
                print("需要 --license-id 或 --device-id", file=sys.stderr)
                return 1
            r = _post(
                server,
                "/admin/unbind",
                {
                    "admin_key": args.admin_key,
                    "license_id": args.license_id,
                    "device_id": args.device_id,
                },
            )
            print(json.dumps(r, ensure_ascii=False, indent=2))
        elif args.cmd == "create-code":
            r = _post(
                server,
                "/admin/create-code",
                {"admin_key": args.admin_key, "plan": args.plan},
            )
            print(f"激活码: {r.get('code')}")
        elif args.cmd == "export-csv":
            return cmd_export_csv(args)
        elif args.cmd == "stats":
            return cmd_stats(args)
    except urllib.error.HTTPError as exc:
        print(exc.read().decode(), file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"无法连接 {server}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
