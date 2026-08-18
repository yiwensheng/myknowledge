"""自我蒸馏：四层本地骨架 + 蒸馏工作流 + ask/produce 注入块。"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import wiki_root
from .wiki import serialize_page, slugify

BEIJING = timezone(timedelta(hours=8))

DISTILL_ROOT_NAME = "distill"
DISTILL_LAYERS = ("memory", "skills", "principle", "meta")
DISTILL_INJECT_PREFIXES = ("distill/skills", "distill/principle")

_LAYER_README: dict[str, str] = {
    "memory": """# Memory｜原始记忆

存放工作成品与踩坑的**原始素材**（PRD、汇报、笔记摘要、约束条件）。

- 只做收纳，不做过度改写。
- 提问/写文章时一般不强制注入本层，避免原文淹没结构。
""",
    "skills": """# Skills｜可复用技能

沉淀**不变的**执行范式：结构、拆解维度、行文骨架。

- 可变字段/数据不要写死；只锁逻辑与要素顺序。
- 提问与写文章会优先检索本目录。
- **中间成果包**：写清标题与「为何留下」，便于三个月后复用（BASB）。
""",
    "principle": """# Principle｜决策原则

存放取舍底线与判断标准（什么该做、什么拒绝、风险优先项）。

- 比「怎么做」更拉开差距的是「怎么选」。
- 提问与写文章会优先检索本目录。
- **为未来自己**：原则须脱离单次项目上下文仍可读懂。
""",
    "meta": """# Meta｜元规则

管理整套蒸馏体系：何时提炼、如何淘汰旧范式、输出须贴合本人风格。

详见同目录「蒸馏规则.md」。
""",
}

_META_RULES = """# 蒸馏规则（Meta）

可变内容不沉淀，不变逻辑才蒸馏。颗粒度优先中层范式（结构/维度/要素），勿全域原子模板。

## BASB / 第二大脑（对齐）

- **渐进摘要**：每次蒸馏只加一层价值；勿一次做成完美百科。
- **中间成果包**：Memory＝原料包，Skills＝可复用结构包，Principle＝取舍底线包；均须能被日后提问/写文章再次调用。
- **为未来自己**：条目标题与首句须脱离本次上下文仍可理解「为何留下」。
- **指向产出**：优先服务正在进行的文章、问题、项目，勿空转漂亮分类。

## 每次产出后（3 分钟）

1. **Memory**：归档本次成品要点与约束（可原文摘要）。
2. **Skills**：提炼 1 条可复用结构或拆解维度（剥离具体字段与数据）。
3. **Principle**：若有踩坑或取舍失误，提炼 0～1 条原则；无则写「无」。

## 更新

- 旧范式不再适配时：归档旧条，写新条，勿原地糊成一团。
- 输出须贴合本人风格，禁止通用套话堆砌。

## 注入

易知在「提问 / 写文章」时会检索 `distill/skills` 与 `distill/principle` 片段注入提示；Memory 不强制注入。
"""

_DISTILL_SYSTEM = """你是个人知识蒸馏助手。根据用户提供的工作产出或主题，提炼可复用资产。
铁律：可变内容（具体字段、数据、一次性文案）不沉淀；只沉淀不变逻辑、结构、原则。
对齐第二大脑：本次提炼须能成为「中间成果包」——三个月后仍可被提问/写文章调用；标题写清为何留下。
必须严格按下列标签输出，不要 Markdown 标题包裹标签本身，不要额外解释：

