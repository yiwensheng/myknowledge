"""Loop Engineering for Myknowledge — scheduled knowledge evolution loops.

Adapted from https://github.com/cobusgreyling/loop-engineering
Pattern: knowledge-evolution (report → ingest → index → optional produce).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import load_dotenv, wiki_root
from .media_types import is_supported
from .memory import memory_stats
from .wiki import list_pages, today_beijing

BEIJING = timezone(timedelta(hours=8))
LOOP_DIR = ".loop"
RUN_LOG = "loop-run-log.jsonl"
LEDGER_FILE = "ledger.json"


@dataclass
class LoopWorkItem:
    kind: str
    title: str
    detail: str
    priority: int = 5
    actionable: bool = False


@dataclass
class LoopDiscovery:
    items: list[LoopWorkItem] = field(default_factory=list)
    inbox_count: int = 0
    draft_count: int = 0
    rag_chunks: int = 0
    memory: dict = field(default_factory=dict)

    def high_priority(self) -> list[LoopWorkItem]:
        return sorted(
            [i for i in self.items if i.priority >= 7],
            key=lambda x: -x.priority,
        )

    def watch_list(self) -> list[LoopWorkItem]:
        return sorted(
            [i for i in self.items if 4 <= i.priority < 7],
            key=lambda x: -x.priority,
        )


def _beijing_now_str() -> str:
    return datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M")


def loop_dir(root: Path | None = None) -> Path:
    root = root or wiki_root()
    d = root / LOOP_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _run_log_path(root: Path | None = None) -> Path:
    return loop_dir(root) / RUN_LOG


def _ledger_path(root: Path | None = None) -> Path:
    return loop_dir(root) / LEDGER_FILE


def default_level() -> int:
    load_dotenv()
    raw = os.environ.get("MYKNOWLEDGE_LOOP_LEVEL", "1").strip().upper()
    if raw.startswith("L"):
        raw = raw[1:]
    try:
        return max(1, min(3, int(raw)))
    except ValueError:
        return 1


def auto_act_enabled(level: int) -> bool:
    load_dotenv()
    if os.environ.get("MYKNOWLEDGE_LOOP_AUTO_ACT", "").strip().lower() in ("0", "false", "no"):
        return False
    if os.environ.get("MYKNOWLEDGE_LOOP_WEEK_ONE", "1").strip().lower() in ("1", "true", "yes"):
        return level >= 2 and os.environ.get("MYKNOWLEDGE_LOOP_WEEK_ONE", "1") == "0"
    return level >= 2


def discover_work(root: Path | None = None) -> LoopDiscovery:
    root = root or wiki_root()
    disc = LoopDiscovery()
    disc.memory = memory_stats(root)

    inbox = root / "inbox"
    if inbox.is_dir():
        for p in inbox.rglob("*"):
            if p.is_file() and is_supported(p.suffix) and "inbox-processed" not in p.parts:
                disc.inbox_count += 1
    if disc.inbox_count:
        disc.items.append(
            LoopWorkItem(
                kind="inbox",
                title=f"inbox 待整理 {disc.inbox_count} 个文件",
                detail="执行 ingest 可提取并入库",
                priority=9,
                actionable=True,
            )
        )

    pages = list_pages(root, include_inbox=False)
    drafts = [p for p in pages if p.status == "draft"]
    disc.draft_count = len(drafts)
    if disc.draft_count >= 5:
        disc.items.append(
            LoopWorkItem(
                kind="drafts",
                title=f"{disc.draft_count} 篇 draft 待精炼",
                detail="运行 wiki-review 或手改后 yws index",
                priority=6,
            )
        )

    orphans = [p for p in pages if not p.links and p.type != "note"]
    if len(orphans) >= 3:
        disc.items.append(
            LoopWorkItem(
                kind="orphans",
                title=f"{len(orphans)} 篇条目无 links（孤岛）",
                detail="见 index/open-questions.md",
                priority=5,
            )
        )

    oq = root / "index" / "open-questions.md"
    if oq.is_file() and "（无）" not in oq.read_text(encoding="utf-8")[:800]:
        disc.items.append(
            LoopWorkItem(
                kind="gaps",
                title="开放问题/断链待处理",
                detail="index/open-questions.md",
                priority=7,
            )
        )

    rag_path = root / ".rag" / "chunks.json"
    if rag_path.is_file():
        try:
            disc.rag_chunks = len(json.loads(rag_path.read_text(encoding="utf-8")).get("chunks") or [])
        except json.JSONDecodeError:
            pass
    if disc.rag_chunks == 0 and pages:
        disc.items.append(
            LoopWorkItem(
                kind="rag",
                title="RAG 索引为空但有 wiki 条目",
                detail="运行 yws index",
                priority=8,
                actionable=True,
            )
        )

    purpose = root / "purpose.md"
    if purpose.is_file():
        text = purpose.read_text(encoding="utf-8")
        if "开放问题记录区" in text:
            section = text.split("开放问题记录区", 1)[-1]
            open_q = [ln.strip()[2:] for ln in section.splitlines() if ln.strip().startswith("- ") and len(ln.strip()) > 2]
            for q in open_q[:3]:
                disc.items.append(
                    LoopWorkItem(
                        kind="purpose",
                        title=f"待回答: {q[:60]}",
                        detail="purpose.md 开放问题",
                        priority=6,
                    )
                )

    if disc.memory.get("qa_log_entries", 0) > 0 and disc.memory.get("qa_archived_notes", 0) == 0:
        disc.items.append(
            LoopWorkItem(
                kind="memory",
                title="问答日志未归档到 notes/qa",
                detail="检查 MYKNOWLEDGE_AUTO_ARCHIVE_QA",
                priority=4,
            )
        )

    return disc


def _state_path(root: Path | None = None) -> Path:
    return (root or wiki_root()) / "STATE.md"


def _loop_md_path(root: Path | None = None) -> Path:
    return (root or wiki_root()) / "LOOP.md"


def ensure_loop_scaffold(root: Path | None = None, force: bool = False) -> None:
    root = root or wiki_root()
    loop_dir(root)
    state = _state_path(root)
    if not state.exists() or force:
        state.write_text(_default_state_md(), encoding="utf-8")
    loop_md = _loop_md_path(root)
    if not loop_md.exists() or force:
        loop_md.write_text(_default_loop_md(), encoding="utf-8")
    budget = loop_dir(root) / "loop-budget.md"
    if not budget.exists() or force:
        budget.write_text(_default_budget_md(), encoding="utf-8")
    ledger = _ledger_path(root)
    if not ledger.exists():
        ledger.write_text(json.dumps({"runs": 0, "failures": 0, "last_error": ""}, indent=2) + "\n", encoding="utf-8")


def _default_state_md() -> str:
    return f"""# Loop State — Myknowledge

