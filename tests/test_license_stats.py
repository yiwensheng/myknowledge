"""Unit tests for license-server/app/stats.py."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "license-server"))

from app.stats import (  # noqa: E402
    active_devices,
    compute_stats,
    export_all_rows,
    format_stats_text,
    revenue_by_period,
)

BEIJING = timezone(timedelta(hours=8))


def _now() -> str:
    return datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M:%S")


def _seed_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE orders (
          id TEXT PRIMARY KEY, plan TEXT, amount REAL, status TEXT,
          device_id TEXT, pay_trade_no TEXT, qr_url TEXT, activation_code TEXT,
          created_at TEXT, paid_at TEXT
        );
        CREATE TABLE licenses (
          id TEXT PRIMARY KEY, order_id TEXT, device_id TEXT, plan TEXT,
          starts_at TEXT, expires_at TEXT, status TEXT,
          unbind_count INTEGER, unbind_year INTEGER, last_seen_at TEXT
        );
        CREATE TABLE activation_codes (
          code TEXT PRIMARY KEY, plan TEXT, used INTEGER, license_id TEXT, created_at TEXT
        );
        CREATE TABLE events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, detail TEXT, at TEXT
        );
        """
    )
    now = _now()
    yesterday = (datetime.now(BEIJING) - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    week_ago = (datetime.now(BEIJING) - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
    future = (datetime.now(BEIJING) + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")

    conn.execute(
        "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("o1", "month", 29.0, "paid", "dev-a", "", "", "CODE1", now, now),
    )
    conn.execute(
        "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("o2", "year", 299.0, "paid", "dev-b", "", "", "CODE2", now, yesterday),
    )
    conn.execute(
        "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("o3", "lifetime", 199.0, "pending", "dev-c", "", "", "CODE3", now, ""),
    )
    conn.execute(
        "INSERT INTO licenses VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("l1", "o1", "dev-a", "month", now, future, "active", 0, 0, now),
    )
    conn.execute(
        "INSERT INTO licenses VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("l2", "o2", "dev-b", "year", now, future, "active", 0, 0, week_ago),
    )
    conn.execute(
        "INSERT INTO activation_codes VALUES (?,?,?,?,?)",
        ("ABCD1234", "year", 0, "", now),
    )
    conn.execute(
        "INSERT INTO events (kind, detail, at) VALUES (?,?,?)",
        ("order_paid", "o1", now),
    )
    conn.commit()
    conn.close()


class LicenseStatsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name
        _seed_db(Path(self.db_path))

    def tearDown(self) -> None:
        Path(self.db_path).unlink(missing_ok=True)

    def test_revenue_by_month(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = revenue_by_period(conn, "month")
        conn.close()
        self.assertEqual(len(rows), 2)
        total = sum(r["revenue"] for r in rows)
        self.assertAlmostEqual(total, 328.0)

    def test_active_devices(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        d7 = active_devices(conn, 7)
        d30 = active_devices(conn, 30)
        conn.close()
        self.assertTrue(d7["available"])
        self.assertEqual(d7["count"], 1)
        self.assertEqual(d30["count"], 2)

    def test_compute_and_format(self) -> None:
        stats = compute_stats(self.db_path, period="month")
        self.assertEqual(stats["active_subscriptions"]["total"], 2)
        self.assertEqual(stats["pending_orders"]["count"], 1)
        self.assertAlmostEqual(stats["revenue_total"]["revenue"], 328.0)
        text = format_stats_text(stats)
        self.assertIn("有效订阅", text)
        self.assertIn("累计收入", text)
        self.assertIn("活跃设备", text)

    def test_export_includes_events(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = export_all_rows(conn)
        conn.close()
        tables = {r["_table"] for r in rows}
        self.assertIn("events", tables)


if __name__ == "__main__":
    unittest.main()
