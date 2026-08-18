"""Send product feedback email (SMTP preferred, agently-cli fallback)."""

from __future__ import annotations

import json
import os
import shutil
import smtplib
import subprocess
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any


def feedback_to() -> str:
    return os.environ.get("FEEDBACK_TO", "ywsay@126.com").strip() or "ywsay@126.com"


def feedback_from() -> str:
    return (
        os.environ.get("FEEDBACK_FROM", "").strip()
        or os.environ.get("FEEDBACK_SMTP_USER", "").strip()
        or "suddly@agent.qq.com"
    )


def smtp_config() -> dict[str, Any]:
    host = os.environ.get("FEEDBACK_SMTP_HOST", "").strip()
    user = os.environ.get("FEEDBACK_SMTP_USER", "").strip()
    password = os.environ.get("FEEDBACK_SMTP_PASSWORD", "").strip()
    try:
        port = int(os.environ.get("FEEDBACK_SMTP_PORT", "465").strip() or "465")
    except ValueError:
        port = 465
    ssl = os.environ.get("FEEDBACK_SMTP_SSL", "1").strip().lower() not in ("0", "false", "no")
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "ssl": ssl,
        "ok": bool(host and user and password),
    }


def _find_agently() -> str | None:
    env = os.environ.get("FEEDBACK_AGENTLY_CLI", "").strip()
    if env and Path(env).is_file():
        return env
    which = shutil.which("agently-cli") or shutil.which("agently-cli.cmd")
    if which:
        return which
    npm = Path.home() / "AppData" / "Roaming" / "npm" / "agently-cli.cmd"
    if npm.is_file():
        return str(npm)
    exe = (
        Path.home()
        / "AppData"
        / "Roaming"
        / "npm"
        / "node_modules"
        / "@tencent-qqmail"
        / "agently-cli"
        / "node_modules"
        / "@tencent-qqmail"
        / "agently-cli-win32-x64"
        / "bin"
        / "agently-cli.exe"
    )
    if exe.is_file():
        return str(exe)
    return None


def _run_agently(
    args: list[str],
    timeout: int = 45,
    *,
    cwd: str | None = None,
) -> dict[str, Any]:
    cli = _find_agently()
    if not cli:
        raise RuntimeError("未找到 agently-cli，且未配置 FEEDBACK_SMTP_*")
    cmd = [cli, *args]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        cwd=cwd,
    )
    raw = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    data: dict[str, Any] = {}
    try:
        # CLI may print tip lines after JSON; take first JSON object
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        data = {"ok": False, "raw": raw[:500]}
    if proc.returncode not in (0, 8) and not data.get("ok"):
        msg = ""
        if isinstance(data.get("error"), dict):
            msg = str(data["error"].get("message") or "")
        raise RuntimeError(msg or raw[:400] or f"agently-cli exit {proc.returncode}")
    data["_exit"] = proc.returncode
    return data


def _send_smtp(*, subject: str, html: str, reply_to: str = "") -> None:
    cfg = smtp_config()
    if not cfg["ok"]:
        raise RuntimeError("SMTP 未配置")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = feedback_from()
    msg["To"] = feedback_to()
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.attach(MIMEText(html, "html", "utf-8"))
    if cfg["ssl"]:
        with smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=20) as smtp:
            smtp.login(cfg["user"], cfg["password"])
            smtp.sendmail(feedback_from(), [feedback_to()], msg.as_string())
    else:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=20) as smtp:
            smtp.starttls()
            smtp.login(cfg["user"], cfg["password"])
            smtp.sendmail(feedback_from(), [feedback_to()], msg.as_string())


def _extract_confirmation_token(data: dict[str, Any]) -> str:
    if data.get("confirmation_token"):
        return str(data["confirmation_token"])
    nested = data.get("data") if isinstance(data.get("data"), dict) else {}
    for key in ("confirmation_token", "token", "ctk"):
        if nested.get(key):
            return str(nested[key])
    # walk
    raw = json.dumps(data, ensure_ascii=False)
    import re

    m = re.search(r"ctk_[A-Za-z0-9_-]+", raw)
    return m.group(0) if m else ""


def _send_agently(*, subject: str, html: str) -> None:
    import tempfile

    # agently-cli 要求 --body-file 为相对路径
    tmp_dir = Path(tempfile.mkdtemp(prefix="yizhi-fb-"))
    body_name = "body.html"
    body_file = tmp_dir / body_name
    try:
        body_file.write_text(html, encoding="utf-8")
        args = [
            "message",
            "+send",
            "--to",
            feedback_to(),
            "--subject",
            subject,
            "--body-file",
            body_name,
        ]
        first = _run_agently(args, cwd=str(tmp_dir))
        if first.get("_exit") == 0 and first.get("ok"):
            return
        token = _extract_confirmation_token(first)
        if not token:
            if first.get("ok"):
                return
            raise RuntimeError(
                "agently 未返回 confirmation-token，无法完成发送: "
                + str(first.get("raw") or first)[:200]
            )
        second = _run_agently([*args, "--confirmation-token", token], cwd=str(tmp_dir))
        if second.get("_exit") != 0 and not second.get("ok"):
            raise RuntimeError("agently 确认发送失败")
    finally:
        try:
            body_file.unlink(missing_ok=True)
            tmp_dir.rmdir()
        except OSError:
            pass


def send_feedback_email(
    *,
    subject: str,
    html: str,
    reply_to: str = "",
    meta_text: str = "",
) -> str:
    """Send feedback. Returns method used: smtp | agently."""
    body = html
    if meta_text:
        body = f"{html}<hr><pre style='font-size:12px;color:#666'>{meta_text}</pre>"
    if smtp_config()["ok"]:
        _send_smtp(subject=subject, html=body, reply_to=reply_to)
        return "smtp"
    if _find_agently():
        _send_agently(subject=subject, html=body)
        return "agently"
    raise RuntimeError(
        "未配置发信：请在 license-server/.env 设置 FEEDBACK_SMTP_HOST/USER/PASSWORD，"
        "或在服务器安装并登录 agently-cli（suddly@agent.qq.com）"
    )


def mail_ready() -> dict[str, Any]:
    return {
        "smtp": smtp_config()["ok"],
        "agently": bool(_find_agently()),
        "to": feedback_to(),
        "from": feedback_from(),
    }
