"""Built-in and user-defined workflows for 易知 GUI."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from .config import wiki_root
from .skills import SkillInfo, discover_skills, get_skill, run_skill


def _custom_file() -> Path:
    """用户自定义工作流存 wiki 数据目录（安装版 Program Files 不可写）。"""
    return wiki_root() / ".config" / "custom-workflows.json"


# Chinese labels + optional param for GUI (project skills only)
WORKFLOW_META: dict[str, dict[str, Any]] = {
    "wiki-ingest": {
        "label": "整理待处理文件",
        "description": "扫描 inbox/，提取正文、写入 wiki 并重建 RAG",
        "param_key": None,
    },
    "wiki-classify-suggest": {
        "label": "资料分类建议",
        "description": "扫描 inbox/，给出五类目录归属建议（不移动原文件）",
        "param_key": None,
    },
    "wiki-index": {
        "label": "更新检索库",
        "description": "重建 RAG 索引与 index/ 汇总页",
        "param_key": None,
    },
    "wiki-url": {
        "label": "抓取网页入库",
        "description": "下载网页正文并写入 sources/",
        "param_key": "url",
        "param_placeholder": "https://…",
    },
    "wiki-ask": {
        "label": "知识库提问",
        "description": "基于 RAG 片段回答（只许用库内事实）",
        "param_key": "question",
        "param_placeholder": "输入问题…",
    },
    "wiki-review": {
        "label": "知识库回顾",
        "description": "汇总 open-questions、stats、recent 等索引页",
        "param_key": None,
    },
    "loop-triage": {
        "label": "自动检查",
        "description": "Loop L1：扫描缺口并更新 STATE.md（只报告）",
        "param_key": None,
    },
    "knowledge-evolution": {
        "label": "深度自动整理",
        "description": "Loop L3：自动 ingest + index + 进化建议",
        "param_key": None,
    },
    "leader": {
        "label": "生成目标任务书",
        "description": "一句话想法 → 可交给执行 Agent 的目标任务书（防漂移、含验收）",
        "param_key": "topic",
        "param_placeholder": "输入想法或目标…",
    },
    "wiki-distill": {
        "label": "蒸馏本次产出",
        "description": "先预览 Memory/Skill/Principle；确认无误后在末行写「确认入库」再跑一次",
        "param_key": "topic",
        "param_placeholder": "粘贴产出…；入库时末行写「确认入库」",
    },
    "wiki-parse-check": {
        "label": "解析质量抽检",
        "description": "对 inbox 或指定文件做提取+分块抽检（表格/OCR/过短等），导入前先看是否人类可读",
        "param_key": "topic",
        "param_placeholder": "可选：文件或目录路径（空=抽检 inbox）",
    },
    "wiki-pdf-llm-parse": {
        "label": "LLM 版面解析",
        "description": "多模态按页解析复杂 PDF（HTML 表/合并单元格/跨页合表）；写预览笔记，不自动入库",
        "param_key": "topic",
        "param_placeholder": "PDF 路径（空=inbox 首个）；可选末行「保留坐标」",
    },
}

ALLOWED_SOURCES = frozenset({"project", "wiki"})


def _skill_to_workflow(skill: SkillInfo, *, custom_id: str = "", custom_label: str = "") -> dict[str, Any]:
    meta = WORKFLOW_META.get(skill.name, {})
    label = custom_label or meta.get("label") or skill.name
    return {
        "id": custom_id or skill.name,
        "skill": skill.name,
        "label": label,
        "description": meta.get("description") or skill.description[:200],
        "param_key": meta.get("param_key"),
        "param_placeholder": meta.get("param_placeholder", ""),
        "source": skill.source,
        "builtin": not bool(custom_id),
        "runnable": True,
    }


def _load_custom() -> list[dict[str, Any]]:
    path = _custom_file()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data.get("workflows") if isinstance(data, dict) else []
        return items if isinstance(items, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _save_custom(items: list[dict[str, Any]]) -> None:
    path = _custom_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": 1, "workflows": items}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def list_builtin_workflows() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for skill in discover_skills():
        if skill.source not in ALLOWED_SOURCES:
            continue
        if not skill.action or skill.action == "menu":
            continue
        if skill.name not in WORKFLOW_META and skill.action == "script":
            out.append(_skill_to_workflow(skill))
            continue
        if skill.name in WORKFLOW_META:
            out.append(_skill_to_workflow(skill))
    out.sort(key=lambda x: x["label"])
    return out


def list_custom_workflows() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in _load_custom():
        skill_name = str(item.get("skill") or "").strip()
        skill = get_skill(skill_name)
        if not skill or not skill.action or skill.action == "menu":
            continue
        wf = _skill_to_workflow(
            skill,
            custom_id=str(item.get("id") or ""),
            custom_label=str(item.get("label") or skill_name),
        )
        wf["default_params"] = item.get("params") or {}
        out.append(wf)
    return out


def list_all_workflows() -> dict[str, Any]:
    builtin = list_builtin_workflows()
    custom = list_custom_workflows()
    return {
        "builtin": builtin,
        "custom": custom,
        "items": builtin + custom,
        "note": "仅显示易知内置可执行工作流；不含 Cursor 编码类 Skill。",
    }


def add_custom_workflow(label: str, skill: str, params: dict | None = None) -> dict[str, Any]:
    label = label.strip()
    skill = skill.strip()
    if not label:
        raise ValueError("请填写工作流名称")
    if not get_skill(skill) or skill not in WORKFLOW_META:
        raise ValueError("请选择有效的内置工作流")
    items = _load_custom()
    entry = {
        "id": uuid.uuid4().hex[:12],
        "label": label,
        "skill": skill,
        "params": params or {},
    }
    items.append(entry)
    _save_custom(items)
    return list_all_workflows()


def remove_custom_workflow(workflow_id: str) -> dict[str, Any]:
    wid = workflow_id.strip()
    items = [x for x in _load_custom() if str(x.get("id")) != wid]
    _save_custom(items)
    return list_all_workflows()


def resolve_workflow_skill(name_or_id: str) -> tuple[str, dict]:
    """Return (skill_name, default_params)."""
    for item in _load_custom():
        if str(item.get("id")) == name_or_id:
            return str(item.get("skill")), dict(item.get("params") or {})
    return name_or_id, {}


def run_workflow(name_or_id: str, params: dict | None = None) -> dict:
    skill_name, defaults = resolve_workflow_skill(name_or_id)
    merged = {**defaults, **(params or {})}
    result = run_skill(skill_name, merged)
    result["workflow"] = name_or_id
    result["skill"] = skill_name
    if not result.get("output"):
        if isinstance(result.get("answer"), str):
            result["output"] = result["answer"]
        elif result.get("rag_chunks") is not None and result.get("action") == "index":
            result["output"] = f"检索库已更新，共 {result['rag_chunks']} 段"
        elif result.get("count") is not None and result.get("items") is not None:
            lines = [f"已处理 {result['count']} 项："] + [f"  · {x}" for x in result.get("items") or []]
            result["output"] = "\n".join(lines)
        elif result.get("actions") is not None:
            lines = [f"{'完成' if result.get('ok') else '未完成'}（{result.get('action', '')}）"]
            lines.extend(f"✓ {a}" for a in result.get("actions") or [])
            if result.get("errors"):
                lines.extend(f"✗ {e}" for e in result["errors"])
            if result.get("state_path"):
                lines.append(f"\n待办：{result['state_path']}")
            result["output"] = "\n".join(lines)
        elif result.get("async") and result.get("action") == "url":
            job = result.get("job") or {}
            url = job.get("url") or merged.get("url") or ""
            if result.get("already_running"):
                result["output"] = f"已有网页抓取任务在进行中，请稍候…\n{url}".strip()
            else:
                result["output"] = (
                    f"已提交网页抓取任务（{result.get('job_id', '')}）\n"
                    f"{url}\n"
                    "后台处理中，进度见 URL 栏下方与右上角提示。"
                ).strip()
        elif result.get("brief") and isinstance(result.get("brief"), str):
            path = result.get("wiki_page") or result.get("path") or ""
            prefix = f"已保存：{path}\n\n" if path else ""
            result["output"] = result.get("output") or f"{prefix}{result['brief']}"
        elif result.get("title") and result.get("wiki_page"):
            result["output"] = f"✓ {result.get('title')}\n笔记：{result.get('wiki_page')}"
        else:
            import json

            result["output"] = json.dumps(
                {k: v for k, v in result.items() if k != "output"},
                ensure_ascii=False,
                indent=2,
            )
    return result
