"""Stable device fingerprint (SHA-256 hex, first 32 chars)."""

from __future__ import annotations

import hashlib
import os
import platform
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str]) -> str:
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True, timeout=5)
        return out.strip()
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        return ""


def _windows_parts() -> list[str]:
    parts: list[str] = []
    guid = _run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Cryptography' -Name MachineGuid).MachineGuid",
        ]
    )
    if guid:
        parts.append(guid)
    board = _run(["wmic", "baseboard", "get", "serialnumber"])
    for line in board.splitlines():
        line = line.strip()
        if line and line.lower() != "serialnumber":
            parts.append(line)
            break
    vol = _run(["wmic", "logicaldisk", "where", "DeviceID='C:'", "get", "VolumeSerialNumber"])
    for line in vol.splitlines():
        line = line.strip()
        if line and line.lower() != "volumeserialnumber":
            parts.append(line)
            break
    parts.append(platform.node())
    return parts


def _unix_parts() -> list[str]:
    parts: list[str] = [platform.node()]
    mid = Path("/etc/machine-id")
    if mid.is_file():
        parts.append(mid.read_text(encoding="utf-8").strip())
    return parts


def compute_device_id() -> str:
    env = os.environ.get("MYKNOWLEDGE_DEVICE_ID", "").strip()
    if env:
        return env[:64]
    if sys.platform == "win32":
        parts = _windows_parts()
    else:
        parts = _unix_parts()
    raw = "|".join(p for p in parts if p) or platform.platform()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
