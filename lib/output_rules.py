"""User-editable output rules appended from ask corrections."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .prompts import prompts_dir

RULES_FILE = "output-rules.md"
BEIJING = timezone(timedelta(hours=8))
MARKER = "<!-- rules below -->"
MAX_ENABLED_RULES = 20

_HEADING_RE = re.compile(
    r"^###\s+(?:(?P<id>r_[0-9a-f]{6,12})\s*·\s*)?(?P<title>.+?)\s*$",
    re.MULTILINE,
)
_ENABLED_RE = re.compile(r"<!--\s*enabled:\s*(true|false)\s*-->", re.I)


def _rules_path() -> Path:
    return prompts_dir() / RULES_FILE


def _default_template() -> str:
    return (
        "# 输出规则\n\n"
        "纠错、语气偏好与禁止表述会追加在下方；**提问**与**写文章**时会注入模型"
        "（仍须遵守「只许用检索片段」）。\n\n"
        f"{MARKER}\n"
    )


def ensure_rules_file() -> None:
    path = _rules_path()
    if path.is_file():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_default_template(), encoding="utf-8")


def read_rules_raw() -> str:
    ensure_rules_file()
    return _rules_path().read_text(encoding="utf-8")


def _new_rule_id() -> str:
    return "r_" + uuid.uuid4().hex[:8]


def _beijing_now() -> str:
    return datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M")


def _split_header_body(text: str) -> tuple[str, str]:
    if MARKER in text:
        head, body = text.split(MARKER, 1)
        return head.rstrip() + "\n\n" + MARKER + "\n", body.strip()
    lines = text.splitlines()
    body_lines: list[str] = []
    started = False
    head_lines: list[str] = []
    for line in lines:
        if not started and line.startswith("#"):
            head_lines.append(line)
            continue
        if not started and not line.strip():
            head_lines.append(line)
            continue
        started = True
        body_lines.append(line)
    head = "\n".join(head_lines).rstrip()
    if MARKER not in head:
        head = _default_template().rstrip()
    return head + "\n", "\n".join(body_lines).strip()


def _parse_rule_block(heading_line: str, block_body: str) -> dict:
    enabled = True
    em = _ENABLED_RE.search(heading_line)
    if em:
        enabled = em.group(1).lower() == "true"
        heading_clean = _ENABLED_RE.sub("", heading_line).rstrip()
    else:
        heading_clean = heading_line

    m = re.match(
        r"^###\s+(?:(?P<id>r_[0-9a-f]{6,12})\s*·\s*)?(?P<title>.+)$",
        heading_clean.strip(),
    )
    rid = (m.group("id") if m else None) or ""
    title = (m.group("title") if m else heading_clean.replace("###", "", 1).strip()).strip()

    question = ""
    rule_text = ""
    for line in block_body.splitlines():
        s = line.strip()
        if s.startswith("- **触发问题**：") or s.startswith("- **触发问题**:"):
            question = s.split("：", 1)[-1].split(":", 1)[-1].strip()
        elif s.startswith("- **规则**：") or s.startswith("- **规则**:"):
            rule_text = s.split("：", 1)[-1].split(":", 1)[-1].strip()
        elif not rule_text and s and not s.startswith("#"):
            # legacy freeform body
            rule_text = (rule_text + "\n" + s).strip() if rule_text else s

    at = ""
    am = re.search(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})", title)
    if am:
        at = am.group(1)

    return {
        "id": rid,
        "enabled": enabled,
        "title": title,
        "at": at,
        "question": question,
        "text": rule_text or block_body.strip(),
        "kind": "纠错" if "纠错" in title else ("偏好" if "偏好" in title else "规则"),
    }


def list_rules(*, migrate: bool = True) -> list[dict]:
    raw = read_rules_raw()
    _head, body = _split_header_body(raw)
    if not body.strip():
        return []

    matches = list(re.finditer(r"^###\s+.+$", body, flags=re.MULTILINE))
    rules: list[dict] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        chunk = body[start:end].strip()
        lines = chunk.splitlines()
        heading = lines[0]
        block_body = "\n".join(lines[1:]).strip()
        rules.append(_parse_rule_block(heading, block_body))

    dirty = False
    for r in rules:
        if not r["id"]:
            r["id"] = _new_rule_id()
            dirty = True
    if migrate and dirty:
        _write_rules(rules)
    return rules


def _format_rule_markdown(rule: dict) -> str:
    rid = rule["id"]
    at = rule.get("at") or _beijing_now()
    kind = rule.get("kind") or "纠错"
    enabled = "true" if rule.get("enabled", True) else "false"
    lines = [
        f"### {rid} · {at}（{kind}） <!-- enabled: {enabled} -->",
        "",
    ]
    q = (rule.get("question") or "").strip()
    if q:
        lines.append(f"- **触发问题**：{q}")
    lines.append(f"- **规则**：{(rule.get('text') or '').strip()}")
    lines.append("")
    return "\n".join(lines)


def _write_rules(rules: list[dict]) -> None:
    ensure_rules_file()
    path = _rules_path()
    head, _ = _split_header_body(path.read_text(encoding="utf-8"))
    if MARKER not in head:
        head = _default_template()
    parts = [head.rstrip(), ""]
    for r in rules:
        if not r.get("id"):
            r["id"] = _new_rule_id()
        parts.append(_format_rule_markdown(r))
    text = "\n".join(parts).rstrip() + "\n"
    tmp = path.with_suffix(".md.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def count_rules(text: str | None = None) -> int:
    if text is not None:
        _h, body = _split_header_body(text)
        if not body:
            return 0
        return len(re.findall(r"^###\s+", body, flags=re.MULTILINE))
    return len(list_rules(migrate=False))


def format_rules_block() -> str:
    rules = [r for r in list_rules(migrate=True) if r.get("enabled", True)]
    rules = rules[-MAX_ENABLED_RULES:]
    if not rules:
        return ""
    body = "\n".join(_format_rule_markdown(r).rstrip() for r in rules)
    return (
        "## 输出规则（用户纠错与偏好，优先级低于事实约束）\n"
        "以下规则用于语气、结构与风险提示；**不得**用规则要求编造检索片段中不存在的事实。\n\n"
        f"{body}"
    )


def append_rule(rule: str, *, question: str = "") -> dict:
    rule = (rule or "").strip()
    if not rule:
        raise ValueError("请填写要追加的规则")
    if len(rule) > 4000:
        raise ValueError("单条规则过长（上限 4000 字）")

    rules = list_rules(migrate=True)
    item = {
        "id": _new_rule_id(),
        "enabled": True,
        "title": f"{_beijing_now()}（纠错）",
        "at": _beijing_now(),
        "question": (question or "").strip(),
        "text": rule,
        "kind": "纠错",
    }
    rules.append(item)
    _write_rules(rules)
    try:
        from . import memory_db

        memory_db.append_audit("rule_create", "rule", item["id"], detail=rule[:120])
    except Exception:
        pass
    return {
        "ok": True,
        "path": str(_rules_path()),
        "id": item["id"],
        "rules_count": len(rules),
        "appended": _format_rule_markdown(item).strip(),
        "rules": rules,
    }


def update_rule(rule_id: str, *, text: str | None = None, enabled: bool | None = None, question: str | None = None) -> dict:
    rid = (rule_id or "").strip()
    rules = list_rules(migrate=True)
    found = None
    for r in rules:
        if r["id"] == rid:
            found = r
            break
    if not found:
        raise ValueError("规则不存在")
    if text is not None:
        t = text.strip()
        if not t:
            raise ValueError("规则正文不能为空")
        if len(t) > 4000:
            raise ValueError("单条规则过长（上限 4000 字）")
        found["text"] = t
    if question is not None:
        found["question"] = question.strip()
    if enabled is not None:
        found["enabled"] = bool(enabled)
        try:
            from . import memory_db

            memory_db.append_audit(
                "rule_enable" if found["enabled"] else "rule_disable",
                "rule",
                rid,
            )
        except Exception:
            pass
    _write_rules(rules)
    return {"ok": True, "rule": found, "rules_count": len(rules)}


def delete_rule(rule_id: str) -> dict:
    rid = (rule_id or "").strip()
    rules = list_rules(migrate=True)
    new_rules = [r for r in rules if r["id"] != rid]
    if len(new_rules) == len(rules):
        raise ValueError("规则不存在")
    _write_rules(new_rules)
    try:
        from . import memory_db

        memory_db.append_audit("rule_delete", "rule", rid)
    except Exception:
        pass
    return {"ok": True, "rules_count": len(new_rules)}


def get_rules_payload() -> dict:
    rules = list_rules(migrate=True)
    raw = read_rules_raw()
    enabled_n = sum(1 for r in rules if r.get("enabled", True))
    return {
        "path": str(_rules_path()),
        "content": raw,
        "rules": rules,
        "rules_count": len(rules),
        "rules_enabled": enabled_n,
        "preview_block": format_rules_block(),
    }