Last run: （尚未运行）
Pattern: **knowledge-evolution**
Level: L1（仅报告，见 LOOP.md）

## High Priority（循环关注 / 待人工确认）

- [ ] 首次运行：`yws loop run`

## Watch List

- [ ] 配置 `.env` LLM（提问 / L3 产出）

## Last Actions

- （无）

## Metrics

- inbox: 0 · drafts: 0 · RAG chunks: 0
"""


def _default_loop_md() -> str:
    return """# LOOP — Myknowledge 知识进化循环

> 基于 [Loop Engineering](https://github.com/cobusgreyling/loop-engineering) 适配。

## Pattern

**knowledge-evolution** — 发现 inbox/草稿/RAG 缺口 → 更新 STATE → 按级别自动 ingest/index。

## Levels

| Level | 行为 | 命令 |
|-------|------|------|
| L1 | 仅 triage + 写 STATE.md | `yws loop run --level 1` |
| L2 | L1 + 自动 ingest/index | `yws loop run --level 2` |
| L3 | L2 + 对 purpose 开放问题尝试 produce（需 LLM） | `yws loop run --level 3` |

## Human Gates（硬停止）

- L3 produce 仅写 **draft**，不自动 refined
- 不删除 wiki 条目
- 不 force URL 重新抓取
- `MYKNOWLEDGE_LOOP_WEEK_ONE=1` 时强制 L1（第一周仅报告）

## Schedule

```powershell
yws loop watch --interval 3600   # 每小时
# 或 Cursor Automation 每日运行: yws loop run
```

## Audit（可选）

```bash
npx @cobusgreyling/loop-audit . --suggest
```

需本目录存在 `STATE.md`、`LOOP.md`、`skills/`。
"""


def _default_budget_md() -> str:
    return """# Loop Budget — Myknowledge

| 项 | 限额 |
|----|------|
| L3 produce / 天 | 3 |
| 循环间隔 | ≥ 1h |

编辑 `.env`：`MYKNOWLEDGE_LOOP_LEVEL=1`
"""


def _render_state(disc: LoopDiscovery, level: int, actions: list[str]) -> str:
    hp = disc.high_priority()
    wl = disc.watch_list()
    hp_lines = []
    for item in hp[:8]:
        chk = "x" if any(item.title in a for a in actions) else " "
        hp_lines.append(f"- [{chk}] **{item.title}** — {item.detail}")
    if not hp_lines:
        hp_lines.append("- [x] （暂无高优先级项）")
    wl_lines = [f"- {i.title} — {i.detail}" for i in wl[:6]] or ["- （无）"]
    act_lines = [f"- {a}" for a in actions] or ["- （无）"]
    return f"""# Loop State — Myknowledge

Last run: {_beijing_now_str()}
Pattern: **knowledge-evolution**
Level: L{level}

## High Priority（循环关注 / 待人工确认）

{chr(10).join(hp_lines)}

## Watch List

{chr(10).join(wl_lines)}

## Last Actions

{chr(10).join(act_lines)}

## Metrics

- inbox: {disc.inbox_count} · drafts: {disc.draft_count} · RAG chunks: {disc.rag_chunks}
- memory sessions: {disc.memory.get('sessions', 0)} · qa archived: {disc.memory.get('qa_archived_notes', 0)}
"""


def _append_run_log(root: Path, entry: dict) -> None:
    path = _run_log_path(root)
    entry["at"] = _beijing_now_str()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _update_ledger(root: Path, ok: bool, error: str = "") -> None:
    path = _ledger_path(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        data = {"runs": 0, "failures": 0, "last_error": ""}
    data["runs"] = int(data.get("runs", 0)) + 1
    if not ok:
        data["failures"] = int(data.get("failures", 0)) + 1
        data["last_error"] = error[:500]
    else:
        data["last_error"] = ""
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_loop(level: int | None = None, dry_run: bool = False, root: Path | None = None) -> dict:
    root = root or wiki_root()
    load_dotenv()
    ensure_loop_scaffold(root)
    if level is None:
        level = default_level()
    if os.environ.get("MYKNOWLEDGE_LOOP_WEEK_ONE", "1").strip().lower() in ("1", "true", "yes"):
        level = min(level, 1)

    disc = discover_work(root)
    actions: list[str] = []
    errors: list[str] = []
    executed: dict = {}

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "level": level,
            "discovery": {
                "inbox": disc.inbox_count,
                "drafts": disc.draft_count,
                "rag_chunks": disc.rag_chunks,
                "high_priority": [i.title for i in disc.high_priority()],
            },
        }

    if level >= 2 and auto_act_enabled(level):
        if disc.inbox_count > 0:
            try:
                from .ingest import ingest_inbox, sync_all

                done = ingest_inbox(root)
                n = sync_all(root)
                actions.append(f"ingest: {len(done)} 文件 → RAG {n} chunks")
                executed["ingest"] = done
            except Exception as e:
                errors.append(f"ingest: {e}")
        elif any(i.kind == "rag" for i in disc.items):
            try:
                from .ingest import sync_all

                n = sync_all(root)
                actions.append(f"index: RAG {n} chunks")
                executed["index"] = n
            except Exception as e:
                errors.append(f"index: {e}")

    if level >= 3 and auto_act_enabled(level) and not errors:
        load_dotenv()
        if os.environ.get("MYKNOWLEDGE_LLM_API_KEY") or os.environ.get("LLM_API_KEY"):
            purpose = root / "purpose.md"
            topic = ""
            if purpose.is_file():
                text = purpose.read_text(encoding="utf-8")
                if "开放问题记录区" in text:
                    for ln in text.split("开放问题记录区", 1)[-1].splitlines():
                        ln = ln.strip()
                        if ln.startswith("- ") and len(ln) > 2:
                            topic = ln[2:].strip()
                            break
            if topic:
                try:
                    from .llm import produce

                    r = produce(topic, save_to_wiki=True)
                    wp = r.get("wiki_page") or ""
                    actions.append(f"produce: {topic[:40]} → {wp}")
                    executed["produce"] = wp
                except Exception as e:
                    errors.append(f"produce: {e}")

    # Refresh metrics after actions
    disc = discover_work(root)
    state_md = _render_state(disc, level, actions)
    _state_path(root).write_text(state_md, encoding="utf-8")

    ok = not errors
    result = {
        "ok": ok,
        "level": level,
        "pattern": "knowledge-evolution",
        "actions": actions,
        "errors": errors,
        "executed": executed,
        "state_path": str(_state_path(root)),
        "high_priority": [i.title for i in disc.high_priority()],
        "metrics": {
            "inbox": disc.inbox_count,
            "drafts": disc.draft_count,
            "rag_chunks": disc.rag_chunks,
        },
    }
    _append_run_log(root, result)
    _update_ledger(root, ok, "; ".join(errors))
    return result


def loop_status(root: Path | None = None) -> dict:
    root = root or wiki_root()
    ensure_loop_scaffold(root)
    disc = discover_work(root)
    ledger = {}
    lp = _ledger_path(root)
    if lp.is_file():
        try:
            ledger = json.loads(lp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    last_run = ""
    sp = _state_path(root)
    if sp.is_file():
        m = re.search(r"Last run:\s*(.+)", sp.read_text(encoding="utf-8"))
        if m:
            last_run = m.group(1).strip()
    return {
        "pattern": "knowledge-evolution",
        "level_default": default_level(),
        "last_run": last_run,
        "ledger": ledger,
        "discovery": {
            "inbox": disc.inbox_count,
            "drafts": disc.draft_count,
            "rag_chunks": disc.rag_chunks,
            "high_priority": [i.title for i in disc.high_priority()],
        },
        "state_file": str(sp),
        "loop_file": str(_loop_md_path(root)),
    }
