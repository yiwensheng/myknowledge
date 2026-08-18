"""DB migration and heartbeat last_seen_at tests."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "license-server"))

from app import db  # noqa: E402


class DbMigrationTests(unittest.TestCase):
    def test_last_seen_on_heartbeat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_file = Path(tmp) / "test.db"
            import os

            os.environ["LICENSE_DB"] = str(db_file)
            order = db.create_order("month", "device" + "x" * 24)
            db.mark_order_paid(order["id"])
            lic = db.issue_license_for_order(order["id"])
            assert lic
            self.assertEqual(lic.get("last_seen_at", ""), "")

            updated = db.heartbeat(lic["id"], lic["device_id"])
            self.assertNotEqual(updated.get("last_seen_at", ""), "")

            conn = sqlite3.connect(db_file)
            cols = {r[1] for r in conn.execute("PRAGMA table_info(licenses)").fetchall()}
            conn.close()
            self.assertIn("last_seen_at", cols)


if __name__ == "__main__":
    unittest.main()
