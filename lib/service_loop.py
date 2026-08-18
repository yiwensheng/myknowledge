"""Subscription service-loop: onboarding tasks, trial weeks, assets, scene templates."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import CONTENT_DIRS, wiki_root
from .llm import _chat
from .wiki import save_page

CONFIG_NAME = "service-loop.json"

TASK_KEYS = ("key_ok", "ingest_or_note", "ask_with_cite", "distill_once")
WEEK_KEYS = ("w1", "w2", "w3", "w4")

WEEK_META = {
    "w1": {"title": "入库", "hint": "导入一份资料或写一条笔记"},
    "w2": {"title": "有据问答", "hint": "完成一次带出处的提问"},
    "w3": {"title": "一篇产出", "hint": "写文章定稿或跑通场景模板并确认入库"},
    "w4": {"title": "沉淀", "hint": "蒸馏一次产出为可复用 Skill"},
}

COMMON_SYSTEM = (
    "你是易知的服务协作助手。只根据用户提供的输入起草，禁止编造未给出的事实、数据、课标、报价或效果。"
    "凡缺失信息一律写入「待确认」小节，不得补全成已确认事实。"
    "禁止承诺涨粉、提分、成交、流量等结果指标。"
    "输出使用简体中文 Markdown。"
)

TEMPLATES: dict[str, dict[str, Any]] = {
    "jiaoshi": {
        "id": "jiaoshi",
        "label": "教师课堂",
        "loop": "备课→上课→练习→作业→检测→反馈",
        "blurb": "一课六步闭环：备课、上课、练习、作业、检测、反馈与下节衔接。",
        "fields": [
            {"key": "subject", "label": "学科/年级", "required": True},
            {"key": "goal", "label": "本课目标", "required": True},
            {"key": "materials", "label": "已有讲义/教材线索", "required": False},
            {"key": "learners", "label": "学情（可选）", "required": False},
            {"key": "pending", "label": "待确认项（学时/课标等）", "required": False},
        ],
        "user_prompt": (
            "请按教师课堂六步写一课协作草案（每步独立二级标题）：\n"
            "1. 备课要点\n2. 上课流程\n3. 课堂练习\n4. 课后作业\n5. 检测方式\n6. 反馈与下节衔接\n"
            "最后增加「待确认」列表。输入如下：\n{payload}"
        ),
        "title_prefix": "教案草案",
    },
    "kaoyan": {
        "id": "kaoyan",
        "label": "考研/教研",
        "loop": "讲义入库→错题/考点问答→一页复习稿",
        "blurb": "围绕本周讲义与错题，产出一页复习稿与建议提问清单。",
        "fields": [
            {"key": "subject", "label": "科目", "required": True},
            {"key": "scope", "label": "本周范围", "required": True},
            {"key": "mistakes", "label": "错题/考点笔记", "required": False},
            {"key": "pending", "label": "待确认考点", "required": False},
        ],
        "user_prompt": (
            "产出「一页复习稿」Markdown，含：本周要点、易错点、建议自测题、建议在易知提问的问题清单、待确认。\n"
            "输入：\n{payload}"
        ),
        "title_prefix": "复习稿",
    },
    "zimeiti": {
        "id": "zimeiti",
        "label": "自媒体",
        "loop": "素材入库→热点稿→蒸馏写作 Skill",
        "blurb": "热点稿草案（非终稿）；确认入库后可再走蒸馏沉淀写作 Skill。",
        "fields": [
            {"key": "topic", "label": "选题", "required": True},
            {"key": "materials", "label": "素材要点/来源", "required": False},
            {"key": "channel", "label": "渠道", "required": False},
            {"key": "feedback", "label": "上期反馈", "required": False},
        ],
        "user_prompt": (
            "写一篇「热点稿草案」（非终稿），含标题备选、结构大纲、正文草稿、可蒸馏的写作要点、待确认。\n"
            "文末提示用户可在易知对本次产出执行「蒸馏本次产出」。\n输入：\n{payload}"
        ),
        "title_prefix": "热点稿草案",
    },
    "zhichang": {
        "id": "zhichang",
        "label": "职场",
        "loop": "会议纪要入库→待办摘要→周报草稿",
        "blurb": "从会议要点生成待办摘要与周报草稿。",
        "fields": [
            {"key": "meeting", "label": "会议要点/纪要", "required": True},
            {"key": "goals", "label": "本周目标", "required": False},
            {"key": "pending", "label": "待确认事项", "required": False},
        ],
        "user_prompt": (
            "输出两部分：① 待办摘要（负责人未知则标待确认）② 周报草稿。末尾「待确认」。\n输入：\n{payload}"
        ),
        "title_prefix": "周报与待办",
    },
    "opc": {
        "id": "opc",
        "label": "一人公司 OPC",
        "loop": "线索/客户笔记→本周交付清单→复盘纪要",
        "blurb": "一人公司一周运营协作：交付清单 + 复盘；不承诺成交。",
        "fields": [
            {"key": "positioning", "label": "业务定位", "required": True},
            {"key": "pipeline", "label": "本周客户/线索", "required": False},
            {"key": "deliverables", "label": "计划交付物", "required": False},
            {"key": "pending", "label": "待确认报价/范围", "required": False},
        ],
        "user_prompt": (
            "写「一人公司一周运营协作草案」，含：本周优先事项、交付清单、客户跟进要点、周末复盘问题、待确认。"
            "禁止承诺成交或收入数字。\n输入：\n{payload}"
        ),
        "title_prefix": "OPC周计划",
    },
}


def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds") + "Z"


def _config_path(root: Path | None = None) -> Path:
    return (root or wiki_root()) / ".config" / CONFIG_NAME


def default_state() -> dict[str, Any]:
    return {
        "version": 1,
        "started_at": _utc_iso(),
        "scenario": None,
        "tasks": {k: False for k in TASK_KEYS},
        "weeks": {k: {"done": False, "note": ""} for k in WEEK_KEYS},
        "dismissed_bar": False,
        "template_runs": [],
    }


def load_state(root: Path | None = None) -> dict[str, Any]:
    path = _config_path(root)
    if not path.is_file():
        return default_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_state()
    if not isinstance(data, dict):
        return default_state()
    base = default_state()
    base["started_at"] = data.get("started_at") or base["started_at"]
    base["scenario"] = data.get("scenario")
    base["dismissed_bar"] = bool(data.get("dismissed_bar"))
    tasks = data.get("tasks") if isinstance(data.get("tasks"), dict) else {}
    for k in TASK_KEYS:
        base["tasks"][k] = bool(tasks.get(k))
    weeks = data.get("weeks") if isinstance(data.get("weeks"), dict) else {}
    for k in WEEK_KEYS:
        w = weeks.get(k) if isinstance(weeks.get(k), dict) else {}
        base["weeks"][k] = {"done": bool(w.get("done")), "note": str(w.get("note") or "")}
    runs = data.get("template_runs")
    base["template_runs"] = runs if isinstance(runs, list) else []
    return base


def save_state(state: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    root = root or wiki_root()
    path = _config_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return state


def _has_user_content(root: Path) -> bool:
    for name in CONTENT_DIRS:
        d = root / name
        if not d.is_dir():
            continue
        for p in d.rglob("*"):
            if p.is_file() and p.suffix.lower() in {".md", ".txt", ".pdf", ".docx", ".html"}:
                if p.name.lower() == "readme.md" and "distill" in p.parts:
                    continue
                return True
    inbox = root / "inbox"
    if inbox.is_dir():
        for p in inbox.rglob("*"):
            if p.is_file():
                return True
    assets = root / "assets"
    if assets.is_dir():
        for p in assets.rglob("*"):
            if p.is_file() and p.name not in {".gitkeep"}:
                return True
    return False


def _qa_stats(root: Path) -> dict[str, int]:
    total = 0
    with_sources = 0
    try:
        from .memory_db import connect, ensure_db

        ensure_db(root)
        with connect(root) as conn:
            total = int(conn.execute("SELECT COUNT(*) AS n FROM qa_log").fetchone()["n"])
            rows = conn.execute("SELECT sources, grounded FROM qa_log").fetchall()
            for row in rows:
                try:
                    src = json.loads(row["sources"] or "[]")
                except json.JSONDecodeError:
                    src = []
                if (isinstance(src, list) and len(src) > 0) or int(row["grounded"] or 0):
                    with_sources += 1
    except Exception:
        pass
    return {"ask_count": total, "ask_with_cite": with_sources}


def _distill_skill_count(root: Path) -> int:
    base = root / "distill" / "skills"
    if not base.is_dir():
        return 0
    n = 0
    for p in base.rglob("*.md"):
        if p.name.lower() == "readme.md":
            continue
        n += 1
    return n


def _note_file_count(root: Path) -> int:
    n = 0
    for name in ("notes", "concepts", "entities", "sources", "comparisons", "archive"):
        d = root / name
        if not d.is_dir():
            continue
        for p in d.rglob("*.md"):
            n += 1
    return n


def _asset_file_count(root: Path) -> int:
    d = root / "assets"
    if not d.is_dir():
        return 0
    return sum(1 for p in d.rglob("*") if p.is_file())


def _folder_count(root: Path) -> int:
    try:
        from .folders import list_folders

        return len(list_folders(root) or [])
    except Exception:
        path = root / ".config" / "folders.json"
        if not path.is_file():
            return 0
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            folders = data.get("folders") if isinstance(data, dict) else data
            return len(folders) if isinstance(folders, list) else 0
        except (OSError, json.JSONDecodeError):
            return 0


def infer_tasks(root: Path | None = None) -> dict[str, bool]:
    root = root or wiki_root()
    qa = _qa_stats(root)
    return {
        "ingest_or_note": _has_user_content(root),
        "ask_with_cite": qa["ask_with_cite"] > 0,
        "distill_once": _distill_skill_count(root) > 0,
    }


def merge_inferred(state: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    inferred = infer_tasks(root)
    tasks = dict(state.get("tasks") or {})
    for k, v in inferred.items():
        if v:
            tasks[k] = True
    state = dict(state)
    state["tasks"] = tasks
    # Auto-mark weeks from tasks
    weeks = {k: dict(v) for k, v in (state.get("weeks") or {}).items()}
    if tasks.get("ingest_or_note"):
        weeks.setdefault("w1", {"done": False, "note": ""})["done"] = True
    if tasks.get("ask_with_cite"):
        weeks.setdefault("w2", {"done": False, "note": ""})["done"] = True
    if tasks.get("distill_once"):
        weeks.setdefault("w4", {"done": False, "note": ""})["done"] = True
    state["weeks"] = weeks
    return state


def patch_state(updates: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    root = root or wiki_root()
    state = load_state(root)
    if "dismissed_bar" in updates:
        state["dismissed_bar"] = bool(updates["dismissed_bar"])
    if "scenario" in updates:
        state["scenario"] = updates["scenario"]
    if isinstance(updates.get("tasks"), dict):
        for k in TASK_KEYS:
            if k in updates["tasks"]:
                state["tasks"][k] = bool(updates["tasks"][k])
    if isinstance(updates.get("weeks"), dict):
        for k in WEEK_KEYS:
            if k not in updates["weeks"]:
                continue
            w = updates["weeks"][k]
            if not isinstance(w, dict):
                continue
            cur = state["weeks"].setdefault(k, {"done": False, "note": ""})
            if "done" in w:
                cur["done"] = bool(w["done"])
            if "note" in w:
                cur["note"] = str(w["note"] or "")
    save_state(state, root)
    return get_status(root)


def collect_assets(root: Path | None = None) -> dict[str, Any]:
    root = root or wiki_root()
    qa = _qa_stats(root)
    return {
        "notes_count": _note_file_count(root),
        "assets_count": _asset_file_count(root),
        "ask_count": qa["ask_count"],
        "ask_with_cite": qa["ask_with_cite"],
        "distill_skills": _distill_skill_count(root),
        "folders_count": _folder_count(root),
        "wiki_root": str(root),
    }


def get_status(root: Path | None = None) -> dict[str, Any]:
    root = root or wiki_root()
    state = merge_inferred(load_state(root), root)
    tasks = state["tasks"]
    core_done = all(tasks.get(k) for k in ("key_ok", "ingest_or_note", "ask_with_cite"))
    return {
        **state,
        "week_meta": WEEK_META,
        "core_loop_done": core_done,
        "assets": collect_assets(root),
        "templates": list_templates(),
    }


def list_templates() -> list[dict[str, Any]]:
    out = []
    for t in TEMPLATES.values():
        out.append(
            {
                "id": t["id"],
                "label": t["label"],
                "loop": t["loop"],
                "blurb": t["blurb"],
                "fields": t["fields"],
            }
        )
    return out


def _format_payload(fields: list[dict[str, Any]], values: dict[str, Any]) -> str:
    lines = []
    for f in fields:
        key = f["key"]
        label = f["label"]
        val = str(values.get(key) or "").strip()
        if not val:
            lines.append(f"- {label}：（未提供 → 列入待确认）")
        else:
            lines.append(f"- {label}：{val}")
    return "\n".join(lines)


def run_template(template_id: str, values: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    tid = (template_id or "").strip()
    tmpl = TEMPLATES.get(tid)
    if not tmpl:
        return {"ok": False, "error": f"未知模板：{tid}"}
    missing = [
        f["label"]
        for f in tmpl["fields"]
        if f.get("required") and not str(values.get(f["key"]) or "").strip()
    ]
    if missing:
        return {"ok": False, "error": f"请填写：{'、'.join(missing)}"}
    payload = _format_payload(tmpl["fields"], values)
    user = tmpl["user_prompt"].format(payload=payload)
    try:
        markdown = _chat(COMMON_SYSTEM, user, kind="produce")
    except Exception as e:
        return {"ok": False, "error": str(e)}
    markdown = (markdown or "").strip()
    if markdown.startswith("<p>") or markdown.startswith("<pre>"):
        # LLM helper sometimes returns HTML error
        plain = re.sub(r"<[^>]+>", "", markdown)
        if "未配置" in plain or "HTTP" in plain:
            return {"ok": False, "error": plain.strip()[:500]}
    return {
        "ok": True,
        "template_id": tid,
        "label": tmpl["label"],
        "title_prefix": tmpl["title_prefix"],
        "markdown": markdown,
        "loop": tmpl["loop"],
    }


def commit_template(
    template_id: str,
    *,
    title: str,
    markdown: str,
    root: Path | None = None,
) -> dict[str, Any]:
    tid = (template_id or "").strip()
    tmpl = TEMPLATES.get(tid)
    if not tmpl:
        return {"ok": False, "error": f"未知模板：{tid}"}
    body = (markdown or "").strip()
    if not body:
        return {"ok": False, "error": "正文为空"}
    prefix = tmpl["title_prefix"]
    t = (title or "").strip() or f"{prefix}-{datetime.now().strftime('%Y%m%d')}"
    root = root or wiki_root()
    page = save_page(
        "note",
        t,
        body,
        tags=["service-loop", tid, "待确认入库"],
        status="draft",
        root=root,
    )
    state = load_state(root)
    state["template_runs"] = list(state.get("template_runs") or [])
    state["template_runs"].append(
        {
            "id": tid,
            "title": t,
            "rel": page.rel_path,
            "at": _utc_iso(),
        }
    )
    state["weeks"].setdefault("w3", {"done": False, "note": ""})["done"] = True
    save_state(state, root)
    return {"ok": True, "title": t, "rel_path": page.rel_path, "message": "已写入笔记，可继续提问或蒸馏。"}
