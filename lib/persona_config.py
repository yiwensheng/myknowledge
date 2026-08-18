"""User-customizable persona (stored in wiki .config/persona.json)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import wiki_root

BEIJING = timezone(timedelta(hours=8))
CONFIG_DIR = ".config"
PERSONA_FILE = "persona.json"

TONE_LABELS = {
    "objective": "客观理性",
    "concise": "简明务实",
    "warm": "温和亲切",
    "academic": "严谨学术",
    "direct": "直截了当",
}

PREFERENCE_LABELS = {
    "conclusion_first": "先给结论，再列依据",
    "use_tables": "对比类内容优先用表格",
    "use_lists": "步骤与要点用条目列举",
    "wiki_oriented": "产出面向长期维护的结构化笔记",
}

PRESET_TEMPLATES: dict[str, dict[str, Any]] = {
    "curator": {
        "label": "知识策展师（默认）",
        "role_name": "易知 知识策展师",
        "role_intro": "负责把碎片资料整理成可复用、可检索的结构化知识。",
        "audience": "未来的自己、需要快速查阅的读者",
        "tones": ["objective", "concise"],
        "domain": "",
        "preferences": ["conclusion_first", "use_lists", "wiki_oriented"],
        "custom_notes": "",
    },
    "teacher": {
        "label": "教师 / 讲解者",
        "role_name": "易知 学习导师",
        "role_intro": "用清晰、分步骤的方式讲解知识库中的内容，帮助读者理解而非堆砌信息。",
        "audience": "学生、初学者、需要指导的读者",
        "tones": ["warm", "concise"],
        "domain": "教学与辅导",
        "preferences": ["conclusion_first", "use_lists"],
        "custom_notes": "复杂概念先给直觉，再给定义；适当用「第一步、第二步」组织。",
    },
    "researcher": {
        "label": "研究员 / 分析者",
        "role_name": "易知 研究分析助手",
        "role_intro": "严谨梳理材料中的论点、证据与局限，不做无依据推断。",
        "audience": "做调研、写报告的自己或同事",
        "tones": ["objective", "academic"],
        "domain": "研究与分析",
        "preferences": ["conclusion_first", "use_tables", "wiki_oriented"],
        "custom_notes": "指出材料间矛盾时保持中立；区分「材料所述」与「待核实」。",
    },
    "operator": {
        "label": "执行 / 运营",
        "role_name": "易知 执行助手",
        "role_intro": "把知识库内容转化为可执行的清单、流程与注意事项。",
        "audience": "需要马上照做的人",
        "tones": ["direct", "concise"],
        "domain": "运营与落地",
        "preferences": ["use_lists", "conclusion_first"],
        "custom_notes": "优先输出行动项、截止时间、责任边界（仅当材料中有依据）。",
    },
    "custom": {
        "label": "完全自定义",
        "role_name": "",
        "role_intro": "",
        "audience": "",
        "tones": [],
        "domain": "",
        "preferences": [],
        "custom_notes": "",
    },
}

GROUNDED_RULES = """
## 事实约束（始终适用）

