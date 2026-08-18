#!/usr/bin/env python3
"""扩展授权联调：订单、激活码、解绑。"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

SERVER = os.environ.get("TEST_LICENSE_SERVER", "http://127.0.0.1:18888")
ADMIN = os.environ.get("LICENSE_ADMIN_KEY", "dev-admin")
SECRET = os.environ.get("LICENSE_JWT_SECRET", "dev-insecure-change-me")
DEVICE_A = "testdevice" + "0" * 22
DEVICE_B = "testdevice" + "1" * 22
DEVICE_C = "testdevice" + "2" * 22


def _post(path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{SERVER}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _get(path: str) -> dict:
    req = urllib.request.Request(f"{SERVER}{path}", method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def test_order_activate_flow() -> None:
    health = _get("/health")
    assert health.get("ok"), health

    order = _post("/license/create-order", {"plan": "month", "device_id": DEVICE_A})
    oid = order["order_id"]
    _post("/admin/mark-paid", {"admin_key": ADMIN, "order_id": oid})
    polled = _get(f"/license/order/{oid}")
    assert polled.get("status") == "paid", polled

    act = _post("/license/activate", {"order_id": oid, "device_id": DEVICE_A})
    token = act.get("token")
    assert token, act

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "license-server"))
    from app.jwt_utils import verify_token

    payload = verify_token(token, SECRET)
    assert payload and payload.get("device_id") == DEVICE_A, payload

    hb = _post("/license/heartbeat", {"token": token, "device_id": DEVICE_A})
    assert hb.get("ok"), hb


def test_activation_code() -> None:
    code_resp = _post("/admin/create-code", {"admin_key": ADMIN, "plan": "year"})
    code = code_resp.get("code")
    assert code, code_resp
    # activate endpoint via client uses order or code - server has activate with code?
    # Check license-server main for code activation path
    act = _post("/license/activate", {"code": code, "device_id": DEVICE_C})
    assert act.get("token") or act.get("license_id"), act


def test_unbind() -> None:
    order = _post("/license/create-order", {"plan": "month", "device_id": DEVICE_B})
    oid = order["order_id"]
    _post("/admin/mark-paid", {"admin_key": ADMIN, "order_id": oid})
    act = _post("/license/activate", {"order_id": oid, "device_id": DEVICE_B})
    lid = act.get("license_id")
    assert lid, act
    ok = _post("/admin/unbind", {"admin_key": ADMIN, "license_id": lid})
    assert ok.get("ok") is not False, ok


def main() -> int:
    tests = [
        ("order_activate", test_order_activate_flow),
        ("activation_code", test_activation_code),
        ("unbind", test_unbind),
    ]
    for name, fn in tests:
        print(f"RUN {name}…")
        fn()
        print(f"  OK {name}")
    print("OK all license flow tests")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        print("FAIL:", exc, file=sys.stderr)
        raise SystemExit(1) from exc
