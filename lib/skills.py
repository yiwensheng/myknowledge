"""Discover and run Myknowledge Skills (Cursor-compatible SKILL.md)."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .config import ROOT, load_dotenv, wiki_root

SKILL_FILE = "SKILL.md"


@dataclass
class SkillInfo:
    name: str
    description: str
    path: Path
    source: str
    action: str = ""
    triggers: list[str] = field(default_factory=list)
    enabled: bool = True

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "path": str(self.path),
            "source": self.source,
            "action": self.action,
            "triggers": self.triggers,
            "enabled": self.enabled,
            "runnable": bool(self.action),
        }


def _parse_skill_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n(.*)", text, re.DOTALL)
    if not m:
        return {}, text
    raw, body = m.group(1), m.group(2)
    meta: dict = {}
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(raw) or {}
        if isinstance(loaded, dict):
            meta = loaded
    except Exception:
        for line in raw.splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, body


def _skill_dirs() -> list[tuple[Path, str]]:
    load_dotenv()
    dirs: list[tuple[Path, str]] = []
    project_skills = ROOT / "skills"
    if project_skills.is_dir():
        dirs.append((project_skills, "project"))
    wiki_sk = wiki_root() / "skills"
    if wiki_sk.is_dir() and wiki_sk.resolve() != project_skills.resolve():
        dirs.append((wiki_sk, "wiki"))
    raw = os.environ.get("MYKNOWLEDGE_SKILLS_DIRS", "").strip()
    if raw:
        parts = re.split(r"[;\n]+", raw) if ";" in raw or "\n" in raw else raw.split(os.pathsep)
        for i, part in enumerate(parts):
            part = part.strip().strip('"').strip("'")
            if part:
                p = Path(part).expanduser().resolve()
                if p.is_dir():
                    dirs.append((p, f"custom-{i}"))
    cursor = Path.home() / ".cursor" / "skills"
    if cursor.is_dir() and os.environ.get("MYKNOWLEDGE_INCLUDE_CURSOR_SKILLS", "0") != "0":
        dirs.append((cursor, "cursor"))
    agents = Path.home() / ".agents" / "skills"
    if agents.is_dir() and os.environ.get("MYKNOWLEDGE_INCLUDE_AGENTS_SKILLS", "0") == "1":
        dirs.append((agents, "agents"))
    return dirs


def _extract_triggers(meta: dict, body: str) -> list[str]:
    triggers: list[str] = []
    myk = meta.get("myknowledge")
    if isinstance(myk, dict):
        raw = myk.get("triggers") or myk.get("trigger")
        if isinstance(raw, list):
            triggers.extend(str(x) for x in raw)
        elif raw:
            triggers.append(str(raw))
    for line in body.splitlines():
        if "|" in line and "用户说" in line:
            continue
        m = re.search(r"[「\"']([^「\"']{2,40})[」\"']", line)
        if m and ("触发" in line or "口令" in line or "用户说" in line):
            triggers.append(m.group(1))
    return list(dict.fromkeys(t.strip() for t in triggers if t.strip()))


def _action_from_meta(meta: dict) -> str:
    myk = meta.get("myknowledge")
    if isinstance(myk, dict):
        action = myk.get("action") or myk.get("run")
        if action:
            return str(action).strip().lower()
    name = str(meta.get("name") or "").lower()
    mapping = {
        "wiki-ingest": "ingest",
        "wiki-index": "index",
        "wiki-review": "review",
        "wiki-url": "url",
        "wiki-classify-suggest": "classify-suggest",
        "wiki-distill": "distill",
        "wiki-parse-check": "parse-check",
        "wiki-pdf-llm-parse": "pdf-llm-parse",
        "wiki-curator": "menu",
        "loop-triage": "loop",
        "knowledge-evolution": "loop-l3",
    }
    return mapping.get(name, "")


def discover_skills(include_disabled: bool = False, runnable_only: bool = False) -> list[SkillInfo]:
    seen: set[str] = set()
    out: list[SkillInfo] = []
    for base, source in _skill_dirs():
        for skill_md in base.rglob(SKILL_FILE):
            if "node_modules" in skill_md.parts:
                continue
            try:
                text = skill_md.read_text(encoding="utf-8")
            except OSError:
                continue
            meta, body = _parse_skill_frontmatter(text)
            name = str(meta.get("name") or skill_md.parent.name).strip()
            if not name or name in seen:
                continue
            seen.add(name)
            desc = str(meta.get("description") or "").strip()
            myk = meta.get("myknowledge") if isinstance(meta.get("myknowledge"), dict) else {}
            enabled = myk.get("enabled", True) is not False
            if not enabled and not include_disabled:
                continue
            action = _action_from_meta(meta)
            if not action and (skill_md.parent / "scripts" / "run.py").is_file():
                action = "script"
            out.append(
                SkillInfo(
                    name=name,
                    description=desc[:500],
                    path=skill_md,
                    source=source,
                    action=action,
                    triggers=_extract_triggers(meta, body),
                    enabled=enabled,
                )
            )
    if runnable_only:
        out = [s for s in out if s.action and s.action != "menu"]
    out.sort(key=lambda s: (s.source, s.name))
    return out


def get_skill(name: str) -> SkillInfo | None:
    for s in discover_skills(include_disabled=True):
        if s.name == name:
            return s
    return None


def load_skill_content(name: str) -> str:
    skill = get_skill(name)
    if not skill:
        raise KeyError(f"Skill not found: {name}")
    return skill.path.read_text(encoding="utf-8")


def match_skill(text: str) -> SkillInfo | None:
    text = text.strip()
    if not text:
        return None
    lower = text.lower()
    best: SkillInfo | None = None
    best_len = 0
    for skill in discover_skills():
        for trig in skill.triggers:
            if trig in text or trig.lower() in lower:
                if len(trig) > best_len:
                    best = skill
                    best_len = len(trig)
        if skill.name.replace("-", " ") in lower or skill.name in lower:
            if len(skill.name) > best_len:
                best = skill
                best_len = len(skill.name)
    return best


def _run_script_skill(skill: SkillInfo, params: dict) -> dict:
    script = skill.path.parent / "scripts" / "run.py"
    if not script.is_file():
        return {"ok": False, "error": f"No scripts/run.py for skill {skill.name}"}
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "WIKI_ROOT": str(wiki_root())}
    for k, v in params.items():
        env[f"MYK_PARAM_{k.upper()}"] = str(v)
    r = subprocess.run(
        [sys.executable, str(script), *[f"{k}={v}" for k, v in params.items()]],
        cwd=str(skill.path.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=600,
    )
    return {
        "ok": r.returncode == 0,
        "stdout": r.stdout,
        "stderr": r.stderr,
        "returncode": r.returncode,
    }


def _run_review() -> dict:
    root = wiki_root()
    parts: list[str] = ["# 知识库回顾\n"]
    for fname in ("open-questions.md", "stats.md", "recent.md"):
        p = root / "index" / fname
        if p.is_file():
            parts.append(f"## {fname}\n\n{p.read_text(encoding='utf-8')}\n")
    from .ingest import sync_all

    sync_all(root)
    return {"ok": True, "output": "\n".join(parts), "action": "review"}


def run_skill(name: str, params: dict | None = None) -> dict:
    """Execute a skill by name. params may include url, topic, question, text."""
    params = dict(params or {})
    skill = get_skill(name)
    if not skill:
        return {"ok": False, "error": f"Skill not found: {name}"}
    action = skill.action
    if action == "script":
        return _run_script_skill(skill, params)

    if action == "ingest":
        from .ingest import ingest_inbox, sync_all

        done = ingest_inbox()
        sync_all()
        return {"ok": True, "action": "ingest", "count": len(done), "items": done}

    if action == "classify-suggest":
        from .classify_suggest import suggest_classification

        max_files = params.get("max_files")
        try:
            mf = int(max_files) if max_files is not None else None
        except (TypeError, ValueError):
            mf = None
        return suggest_classification(max_files=mf)

    if action == "index":
        from .ingest import sync_all

        n = sync_all()
        return {"ok": True, "action": "index", "rag_chunks": n}

    if action == "review":
        return _run_review()

    if action == "url":
        url = params.get("url") or params.get("text") or ""
        if not url.startswith("http"):
            return {"ok": False, "error": "需要参数 url"}
        from .url_jobs import start_url_ingest_job

        job_info = start_url_ingest_job(url, force=bool(params.get("force")))
        return {"ok": True, "action": "url", "async": True, **job_info}

    if action == "ask":
        q = params.get("question") or params.get("text") or ""
        if not q:
            return {"ok": False, "error": "需要参数 question"}
        from .llm import ask

        return {"ok": True, "action": "ask", **ask(q)}

    if action == "produce":
        topic = params.get("topic") or params.get("text") or ""
        if not topic:
            return {"ok": False, "error": "需要参数 topic"}
        from .llm import produce

        return {"ok": True, "action": "produce", **produce(topic, save_to_wiki=params.get("wiki", True))}

    if action == "leader":
        idea = params.get("topic") or params.get("text") or params.get("idea") or ""
        if not idea:
            return {
                "ok": False,
                "error": "需要参数 topic（或 text/idea）",
                "output": "需要参数 topic（或 text/idea）：一句话想法",
            }
        from .llm import generate_goal_brief

        save = params.get("wiki", True)
        if isinstance(save, str):
            save = save.strip().lower() not in ("0", "false", "no")
        result = generate_goal_brief(idea, save_to_wiki=bool(save))
        result["action"] = "leader"
        return result

    if action == "distill":
        topic = params.get("topic") or params.get("text") or params.get("question") or ""
        if not topic:
            return {
                "ok": False,
                "error": "需要参数 topic（主题或粘贴正文）",
                "output": "需要参数 topic：本次产出摘要或正文",
            }
        from .distill import run_distill

        commit_raw = params.get("confirm")
        if commit_raw is None:
            commit_raw = params.get("commit")
        commit: bool | None = None
        if isinstance(commit_raw, bool):
            commit = commit_raw
        elif commit_raw is not None:
            commit = str(commit_raw).strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
                "确认",
                "确认入库",
            )
        return run_distill(str(topic), commit=commit)

    if action == "parse-check":
        topic = params.get("topic") or params.get("text") or params.get("path") or ""
        from .parse_quality import run_parse_quality_check

        return run_parse_quality_check(str(topic))

    if action == "pdf-llm-parse":
        topic = params.get("topic") or params.get("text") or params.get("path") or ""
        from .pdf_llm_parse import run_pdf_llm_parse

        return run_pdf_llm_parse(str(topic))

    if action == "menu":
        workflows = [s for s in discover_skills() if s.action and s.action != "menu"]
        return {
            "ok": True,
            "action": "menu",
            "message": "可用子技能（yws skill run <name>）",
            "workflows": [s.to_dict() for s in workflows],
        }

    if action in ("loop", "loop-l3"):
        from .loop_engine import run_loop

        lvl = 3 if action == "loop-l3" else int(params.get("level") or 1)
        return run_loop(level=lvl, dry_run=bool(params.get("dry_run")))

    return {
        "ok": False,
        "error": f"Skill '{name}' 仅提供说明文档，无内置执行器。请阅读: {skill.path}",
        "content_path": str(skill.path),
    }


def run_matched(text: str, params: dict | None = None) -> dict:
    skill = match_skill(text)
    if not skill:
        return {"ok": False, "error": f"未匹配到 Skill: {text}"}
    merged = dict(params or {})
    if "text" not in merged and "question" not in merged and "url" not in merged:
        merged["text"] = text
    result = run_skill(skill.name, merged)
    result["matched_skill"] = skill.name
    return result
