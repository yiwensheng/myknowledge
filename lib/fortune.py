"""知识黄历 / 今日知签 — 轻量情绪价值（非迷信方法论）。"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import load_dotenv, wiki_root
from .memory import get_evolution, memory_root

BEIJING = timezone(timedelta(hours=8))
SLIPS_FILE = "fortune_slips.jsonl"

# 宜：与知识库工作相关、可执行
_YI = [
    "整理一条闪念进笔记",
    "给一篇草稿补上出处",
    "把今日问答里有用的一句归档",
    "审一遍待整理草稿",
    "为重要笔记补标签或资料夹",
    "用提问核对一个模糊记忆",
    "写一小段可复用的产出提纲",
    "把外链资料收进库",
    "复查一处「待人工确认」",
    "清空 inbox 里最旧的一件",
]

# 忌：轻提醒，不恐吓
_JI = [
    "无出处就定稿入库",
    "一口气塞十个大文件不看摘要",
    "把猜测写成库内事实",
    "跳过冲突提示硬合并说法",
    "深夜连发未复核的长文",
    "清空规则只因一时不爽",
    "用预训练常识填库空缺",
    "把历史问答当新证据",
]

_CHECKLIST = [
    {"id": "grounded", "label": "结论能在检索片段里找到依据"},
    {"id": "conflicts", "label": "多源冲突已标出，未和稀泥"},
    {"id": "risks", "label": "「待人工确认」已过目"},
    {"id": "scope", "label": "未把库外常识写成库内事实"},
]


def fortune_enabled() -> bool:
    load_dotenv()
    raw = os.environ.get("MYKNOWLEDGE_FORTUNE", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def produce_ritual_enabled() -> bool:
    load_dotenv()
    raw = os.environ.get("MYKNOWLEDGE_PRODUCE_RITUAL", "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _today_ymd() -> str:
    return datetime.now(BEIJING).strftime("%Y-%m-%d")


def _seed_int(*parts: str) -> int:
    h = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return int(h[:12], 16)


def _pick(items: list[str], seed: int, n: int = 2) -> list[str]:
    if not items:
        return []
    out: list[str] = []
    x = seed
    used: set[int] = set()
    while len(out) < min(n, len(items)):
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        i = x % len(items)
        if i in used:
            continue
        used.add(i)
        out.append(items[i])
    return out


def daily_slip(*, root: Path | None = None) -> dict[str, Any]:
    """同一北京自然日内容稳定；与库名弱相关避免千库一面。"""
    root = root or wiki_root()
    day = _today_ymd()
    seed = _seed_int(day, str(root.resolve()), "slip")
    yi = _pick(_YI, seed, 2)
    ji = _pick(_JI, seed ^ 0xABCDEF, 2)
    motto_pool = [
        "先停一秒，再写进库。",
        "有依据的句子，比漂亮的句子更值钱。",
        "今日宜慢一点归档，忌假装已经核实。",
        "知识库长厚，靠的是可复查，不是堆字数。",
        "工作之余，给自己留一枚轻签，不耽误正事。",
    ]
    motto = motto_pool[seed % len(motto_pool)]
    return {
        "date": day,
        "yi": yi,
        "ji": ji,
        "motto": motto,
        "disclaimer": "知签是趣味提醒，不是操作规范；做事仍以检索依据为准。",
    }


def library_fortune(*, root: Path | None = None) -> dict[str, Any]:
    """基于真实进化统计的趣味解读，禁止夸大。"""
    evo = get_evolution(refresh=True, root=root)
    wd = evo.get("week_delta") or {}
    qa = int(wd.get("qa_added") or 0)
    arch = int(wd.get("archived_added") or 0)
    rules = int(wd.get("rules_added") or 0)
    total_qa = int(evo.get("qa_log_entries") or 0)
    drafts_hint = ""
    try:
        from .maintenance import list_draft_summary

        drafts = list_draft_summary(limit=5)
        n = int((drafts or {}).get("draft_total") or 0)
        if n >= 8:
            drafts_hint = f"待整理草稿约 {n} 篇，偏囤粮。"
        elif n >= 3:
            drafts_hint = f"待整理草稿约 {n} 篇，节奏正常。"
        else:
            drafts_hint = "待整理不多，库面较清。"
    except Exception:
        drafts_hint = "草稿量未统计。"

    lines: list[str] = []
    if qa == 0 and arch == 0:
        lines.append("近 7 日问答与归档都偏静，像在蓄力或外出。")
    elif qa >= 10:
        lines.append(f"近 7 日问答 {qa} 次，问得勤；记得把有用句落成笔记。")
    else:
        lines.append(f"近 7 日问答 {qa} 次、归档 {arch} 篇——用量如实如此。")
    if rules:
        lines.append(f"同期新增规则 {rules} 条，纠偏在变厚。")
    if total_qa:
        lines.append(f"库内累计问答记录 {total_qa} 条。")
    lines.append(drafts_hint)

    vibe = "平静"
    if qa + arch >= 15:
        vibe = "热闹"
    elif qa + arch >= 5:
        vibe = "稳步"
    elif qa + arch == 0:
        vibe = "静默"

    return {
        "date": _today_ymd(),
        "vibe": vibe,
        "lines": lines,
        "week_delta": wd,
        "disclaimer": "解读只复述本地统计，不作性格评判或运势承诺。",
    }


def _slips_path(root: Path | None = None) -> Path:
    return memory_root(root) / SLIPS_FILE


def record_slip(slip: dict[str, Any] | None = None, *, root: Path | None = None) -> dict[str, Any]:
    """写入/刷新当日签；同一天只保留一条。"""
    root = root or wiki_root()
    slip = slip or daily_slip(root=root)
    day = str(slip.get("date") or _today_ymd())
    path = _slips_path(root)
    rows: list[dict] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(row.get("date") or "") == day:
                continue
            rows.append(row)
    entry = {
        "date": day,
        "yi": slip.get("yi") or [],
        "ji": slip.get("ji") or [],
        "motto": slip.get("motto") or "",
        "recorded_at": datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M:%S"),
    }
    rows.append(entry)
    rows = rows[-8:]
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"ok": True, "entry": entry, "days": len(rows)}


def list_slips(*, root: Path | None = None, limit: int = 8) -> dict[str, Any]:
    path = _slips_path(root)
    rows: list[dict] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    rows = rows[-max(1, min(limit, 8)) :]
    return {"items": list(reversed(rows)), "count": len(rows)}


def produce_checklist() -> dict[str, Any]:
    return {
        "enabled_by_setting": produce_ritual_enabled(),
        "items": list(_CHECKLIST),
        "stamp": "今日可归档",
        "hint": "四项勾齐仅作仪式提醒，不拦截定稿；默认在设置中关闭。",
    }


def fortune_bundle(*, root: Path | None = None, record: bool = True) -> dict[str, Any]:
    """一次取齐：知签 + 库运势 + 签册 + checklist 元数据。"""
    enabled = fortune_enabled()
    slip = daily_slip(root=root) if enabled else None
    if enabled and record and slip:
        record_slip(slip, root=root)
    return {
        "enabled": enabled,
        "ritual_enabled": produce_ritual_enabled(),
        "slip": slip,
        "library": library_fortune(root=root) if enabled else None,
        "slips": list_slips(root=root) if enabled else {"items": [], "count": 0},
        "checklist": produce_checklist(),
    }