- **绝对基于库内事实**：只使用本次注入的检索片段，不用模型自带知识补全。
- **禁止胡说八道**：片段未提及的内容，不得当作事实输出。
- **诚实拒答**：信息不够就拒答或部分回答，并标明「库内暂无依据」。
- 无依据不使用「非常出色」「领先行业」等夸大表述；不把推测写成既定事实。
""".strip()

GENDER_OPTIONS = ("男", "女", "不愿透露", "其他")

OWNER_PRONOUN_MARKERS = (
    "我",
    "我的",
    "本人",
    "咱们",
    "我们自己",
    "我自己",
    "姓名",
    "昵称",
    "叫什么",
    "是谁",
    "哪个",
)

OWNER_FIELD_MARKERS = (
    "电话",
    "手机",
    "邮箱",
    "邮件",
    "微信",
    "头像",
    "性别",
    "单位",
    "职务",
    "职位",
)


def default_owner() -> dict[str, str]:
    return {
        "real_name": "",
        "gender": "",
        "nickname": "",
        "phone": "",
        "email": "",
        "wechat": "",
        "avatar": "",
        "organization": "",
        "job_title": "",
        "aliases": "",
        "bio": "",
    }


def normalize_owner(raw: Any) -> dict[str, str]:
    base = default_owner()
    if not isinstance(raw, dict):
        return base
    for key in base:
        val = raw.get(key)
        base[key] = str(val or "").strip()
    if base["gender"] and base["gender"] not in GENDER_OPTIONS:
        base["gender"] = "其他"
    return base


def owner_aliases(owner: dict[str, str]) -> list[str]:
    out: list[str] = []
    for part in re.split(r"[,，、;；\s]+", str(owner.get("aliases") or "")):
        t = part.strip()
        if t and t not in out:
            out.append(t)
    return out


def owner_identity_terms(owner: dict[str, str] | None = None) -> list[str]:
    owner = owner or {}
    terms: list[str] = []
    for key in ("real_name", "nickname"):
        t = str(owner.get(key) or "").strip()
        if t and t not in terms:
            terms.append(t)
    for alias in owner_aliases(owner):
        if alias not in terms:
            terms.append(alias)
    org = str(owner.get("organization") or "").strip()
    if org and org not in terms:
        terms.append(org)
    return terms


def owner_profile_configured(owner: dict[str, str] | None = None) -> bool:
    owner = owner or {}
    return bool(owner_identity_terms(owner))


def query_refers_to_owner(query: str, owner: dict[str, str] | None = None) -> bool:
    q = (query or "").strip()
    if not q:
        return False
    owner = owner or {}
    terms = owner_identity_terms(owner)
    if any(m in q for m in OWNER_PRONOUN_MARKERS):
        return True
    if any(m in q for m in OWNER_FIELD_MARKERS):
        return True
    q_lower = q.lower()
    for t in terms:
        if t and t in q:
            return True
        if t and t.lower() in q_lower:
            return True
    return False


def expand_queries_for_owner(query: str, owner: dict[str, str] | None = None) -> list[str]:
    """Extra RAG queries when the user likely refers to themselves."""
    owner = owner or {}
    if not owner_profile_configured(owner):
        return []
    if not query_refers_to_owner(query, owner):
        return []
    extras: list[str] = []
    name = str(owner.get("real_name") or "").strip()
    nick = str(owner.get("nickname") or "").strip()
    if name:
        extras.extend([name, f"{name} 工作", f"{name} 记录"])
    if nick and nick != name:
        extras.append(nick)
    for alias in owner_aliases(owner):
        if alias not in extras:
            extras.append(alias)
    extras.extend(["闪念", "memos", "时间线"])
    q = query.strip()
    out: list[str] = []
    for item in extras:
        t = item.strip()
        if t and t not in out and t != q:
            out.append(t)
    return out[:8]


def render_owner_context(owner: dict[str, str] | None = None) -> str:
    owner = normalize_owner(owner or {})
    if not owner_profile_configured(owner):
        return ""

    lines = ["## 知识库主人（基本信息）", ""]
    rows: list[tuple[str, str]] = []
    if owner.get("real_name"):
        rows.append(("姓名", owner["real_name"]))
    if owner.get("nickname"):
        rows.append(("昵称", owner["nickname"]))
    if owner.get("gender"):
        rows.append(("性别", owner["gender"]))
    if owner.get("organization"):
        rows.append(("单位/组织", owner["organization"]))
    if owner.get("job_title"):
        rows.append(("职务", owner["job_title"]))
    if owner.get("phone"):
        rows.append(("联系电话", owner["phone"]))
    if owner.get("email"):
        rows.append(("邮箱", owner["email"]))
    if owner.get("wechat"):
        rows.append(("微信", owner["wechat"]))
    aliases = owner_aliases(owner)
    if aliases:
        rows.append(("别名", "、".join(aliases)))
    if owner.get("bio"):
        rows.append(("简介", owner["bio"]))

    for label, val in rows:
        lines.append(f"- **{label}**：{val}")

    names = "、".join(owner_identity_terms(owner)[:6])
    lines.extend(
        [
            "",
            "## 主人指代与检索规则",
            "",
            f"- 当用户说「我」「我的」「本人」，或问题涉及{names}时，**默认指知识库主人**，不是泛称。",
            "- **闪念**（memos/时间线）中的第一人称记录，视为该用户本人的随记与观点。",
            "- 检索与回答时：在其姓名/昵称/别名、相关工作记录、笔记、闪念、导入资料中查找依据。",
            "- 库内若有他人同名或相似姓名，须结合路径、时间与上下文区分，不得张冠李戴。",
            "- 用户问联系方式等字段时，可引用本节基本信息；若与库内片段冲突，以库内最新材料为准并说明。",
        ]
    )
    return "\n".join(lines).strip()


def owner_context_for_prompt(root: Path | None = None) -> str | None:
    cfg = load_persona_config(root)
    text = render_owner_context(cfg.get("owner") or {})
    return text or None


def avatar_file_path(root: Path | None = None) -> Path | None:
    cfg = load_persona_config(root)
    rel = str((cfg.get("owner") or {}).get("avatar") or "").strip()
    if not rel:
        return None
    base = wiki_root() if root is None else root
    path = (base / rel).resolve()
    try:
        path.relative_to((base / CONFIG_DIR).resolve())
    except ValueError:
        return None
    return path if path.is_file() else None


def persona_path(root: Path | None = None) -> Path:
    base = wiki_root() if root is None else root
    d = base / CONFIG_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d / PERSONA_FILE


def default_config() -> dict[str, Any]:
    tpl = dict(PRESET_TEMPLATES["curator"])
    tpl.pop("label", None)
    return {
        "enabled": False,
        "owner": default_owner(),
        "preset": "curator",
        "role_name": tpl["role_name"],
        "role_intro": tpl["role_intro"],
        "audience": tpl["audience"],
        "tones": list(tpl["tones"]),
        "domain": tpl["domain"],
        "preferences": list(tpl["preferences"]),
        "custom_notes": tpl["custom_notes"],
        "keep_grounded_rules": True,
        "updated_at": "",
    }


def load_persona_config(root: Path | None = None) -> dict[str, Any]:
    path = persona_path(root)
    if not path.is_file():
        return default_config()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default_config()
    if not isinstance(data, dict):
        return default_config()
    base = default_config()
    base.update({k: data[k] for k in base if k in data})
    if "enabled" in data:
        base["enabled"] = bool(data["enabled"])
    if isinstance(data.get("tones"), list):
        base["tones"] = [str(t) for t in data["tones"] if str(t) in TONE_LABELS]
    if isinstance(data.get("preferences"), list):
        base["preferences"] = [str(p) for p in data["preferences"] if str(p) in PREFERENCE_LABELS]
    if "owner" in data:
        base["owner"] = normalize_owner(data.get("owner"))
    preset = str(base.get("preset") or "curator")
    if preset not in PRESET_TEMPLATES:
        base["preset"] = "custom"
    return base


def save_persona_config(config: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    merged = default_config()
    merged.update(config)
    merged["enabled"] = bool(config.get("enabled"))
    merged["keep_grounded_rules"] = bool(config.get("keep_grounded_rules", True))
    merged["tones"] = [t for t in (config.get("tones") or []) if t in TONE_LABELS][:6]
    merged["preferences"] = [p for p in (config.get("preferences") or []) if p in PREFERENCE_LABELS][:8]
    preset = str(config.get("preset") or "curator")
    merged["preset"] = preset if preset in PRESET_TEMPLATES else "custom"
    merged["updated_at"] = datetime.now(BEIJING).strftime("%Y-%m-%dT%H:%M:%S%z")
    for key in ("role_name", "role_intro", "audience", "domain", "custom_notes"):
        merged[key] = str(config.get(key) or "").strip()
    merged["owner"] = normalize_owner(config.get("owner"))
    persona_path(root).write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        from .prompts import invalidate_persona_cache

        invalidate_persona_cache()
    except Exception:
        pass
    return merged


def reset_persona_config(root: Path | None = None) -> dict[str, Any]:
    cfg = default_config()
    path = persona_path(root)
    if path.is_file():
        path.unlink()
    return cfg


def apply_preset(preset_id: str) -> dict[str, Any]:
    pid = preset_id if preset_id in PRESET_TEMPLATES else "curator"
    tpl = PRESET_TEMPLATES[pid]
    cfg = load_persona_config()
    owner = dict(cfg.get("owner") or default_owner())
    cfg["preset"] = pid
    cfg["role_name"] = tpl.get("role_name", "")
    cfg["role_intro"] = tpl.get("role_intro", "")
    cfg["audience"] = tpl.get("audience", "")
    cfg["tones"] = list(tpl.get("tones") or [])
    cfg["domain"] = tpl.get("domain", "")
    cfg["preferences"] = list(tpl.get("preferences") or [])
    cfg["custom_notes"] = tpl.get("custom_notes", "")
    cfg["owner"] = owner
    return cfg


def render_persona(config: dict[str, Any] | None = None) -> str:
    cfg = config or load_persona_config()
    parts: list[str] = []
    owner_block = render_owner_context(cfg.get("owner") or {})
    if owner_block:
        parts.append(owner_block)
    if not cfg.get("enabled"):
        return "\n\n---\n\n".join(parts).strip() if parts else ""

    name = str(cfg.get("role_name") or "易知助手").strip()
    intro = str(cfg.get("role_intro") or "").strip()
    audience = str(cfg.get("audience") or "").strip()
    domain = str(cfg.get("domain") or "").strip()
    tones = [TONE_LABELS[t] for t in (cfg.get("tones") or []) if t in TONE_LABELS]
    prefs = [PREFERENCE_LABELS[p] for p in (cfg.get("preferences") or []) if p in PREFERENCE_LABELS]
    notes = str(cfg.get("custom_notes") or "").strip()

    lines = [f"你是 **{name}**。"]
    if intro:
        lines.append(intro)
    lines.append("")
    lines.append("## 性格与语气")
    if tones:
        lines.append("- " + "、".join(tones))
    else:
        lines.append("- 客观、理性、简明")
    if audience:
        lines.append(f"- 主要服务对象：**{audience}**")
    if domain:
        lines.append(f"- 擅长领域（用户设定）：{domain}")
    lines.append("- 结论须能由检索片段推导；语气平和，不讨好、不夸大。")

    if prefs:
        lines.extend(["", "## 表达偏好"])
        for p in prefs:
            lines.append(f"- {p}")

    if notes:
        lines.extend(["", "## 用户补充说明", notes])

    if cfg.get("keep_grounded_rules", True):
        lines.extend(["", GROUNDED_RULES])

    parts.append("\n".join(lines).strip())
    return "\n\n---\n\n".join(parts).strip()


def render_persona_preview(config: dict[str, Any] | None = None) -> str:
    cfg = config or load_persona_config()
    if cfg.get("enabled"):
        return render_persona(cfg)
    owner_only = render_owner_context(cfg.get("owner") or {})
    if owner_only:
        return owner_only + "\n\n---\n\n（角色人设未启用，将使用 prompts/persona.md 作为助手角色）"
    return ""


def list_presets() -> list[dict[str, str]]:
    return [{"id": k, "label": v.get("label", k)} for k, v in PRESET_TEMPLATES.items()]


def persona_for_prompt(root: Path | None = None) -> str | None:
    """Return custom persona markdown if enabled, else None (use file default)."""
    cfg = load_persona_config(root)
    owner = render_owner_context(cfg.get("owner") or {})
    if not cfg.get("enabled"):
        return owner or None
    text = render_persona(cfg)
    return text or None


def load_owner_config(root: Path | None = None) -> dict[str, str]:
    return normalize_owner(load_persona_config(root).get("owner"))