<<<MEMORY>>>
（2～8 句：本次素材摘要 + 约束/踩坑，保留事实）
<<<SKILL_TITLE>>>
（短标题，10 字内为宜；让未来自己一眼看懂）
<<<SKILL_BODY>>>
（可复用范式：结构/维度/步骤；用列表；勿写死本次专有名词数据）
<<<PRINCIPLE_TITLE>>>
（有原则则短标题；否则只写：无）
<<<PRINCIPLE_BODY>>>
（原则正文；若无原则只写：无）
"""


def distill_dir(root: Path | None = None) -> Path:
    return (root or wiki_root()) / DISTILL_ROOT_NAME


def ensure_distill_skeleton(root: Path | None = None, *, force_readme: bool = False) -> dict[str, Any]:
    """幂等创建 distill 四层目录与说明文件。不覆盖已有用户文件（除非 force_readme）。"""
    root = root or wiki_root()
    base = distill_dir(root)
    created: list[str] = []
    base.mkdir(parents=True, exist_ok=True)
    for layer in DISTILL_LAYERS:
        d = base / layer
        d.mkdir(parents=True, exist_ok=True)
        readme = d / "README.md"
        if force_readme or not readme.is_file():
            readme.write_text(_LAYER_README[layer].rstrip() + "\n", encoding="utf-8")
            created.append(readme.relative_to(root).as_posix())
    meta_rules = base / "meta" / "蒸馏规则.md"
    if force_readme or not meta_rules.is_file():
        meta_rules.write_text(_META_RULES.rstrip() + "\n", encoding="utf-8")
        created.append(meta_rules.relative_to(root).as_posix())
    return {"ok": True, "root": str(base), "created": created}


def _today_stamp() -> str:
    return datetime.now(BEIJING).strftime("%Y%m%d")


def _extract_tag(text: str, name: str) -> str:
    pat = rf"<<<{name}>>>\s*(.*?)(?=<<<[A-Z_]+>>>|\Z)"
    m = re.search(pat, text, re.DOTALL | re.IGNORECASE)
    return (m.group(1) if m else "").strip()


def _parse_distill_output(raw: str) -> dict[str, str]:
    memory = _extract_tag(raw, "MEMORY")
    skill_title = _extract_tag(raw, "SKILL_TITLE")
    skill_body = _extract_tag(raw, "SKILL_BODY")
    principle_title = _extract_tag(raw, "PRINCIPLE_TITLE")
    principle_body = _extract_tag(raw, "PRINCIPLE_BODY")
    return {
        "memory": memory,
        "skill_title": skill_title,
        "skill_body": skill_body,
        "principle_title": principle_title,
        "principle_body": principle_body,
    }


def _is_empty_principle(title: str, body: str) -> bool:
    t = (title or "").strip()
    b = (body or "").strip()
    if not t and not b:
        return True
    if t in ("无", "无。", "none", "N/A", "-") and (not b or b in ("无", "无。", "none", "N/A", "-")):
        return True
    if b in ("无", "无。") and t in ("无", "无。", ""):
        return True
    return False


def _write_distill_page(
    root: Path,
    layer: str,
    title: str,
    body: str,
    tags: list[str],
) -> str:
    stamp = _today_stamp()
    slug = slugify(title)
    rel = f"{DISTILL_ROOT_NAME}/{layer}/{stamp}-{slug}.md"
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        rel = f"{DISTILL_ROOT_NAME}/{layer}/{stamp}-{slug}-{datetime.now(BEIJING).strftime('%H%M%S')}.md"
        path = root / rel
    today = datetime.now(BEIJING).strftime("%Y-%m-%d")
    meta = {
        "title": title,
        "type": "note",
        "tags": tags,
        "created": today,
        "updated": today,
        "status": "active",
        "links": [],
    }
    path.write_text(serialize_page(meta, body.rstrip() + "\n"), encoding="utf-8")
    return rel


_COMMIT_LINE_RE = re.compile(
    r"(?im)^\s*(确认入库|\[确认入库\]|confirm(?:\s*=\s*1)?|commit(?:\s*=\s*1)?)\s*$"
)


def _parse_topic_commit(topic: str, commit: bool | None) -> tuple[str, bool]:
    """从正文剥离「确认入库」标记；commit 显式 True/False 优先。"""
    t = (topic or "").strip()
    if commit is True:
        return _COMMIT_LINE_RE.sub("", t).strip(), True
    if commit is False:
        return _COMMIT_LINE_RE.sub("", t).strip(), False
    if not t:
        return "", False
    if _COMMIT_LINE_RE.search(t):
        return _COMMIT_LINE_RE.sub("", t).strip(), True
    return t, False


def _preview_markdown(parsed: dict[str, str], topic: str) -> str:
    mem = parsed.get("memory") or topic[:2000]
    skill_title = parsed.get("skill_title") or "未命名范式"
    skill_body = parsed.get("skill_body") or "（模型未给出正文，请人工补全）"
    lines = [
        "# 蒸馏预览（未入库）\n",
        "## Memory\n",
        mem.strip() + "\n",
        f"## Skill：{skill_title}\n",
        skill_body.strip() + "\n",
    ]
    if _is_empty_principle(parsed.get("principle_title", ""), parsed.get("principle_body", "")):
        lines.append("## Principle\n\n（本次无）\n")
    else:
        p_title = parsed.get("principle_title") or "未命名原则"
        p_body = (parsed.get("principle_body") or "").strip()
        lines.append(f"## Principle：{p_title}\n")
        lines.append(p_body + "\n")
    lines.append(
        "---\n确认无误后，在参数末尾单独一行写「确认入库」再运行一次，才会写入 "
        "`distill/memory|skills|principle`。\n"
    )
    return "\n".join(lines)


def run_distill(
    topic: str,
    root: Path | None = None,
    *,
    commit: bool | None = None,
) -> dict[str, Any]:
    """蒸馏主题/正文 → 预览或写入 memory + skill + 可选 principle。

    默认仅预览；正文末行「确认入库」或 commit=True 时才入库。
    """
    topic, do_commit = _parse_topic_commit(topic, commit)
    if not topic:
        return {"ok": False, "error": "需要参数 topic（主题或粘贴正文）"}
    root = root or wiki_root()
    ensure_distill_skeleton(root)

    from .llm import _chat

    user = (
        "请蒸馏以下工作产出或主题。若内容较短，仍尽量抽出一条可复用 Skill；"
        "仅当确有决策/避坑点时再写 Principle。\n\n"
        f"{topic}"
    )
    raw = _chat(_DISTILL_SYSTEM, user, kind="ask")
    if "未配置 LLM" in raw or "LLM 请求失败" in raw:
        return {"ok": False, "error": raw, "output": raw}

    parsed = _parse_distill_output(raw)
    if not parsed["skill_title"] and not parsed["skill_body"] and not parsed["memory"]:
        return {
            "ok": False,
            "error": "模型输出无法解析，请重试或换模型",
            "raw": raw[:2000],
            "output": raw[:2000],
        }

    if not do_commit:
        output = _preview_markdown(parsed, topic)
        return {
            "ok": True,
            "action": "distill",
            "preview": True,
            "committed": False,
            "parsed": {
                "memory": parsed["memory"],
                "skill_title": parsed["skill_title"],
                "skill_body": parsed["skill_body"],
                "principle_title": parsed["principle_title"],
                "principle_body": parsed["principle_body"],
            },
            "output": output,
        }

    written: list[str] = []
    mem_body = parsed["memory"] or topic[:2000]
    mem_title = f"记忆-{slugify(topic)[:40]}"
    written.append(
        _write_distill_page(root, "memory", mem_title, mem_body, ["distill", "memory"])
    )

    skill_title = parsed["skill_title"] or "未命名范式"
    skill_body = parsed["skill_body"] or "（模型未给出正文，请人工补全）"
    written.append(
        _write_distill_page(root, "skills", skill_title, skill_body, ["distill", "skill"])
    )

    principle_rel = ""
    if not _is_empty_principle(parsed["principle_title"], parsed["principle_body"]):
        p_title = parsed["principle_title"] or "未命名原则"
        p_body = parsed["principle_body"] or ""
        principle_rel = _write_distill_page(
            root, "principle", p_title, p_body, ["distill", "principle"]
        )
        written.append(principle_rel)

    try:
        from .ingest import defer_refresh_rag

        defer_refresh_rag()
    except Exception:
        pass

    lines = [
        "# 蒸馏完成（已入库）\n",
        f"- Memory：`{written[0]}`",
        f"- Skill：`{written[1]}`",
    ]
    if principle_rel:
        lines.append(f"- Principle：`{principle_rel}`")
    else:
        lines.append("- Principle：（本次无）")
    lines.append("\n已触发检索库刷新（后台）。提问/写文章将优先参考 Skills 与 Principle。")
    output = "\n".join(lines)
    return {
        "ok": True,
        "action": "distill",
        "preview": False,
        "committed": True,
        "written": written,
        "principle": principle_rel,
        "output": output,
    }


def _has_user_distill_pages(root: Path | None = None) -> bool:
    base = distill_dir(root)
    if not base.is_dir():
        return False
    for layer in ("skills", "principle"):
        d = base / layer
        if not d.is_dir():
            continue
        for p in d.glob("*.md"):
            if p.name.lower() != "readme.md":
                return True
    return False


def distill_sources_for_query(query: str, top_k: int = 4) -> list[dict[str, Any]]:
    """检索 skills/principle，供提问页可视化引用。"""
    q = (query or "").strip()
    if not q or not _has_user_distill_pages():
        return []
    from .rag import search

    chunks = search(q, top_k=top_k, scope_paths=list(DISTILL_INJECT_PREFIXES))
    out: list[dict[str, Any]] = []
    for c in chunks:
        layer = "skills" if "skills" in (c.rel_path or "").replace("\\", "/") else "principle"
        if "principle" in (c.rel_path or "").replace("\\", "/"):
            layer = "principle"
        out.append(
            {
                "title": c.title,
                "rel_path": c.rel_path,
                "score": round(float(c.score), 4) if c.score is not None else None,
                "layer": layer,
            }
        )
    return out


def distill_context_block(query: str, top_k: int = 4) -> str:
    """检索 skills/principle，返回可拼进 prompt 的文本；无命中则空串。"""
    q = (query or "").strip()
    if not q:
        return ""
    if not _has_user_distill_pages():
        return ""

    from .rag import format_context, search

    chunks = search(q, top_k=top_k, scope_paths=list(DISTILL_INJECT_PREFIXES))
    if not chunks:
        return ""
    ctx = format_context(chunks)
    return (
        "\n\n【个人技能与原则】以下片段来自 distill/skills 与 distill/principle，"
        "须在结构、取舍与表达上优先贴合；不得与知识库事实冲突，不得编造库外事实。\n"
        f"{ctx}"
    )
