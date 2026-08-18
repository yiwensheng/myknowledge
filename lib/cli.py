#!/usr/bin/env python3
"""易知 CLI — yws.bat backend."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

# Ensure package import from repo root
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.config import load_dotenv, output_dir, wiki_root  # noqa: E402
from lib.ingest import ingest_inbox, sync_all  # noqa: E402
from lib.url_ingest import ingest_url  # noqa: E402
from lib.llm import ask, ask_stream, produce  # noqa: E402
from lib.memory import memory_stats, new_session_id  # noqa: E402
from lib.loop_engine import ensure_loop_scaffold, loop_status, run_loop  # noqa: E402
from lib.skills import discover_skills, get_skill, load_skill_content, match_skill, run_matched, run_skill  # noqa: E402
from lib.rag import rebuild_index, rag_status, search  # noqa: E402
from lib.wiki import delete_page, list_pages, save_page, search_keyword, today_beijing  # noqa: E402
from lib.watcher import WikiWatcher  # noqa: E402


def cmd_init(_: argparse.Namespace) -> int:
    script = _ROOT / "scripts" / "init_wiki.py"
    import subprocess

    r = subprocess.run([sys.executable, str(script)], env=dict(__import__("os").environ))
    sync_all()
    print(f"Wiki ready: {wiki_root()}")
    # 若 init 脚本因安装目录无写权限失败，但知识库目录已就绪，视为成功
    if r.returncode != 0 and (wiki_root() / "inbox").is_dir():
        print("Note: wiki dirs present; treating init as success")
        return 0
    return r.returncode


def _strip_html(html: str) -> str:
    import re

    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    text = re.sub(r"</p>", "\n", text, flags=re.I)
    text = re.sub(r"</li>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _cli_session_file() -> Path:
    return wiki_root() / ".memory" / "cli-session.json"


def _resolve_ask_session(args: argparse.Namespace) -> tuple[str, bool | None, bool | None]:
    remember: bool | None = False if args.no_remember else None
    auto_archive: bool | None = False if args.no_archive else None
    if args.no_remember:
        return "", remember, auto_archive
    if args.new_session:
        sid = new_session_id()
        _cli_session_file().write_text(
            json.dumps({"id": sid}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return sid, remember, auto_archive
    if args.session:
        return args.session, remember, auto_archive
    path = _cli_session_file()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            sid = str(data.get("id") or "").strip()
            if sid:
                return sid, remember, auto_archive
        except json.JSONDecodeError:
            pass
    sid = new_session_id()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"id": sid}, ensure_ascii=False) + "\n", encoding="utf-8")
    return sid, remember, auto_archive


def cmd_ask(args: argparse.Namespace) -> int:
    if not args.question:
        print("Usage: yws ask \"your question\"", file=sys.stderr)
        return 1
    session_id, remember, auto_archive = _resolve_ask_session(args)
    args.stream = not args.no_stream
    if args.json and not args.stream:
        result = ask(
            args.question,
            top_k=args.top,
            session_id=session_id,
            remember=remember,
            auto_archive=auto_archive,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    html_parts: list[str] = []
    sources: list = []
    archived = None
    for ev in ask_stream(
        args.question,
        top_k=args.top,
        session_id=session_id,
        remember=remember,
        auto_archive=auto_archive,
    ):
        if ev.get("type") in ("html", "token"):
            chunk = ev.get("text") or ""
            html_parts.append(chunk)
            if args.stream and not args.json:
                sys.stdout.write(_strip_html(chunk))
                sys.stdout.flush()
        elif ev.get("type") == "done":
            sources = ev.get("sources") or []
            footer = ev.get("footer") or ""
            archived = ev.get("archived")
            html_parts.append(footer)
            if args.stream and footer and not args.json:
                sys.stdout.write(_strip_html(footer))
                sys.stdout.flush()

    full_html = "".join(html_parts)
    if args.json:
        print(
            json.dumps(
                {"answer_html": full_html, "sources": sources, "archived": archived, "session_id": session_id},
                ensure_ascii=False,
                indent=2,
            )
        )
    elif not args.stream:
        print(_strip_html(full_html))
        if sources:
            print("\n--- 来源 ---")
            for s in sources:
                print(f"- {s['title']} ({s['path']})")
    elif sources:
        print("\n--- 来源 ---")
        for s in sources:
            print(f"- {s['title']} ({s['path']})")
    if archived:
        print(f"\n--- 已归档入库: {archived} ---")
    elif session_id and not args.no_remember:
        print(f"\n--- 会话: {session_id}（连续对话已启用）---")
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    q = args.keyword or ""
    if args.rag:
        chunks = search(q, top_k=args.top)
        if args.json:
            print(
                json.dumps(
                    [{"title": c.title, "path": c.rel_path, "score": c.score, "text": c.text} for c in chunks],
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            for c in chunks:
                print(f"[{c.score:.2f}] {c.title} ({c.rel_path})\n  {c.text[:120]}...\n")
        return 0
    pages = search_keyword(q, type_filter=args.type, limit=args.top)
    if args.json:
        print(json.dumps([p.to_dict() for p in pages], ensure_ascii=False, indent=2))
    else:
        for p in pages:
            print(f"- [{p.type}] {p.title} ({p.rel_path})")
    return 0


def cmd_promo_audio(args: argparse.Namespace) -> int:
    """Generate single-voice narration MP3 from bundled 宣传文案."""
    from lib.yizhi_narration import synthesize_yizhi_promo_audio

    result = synthesize_yizhi_promo_audio(
        rewrite=not bool(getattr(args, "raw", False)),
        title=getattr(args, "title", None) or "易知宣传",
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"口播字数: {result.get('script_chars')}")
        print(f"分段: {result.get('segments')}")
        print(f"目录: {result.get('directory')}")
        if result.get("merged_file"):
            print(f"音频: {result['merged_file']} ({result.get('merged_format')})")
        if result.get("merged_error"):
            print(f"合并警告: {result['merged_error']}", file=sys.stderr)
            return 1
    return 0 if result.get("merged_file") else 1


def cmd_produce(args: argparse.Namespace) -> int:
    if not args.topic:
        print("Usage: yws produce \"topic\"", file=sys.stderr)
        return 1
    result = produce(args.topic, top_k=args.top, save_to_wiki=args.wiki)
    content = result["content"]
    if args.out:
        out_path = Path(args.out)
    elif not args.wiki:
        out_root = output_dir()
        out_root.mkdir(parents=True, exist_ok=True)
        slug = args.topic[:40].replace(" ", "-")
        out_path = out_root / f"{slug}-{today_beijing()}.md"
    else:
        out_path = None
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
    if args.json:
        if out_path:
            result["saved_to"] = str(out_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(content)
        if result.get("wiki_page"):
            print(f"\n已入库: {result['wiki_page']} (draft)")
        elif out_path:
            print(f"\n已保存: {out_path}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    pages = list_pages(type_filter=args.type, include_inbox=not args.no_inbox)
    if args.json:
        print(json.dumps([p.to_dict() for p in pages], ensure_ascii=False, indent=2))
    else:
        for p in pages:
            print(f"{p.rel_path}\t{p.type}\t{p.status}\t{p.title}")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    body = args.body or ""
    if args.file:
        body = Path(args.file).read_text(encoding="utf-8")
    p = save_page(args.type, args.title, body, tags=args.tag or [], status=args.status)
    sync_all()
    print(p.rel_path)
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    ok = delete_page(args.path)
    if ok:
        sync_all()
        print(f"deleted: {args.path}")
        return 0
    print(f"not found: {args.path}", file=sys.stderr)
    return 1


def cmd_url(args: argparse.Namespace) -> int:
    if not args.url:
        print('Usage: yws url "https://example.com/article"', file=sys.stderr)
        return 1
    if getattr(args, "async_mode", False):
        from lib.url_jobs import get_job, start_url_ingest_job

        info = start_url_ingest_job(args.url, force=args.force)
        job_id = info.get("job_id", "")
        print(f"已提交后台任务 {job_id}")
        if info.get("already_running"):
            print("（已有任务在进行中）")
            return 0
        for _ in range(600):
            time.sleep(1)
            job = get_job(job_id)
            if not job:
                break
            if job.get("status") in ("done", "failed"):
                if args.json:
                    print(json.dumps(job, ensure_ascii=False, indent=2))
                elif job.get("status") == "failed":
                    print(job.get("error", "failed"), file=sys.stderr)
                    return 1
                else:
                    print(f"已入库: {job.get('wiki_page')}")
                    print(f"  标题: {job.get('title')}")
                return 0
        print("任务超时", file=sys.stderr)
        return 1
    try:
        result = ingest_url(args.url, force=args.force)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if result.get("duplicate"):
        print(f"已存在（跳过）: {result['wiki_page']}")
        print(f"  URL: {result['url']}")
        return 0
    if result.get("quality_warning"):
        print(f"警告: {result['quality_warning']}", file=sys.stderr)
    print(f"已入库: {result['wiki_page']}")
    print(f"  标题: {result['title']}")
    print(f"  抓取: {result['method']}")
    print(f"  本地化: {result.get('localized', '')}")
    print(f"  URL: {result['url']}")
    return 0


def cmd_jobs(args: argparse.Namespace) -> int:
    sub = getattr(args, "jobs_cmd", "list")
    if sub == "list":
        from lib.upload_jobs import list_active_jobs as upload_jobs
        from lib.url_jobs import list_active_jobs as url_jobs
        from lib.linked_dir_jobs import list_active_jobs as linked_jobs
        from lib.index_jobs import list_active_jobs as index_jobs

        data = {
            "upload": upload_jobs(),
            "url": url_jobs(),
            "linked": linked_jobs(),
            "index": index_jobs(),
        }
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            for kind, jobs in data.items():
                if not jobs:
                    continue
                print(f"[{kind}]")
                for j in jobs:
                    print(f"  {j.get('id')} · {j.get('status')} · {j.get('current', '')}")
        return 0
    print("Unknown jobs subcommand", file=sys.stderr)
    return 1


def cmd_ingest(_: argparse.Namespace) -> int:
    done = ingest_inbox()
    print(f"ingested {len(done)} file(s)")
    for r in done:
        print(f"  - {r}")
    return 0


def cmd_index(_: argparse.Namespace) -> int:
    n = sync_all()
    print(f"Indexed {n} RAG chunks (TF + vector embeddings if configured).")
    st = rag_status()
    emb = st.get("embeddings") or {}
    print(f"RAG mode={st.get('mode')} · embeddings={emb.get('count', 0)} ({emb.get('model', '')})")
    return 0


def cmd_rag(args: argparse.Namespace) -> int:
    sub = getattr(args, "rag_cmd", None)
    if sub == "rebuild":
        n = rebuild_index()
        st = rag_status()
        if args.json:
            print(json.dumps({"chunks": n, **st}, ensure_ascii=False, indent=2))
        else:
            emb = st.get("embeddings") or {}
            print(f"Rebuilt {n} chunks · mode={st.get('mode')} · vectors={emb.get('count', 0)}")
        return 0
    st = rag_status()
    if args.json:
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return 0
    emb = st.get("embeddings") or {}
    ext = st.get("external") or {}
    print(f"RAG mode: {st.get('mode')}")
    print(f"Chunks: {st.get('chunks')} (size≈{st.get('chunk_size')})")
    print(f"Embeddings: {emb.get('count', 0)} · model={emb.get('model')} · enabled={emb.get('enabled')}")
    print(
        f"AnythingLLM: enabled={ext.get('enabled')} augment={ext.get('augment')} "
        f"chat_fallback={ext.get('chat_fallback')} workspace={ext.get('workspace') or '-'}"
    )
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    w = WikiWatcher()
    print(f"Watching {wiki_root()} (poll {w.poll}s). Ctrl+C to stop.")
    print("首次启动仅记录现有文件，从第二次扫描开始处理变更。")
    try:
        while True:
            try:
                w.run_once()
            except Exception as e:
                print(f"[watch] 跳过本轮：{e}", file=sys.stderr)
            time.sleep(w.poll)
    except KeyboardInterrupt:
        return 0


def _skill_params(args: argparse.Namespace) -> dict:
    p: dict = {}
    if getattr(args, "url", None):
        p["url"] = args.url
    if getattr(args, "question", None):
        p["question"] = args.question
    if getattr(args, "topic", None):
        p["topic"] = args.topic
    if getattr(args, "force", False):
        p["force"] = True
    if getattr(args, "wiki", False):
        p["wiki"] = True
    if getattr(args, "text", None):
        p["text"] = args.text
    return p


def cmd_skill(args: argparse.Namespace) -> int:
    if not args.skill_cmd:
        print("Usage: yws skill list|show|run|match", file=sys.stderr)
        return 1
    sub = args.skill_cmd
    if sub == "list":
        items = [s.to_dict() for s in discover_skills()]
        if args.json:
            print(json.dumps(items, ensure_ascii=False, indent=2))
        else:
            for s in discover_skills():
                run_tag = " [可执行]" if s.action else ""
                print(f"- {s.name}{run_tag} ({s.source})")
                if s.description:
                    print(f"    {s.description[:120]}")
        return 0
    if sub == "show":
        if not args.name:
            print("Usage: yws skill show <name>", file=sys.stderr)
            return 1
        try:
            print(load_skill_content(args.name))
        except KeyError as e:
            print(str(e), file=sys.stderr)
            return 1
        return 0
    if sub == "match":
        if not args.text:
            print("Usage: yws skill match \"整理知识库\"", file=sys.stderr)
            return 1
        s = match_skill(args.text)
        if args.json:
            print(json.dumps(s.to_dict() if s else None, ensure_ascii=False, indent=2))
        elif s:
            print(f"{s.name} ({s.action or 'doc-only'})")
        else:
            print("未匹配")
            return 1
        return 0
    if sub == "run":
        if not args.name:
            print("Usage: yws skill run <name>", file=sys.stderr)
            return 1
        result = run_skill(args.name, _skill_params(args))
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif result.get("ok"):
            if result.get("output"):
                print(result["output"])
            elif result.get("message"):
                print(result["message"])
                for w in result.get("workflows") or []:
                    print(f"  - {w.get('name')}: {w.get('description', '')[:80]}")
            else:
                print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(result.get("error") or json.dumps(result, ensure_ascii=False), file=sys.stderr)
            return 1
        return 0
    print("Usage: yws skill list|show|run|match", file=sys.stderr)
    return 1


def cmd_loop(args: argparse.Namespace) -> int:
    if not args.loop_cmd:
        print("Usage: yws loop run|status|watch", file=sys.stderr)
        return 1
    ensure_loop_scaffold()
    sub = args.loop_cmd
    if sub == "status":
        st = loop_status()
        if args.json:
            print(json.dumps(st, ensure_ascii=False, indent=2))
        else:
            print(f"Pattern: {st['pattern']} · default L{st['level_default']}")
            print(f"Last run: {st['last_run'] or '（无）'}")
            d = st["discovery"]
            print(f"inbox={d['inbox']} drafts={d['drafts']} RAG={d['rag_chunks']}")
            for t in d.get("high_priority") or []:
                print(f"  ! {t}")
        return 0
    if sub == "run":
        level = args.level
        result = run_loop(level=level, dry_run=args.dry_run)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif result.get("dry_run"):
            print("Dry run:", json.dumps(result.get("discovery"), ensure_ascii=False))
        else:
            print(f"L{result['level']} knowledge-evolution — ok={result['ok']}")
            for a in result.get("actions") or []:
                print(f"  ✓ {a}")
            for e in result.get("errors") or []:
                print(f"  ✗ {e}", file=sys.stderr)
            print(f"STATE → {result.get('state_path')}")
        return 0 if result.get("ok", True) else 1
    if sub == "watch":
        print(f"Loop watch every {args.interval}s (Ctrl+C to stop). Level L{args.level}")
        try:
            while True:
                r = run_loop(level=args.level)
                print(f"[{_beijing_now_loop()}] L{r['level']} ok={r['ok']} actions={len(r.get('actions') or [])}")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            return 0
    print("Usage: yws loop run|status|watch", file=sys.stderr)
    return 1


def _beijing_now_loop() -> str:
    from datetime import datetime, timedelta, timezone

    return datetime.now(timezone(timedelta(hours=8))).strftime("%H:%M:%S")


def cmd_gui(_: argparse.Namespace) -> int:
    import subprocess

    root = Path(__file__).resolve().parent.parent
    bat = root / "yws-gui.bat"
    if sys.platform == "win32" and bat.is_file():
        return subprocess.call([str(bat)], cwd=str(root))
    electron = root / "electron"
    return subprocess.call(["npm", "start"], cwd=str(electron), shell=True)


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="yws", description="易知 知识库 CLI")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("init", help="初始化目录与索引")

    p_ask = sub.add_parser("ask", help="RAG 提问")
    p_ask.add_argument("question", nargs="?", help="问题")
    p_ask.add_argument("--top", type=int, default=5)
    p_ask.add_argument("--json", action="store_true")
    p_ask.add_argument("--no-stream", action="store_true", help="禁用流式输出")
    p_ask.add_argument("--session", help="对话会话 ID（连续追问）")
    p_ask.add_argument("--new-session", action="store_true", help="开始新会话")
    p_ask.add_argument("--no-remember", action="store_true", help="不记住本次会话上下文")
    p_ask.add_argument("--no-archive", action="store_true", help="有依据时不自动归档到 notes/qa/")

    p_q = sub.add_parser("query", help="查询")
    p_q.add_argument("keyword", nargs="?", default="")
    p_q.add_argument("--type")
    p_q.add_argument("--top", type=int, default=10)
    p_q.add_argument("--rag", action="store_true", help="语义/TF RAG 检索")
    p_q.add_argument("--json", action="store_true")

    p_promo = sub.add_parser(
        "promo-audio",
        help="根据《易知-自我进化个人知识库-宣传文案》生成单人口播长语音 MP3",
    )
    p_promo.add_argument("--title", default="易知宣传", help="输出目录名")
    p_promo.add_argument(
        "--raw",
        action="store_true",
        help="不经大模型口播改写，直接朗读宣传原文",
    )
    p_promo.add_argument("--json", action="store_true")

    p_p = sub.add_parser("produce", help="RAG 产出文章")
    p_p.add_argument("topic", nargs="?", help="主题")
    p_p.add_argument("--out", help="输出文件路径")
    p_p.add_argument("--top", type=int, default=8)
    p_p.add_argument("--wiki", action="store_true", help="产出后直接写入 wiki（draft）")
    p_p.add_argument("--json", action="store_true")

    p_l = sub.add_parser("list", help="列表")
    p_l.add_argument("--type")
    p_l.add_argument("--no-inbox", action="store_true")
    p_l.add_argument("--json", action="store_true")

    p_a = sub.add_parser("add", help="新增条目")
    p_a.add_argument("--type", default="note")
    p_a.add_argument("--title", required=True)
    p_a.add_argument("--body", default="")
    p_a.add_argument("--file")
    p_a.add_argument("--tag", action="append")
    p_a.add_argument("--status", default="draft")

    p_d = sub.add_parser("delete", help="删除条目")
    p_d.add_argument("path")

    p_u = sub.add_parser("url", help="抓取 URL 并本地化入库")
    p_u.add_argument("url", nargs="?", help="网页地址")
    p_u.add_argument("--force", action="store_true", help="忽略 URL 去重，重新抓取入库")
    p_u.add_argument("--async", dest="async_mode", action="store_true", help="后台任务并等待完成")
    p_u.add_argument("--json", action="store_true")

    p_jobs = sub.add_parser("jobs", help="查看后台任务")
    jobs_sub = p_jobs.add_subparsers(dest="jobs_cmd")
    p_jl = jobs_sub.add_parser("list", help="列出活跃任务")
    p_jl.add_argument("--json", action="store_true")

    sub.add_parser("ingest", help="整理 inbox")
    sub.add_parser("index", help="重建索引与 RAG")
    p_rag = sub.add_parser("rag", help="RAG 状态与向量重建")
    rag_sub = p_rag.add_subparsers(dest="rag_cmd")
    p_rs = rag_sub.add_parser("status", help="显示 RAG / 向量 / 外联配置")
    p_rs.add_argument("--json", action="store_true")
    p_rr = rag_sub.add_parser("rebuild", help="仅重建 RAG（含向量）")
    p_rr.add_argument("--json", action="store_true")
    sub.add_parser("watch", help="监视目录自动 ingest/RAG")
    sub.add_parser("gui", help="打开图形界面")

    p_skill = sub.add_parser("skill", help="Skills 发现与执行")
    skill_sub = p_skill.add_subparsers(dest="skill_cmd")
    p_sl = skill_sub.add_parser("list", help="列出 Skills")
    p_sl.add_argument("--json", action="store_true")
    p_ss = skill_sub.add_parser("show", help="显示 SKILL.md 全文")
    p_ss.add_argument("name")
    p_sm = skill_sub.add_parser("match", help="按口令匹配 Skill")
    p_sm.add_argument("text")
    p_sm.add_argument("--json", action="store_true")
    p_sr = skill_sub.add_parser("run", help="执行 Skill")
    p_sr.add_argument("name")
    p_sr.add_argument("--url")
    p_sr.add_argument("--question")
    p_sr.add_argument("--topic")
    p_sr.add_argument("--text")
    p_sr.add_argument("--force", action="store_true")
    p_sr.add_argument("--wiki", action="store_true")
    p_sr.add_argument("--json", action="store_true")

    p_loop = sub.add_parser("loop", help="Loop Engineering 知识进化循环")
    loop_sub = p_loop.add_subparsers(dest="loop_cmd")
    p_lr = loop_sub.add_parser("run", help="运行 knowledge-evolution 循环")
    p_lr.add_argument("--level", type=int, default=None, help="1=报告 2=ingest/index 3=+produce")
    p_lr.add_argument("--dry-run", action="store_true")
    p_lr.add_argument("--json", action="store_true")
    p_ls = loop_sub.add_parser("status", help="循环状态与待办")
    p_ls.add_argument("--json", action="store_true")
    p_lw = loop_sub.add_parser("watch", help="定时运行循环")
    p_lw.add_argument("--interval", type=int, default=3600, help="秒")
    p_lw.add_argument("--level", type=int, default=2)

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        return 0
    if args.cmd == "rag" and not getattr(args, "rag_cmd", None):
        args.rag_cmd = "status"
        args.json = False
    if args.cmd == "jobs" and not getattr(args, "jobs_cmd", None):
        args.jobs_cmd = "list"
        args.json = False

    handlers = {
        "init": cmd_init,
        "ask": cmd_ask,
        "query": cmd_query,
        "promo-audio": cmd_promo_audio,
        "produce": cmd_produce,
        "list": cmd_list,
        "add": cmd_add,
        "delete": cmd_delete,
        "url": cmd_url,
        "jobs": cmd_jobs,
        "ingest": cmd_ingest,
        "index": cmd_index,
        "rag": cmd_rag,
        "watch": cmd_watch,
        "gui": cmd_gui,
        "skill": cmd_skill,
        "loop": cmd_loop,
    }
    if args.cmd == "loop" and not getattr(args, "loop_cmd", None):
        print("Usage: yws loop run|status|watch", file=sys.stderr)
        return 1
    return handlers[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
