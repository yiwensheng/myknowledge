"""OpenAI-compatible chat for ask / produce."""

from __future__ import annotations

import json
import os
import re
import ssl
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

from .config import ROOT, anythingllm_config, llm_config, load_dotenv, rag_top_k, wiki_root
from .html_answer import esc, html_to_plain, no_ground_html
from .citation import enrich_source, linkify_fragment_refs, sources_footer_html
from .memory import (
    append_session_turn,
    archive_qa_to_wiki,
    auto_archive_enabled,
    format_related_qa_block,
    log_qa,
    remember_enabled,
    search_related_qa,
    session_messages,
)
from .markdown_render import markdown_to_html
from .prompts import (
    parse_wiki_hints,
    system_for_ask,
    system_for_produce,
    title_from_markdown,
)
from .rag import format_context, search
from .wiki import save_page


def _temperature(kind: str) -> float:
    load_dotenv()
    if kind == "produce":
        raw = os.environ.get("MYKNOWLEDGE_LLM_TEMPERATURE_PRODUCE", "0.35")
    else:
        raw = os.environ.get("MYKNOWLEDGE_LLM_TEMPERATURE_ASK", "0.15")
    try:
        return float(raw)
    except ValueError:
        return 0.3


def _max_tokens(kind: str) -> int | None:
    load_dotenv()
    key = "MYKNOWLEDGE_LLM_MAX_TOKENS_PRODUCE" if kind == "produce" else "MYKNOWLEDGE_LLM_MAX_TOKENS_ASK"
    raw = os.environ.get(key, "").strip()
    if not raw:
        return 8192 if kind == "produce" else None
    try:
        return max(512, min(32768, int(raw)))
    except ValueError:
        return 8192 if kind == "produce" else None


def _build_ask_prompt(question: str, ctx: str, related_block: str = "") -> str:
    extra = f"\n\n{related_block}" if related_block else ""
    owner_hint = ""
    product_hint = ""
    conflict_hint = ""
    try:
        from .persona_config import load_owner_config, query_refers_to_owner

        if query_refers_to_owner(question, load_owner_config()):
            owner_hint = (
                "\n\n【主人指代】问题中的「我/我的/本人」或所涉姓名，指知识库主人；"
                "优先在闪念、时间线、其姓名/昵称相关笔记与工作记录中找依据。"
            )
    except Exception:
        pass
    try:
        from .yizhi_product import query_refers_to_yizhi

        if query_refers_to_yizhi(question):
            product_hint = (
                "\n\n【产品自我介绍】本题在问「易知 / 本软件 / 你自己（作为产品）」时，"
                "须依据系统提示中的「易知产品说明」作答；不得用产品说明编造用户知识库事实。"
                "输出仍为 HTML，禁止 Markdown。"
            )
    except Exception:
        pass
    try:
        from .config import rag_conflict_prompt_enabled

        if rag_conflict_prompt_enabled():
            paths = set(re.findall(r"路径：([^\n]+)", ctx))
            multi = len(paths) >= 2 or ctx.count("--- 片段") >= 2
            if multi:
                conflict_hint = (
                    "\n\n【冲突处理】若多段检索片段对同一事实说法不一致："
                    "须在「直接回答」或「待人工确认」中明确列出矛盾双方及对应片段编号，"
                    "禁止和稀泥成单一结论；不足处写「库内暂无统一依据」。"
                )
            else:
                conflict_hint = (
                    "\n\n【冲突处理】若片段内部表述冲突，指出冲突并标注片段编号，勿强行统一。"
                )
    except Exception:
        pass
    hard = (
        "【硬性要求】你只能使用下方「检索片段」中的信息作答。"
        "禁止编造、禁止用预训练知识补全。输出必须是 HTML（见系统提示），禁止 Markdown。"
        "若片段来自「分析提炼」章节，其要点与事实须与正文一致，可优先引用以组织回答。"
        "若提供了历史相关问答，仅用于理解追问意图，不得把历史问答当作新的事实依据。"
    )
    if product_hint:
        hard = (
            "【硬性要求】关于用户知识库材料：只使用下方「检索片段」，禁止编造。"
            "关于易知本软件：可使用系统提示中的「易知产品说明」。"
            "输出必须是 HTML（见系统提示），禁止 Markdown。"
        )
    distill_hint = ""
    try:
        from .distill import distill_context_block

        distill_hint = distill_context_block(question)
    except Exception:
        pass
    return (
        f"问题：{question}\n\n"
        f"{hard}"
        f"{owner_hint}{product_hint}{conflict_hint}{extra}{distill_hint}\n\n"
        f"检索片段：\n{ctx}"
    )


def prepare_ask(
    question: str,
    top_k: int | None = None,
    session_id: str = "",
    remember: bool | None = None,
    scope_paths: list[str] | None = None,
) -> tuple[str | None, list[dict], bool, str | None, list[dict]]:
    """Returns (user_prompt, sources, grounded, static_html_if_no_llm, related_qa)."""
    k = top_k if top_k is not None else rag_top_k("ask")
    from .rag_agent import search_enhanced

    chunks = search_enhanced(question, top_k=k, scope_paths=scope_paths)
    sources = [
        enrich_source(
            index=i,
            title=c.title,
            rel_path=c.rel_path,
            score=c.score,
            retrieval=c.retrieval,
            text=c.text,
            asset_path=c.asset_path,
        )
        for i, c in enumerate(chunks, 1)
    ]
    related_entries: list[dict] = []
    if chunks:
        ctx = format_context(chunks)
        related = ""
        if remember_enabled(remember) and not scope_paths:
            related_entries = search_related_qa(question)
            related = format_related_qa_block(related_entries)
        return _build_ask_prompt(question, ctx, related), sources, True, None, related_entries

    try:
        from .yizhi_product import load_yizhi_product, query_refers_to_yizhi

        if query_refers_to_yizhi(question) and load_yizhi_product():
            ctx = (
                "（知识库无直接命中；请仅依据系统提示「易知产品说明」介绍本软件，"
                "勿编造用户个人资料或库内文件内容。）"
            )
            return _build_ask_prompt(question, ctx), sources, True, None, related_entries
    except Exception:
        pass

    cfg = anythingllm_config()
    if cfg.get("chat_fallback") and cfg.get("enabled"):
        from .rag_external import workspace_query_chat

        ext = workspace_query_chat(question)
        if ext:
            text = str(ext.get("textResponse") or ext.get("response") or "").strip()
            if text:
                ext_sources: list[dict] = []
                for s in ext.get("sources") or []:
                    if isinstance(s, dict):
                        ext_sources.append(
                            {
                                "title": str(s.get("title") or "AnythingLLM"),
                                "path": f"@anythingllm:{cfg.get('workspace')}",
                                "score": 0.0,
                                "retrieval": "anythingllm-chat",
                            }
                        )
                    else:
                        ext_sources.append(
                            {
                                "title": str(s),
                                "path": f"@anythingllm:{cfg.get('workspace')}",
                                "retrieval": "anythingllm-chat",
                            }
                        )
                html = f'<div class="answer"><p>{esc(text)}</p>{sources_footer_html(ext_sources)}</div>'
                return None, ext_sources or sources, True, html, related_entries

    return None, sources, False, no_ground_html(question), related_entries


def _is_retriable_llm_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(
        token in msg
        for token in (
            "ssl",
            "eof",
            "timed out",
            "connection reset",
            "10054",
            "unexpected_eof",
            "remote end closed",
        )
    )


def _llm_error_html(label: str, detail: str) -> str:
    return f'<p class="error">LLM 请求失败 ({esc(label)}): {esc(detail)}</p>'


def _urlopen_llm(req: urllib.request.Request, timeout: int = 180):
    ctx = ssl.create_default_context()
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            return urllib.request.urlopen(req, timeout=timeout, context=ctx)
        except Exception as exc:
            last_err = exc
            if attempt < 2 and _is_retriable_llm_error(exc):
                time.sleep(1.0 + attempt)
                continue
            raise
    if last_err:
        raise last_err
    raise RuntimeError("LLM request failed")


def _chat(system: str, user: str, kind: str = "ask") -> str:
    parts = list(_chat_stream(system, user, kind=kind))
    return "".join(parts)


def probe_llm(timeout: int = 45) -> dict[str, Any]:
    """Short non-stream chat to verify API base / key / model."""
    load_dotenv()
    cfg = llm_config()
    if not (cfg.get("api_key") or "").strip():
        return {
            "ok": False,
            "latency_ms": 0,
            "error": "未配置 API Key。请在设置 → 大模型中填写后重试。",
        }
    payload: dict[str, Any] = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": "Reply with exactly: pong"},
            {"role": "user", "content": "ping"},
        ],
        "temperature": 0,
        "max_tokens": 8,
        "stream": False,
    }
    req = urllib.request.Request(
        cfg["chat_url"],
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {cfg['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with _urlopen_llm(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        latency_ms = int((time.perf_counter() - t0) * 1000)
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            return {"ok": False, "latency_ms": latency_ms, "error": f"响应非 JSON：{raw[:200]}"}
        content = (
            ((obj.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        ).strip()
        return {
            "ok": True,
            "latency_ms": latency_ms,
            "model": cfg.get("model") or "",
            "reply": content[:80],
            "message": f"连接成功（{latency_ms} ms）",
        }
    except urllib.error.HTTPError as e:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        body = e.read().decode("utf-8", errors="replace")[:400]
        return {"ok": False, "latency_ms": latency_ms, "error": f"HTTP {e.code}: {body}"}
    except Exception as e:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "error": f"{type(e).__name__}: {e}",
        }


def _chat_stream(
    system: str,
    user: str,
    kind: str = "ask",
    history: list[dict[str, str]] | None = None,
) -> Iterator[str]:
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    for turn in history or []:
        role = turn.get("role") or ""
        content = (turn.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user})
    yield from _chat_stream_messages(messages, kind=kind)


def _chat_stream_messages(messages: list[dict[str, str]], kind: str = "ask") -> Iterator[str]:
    cfg = llm_config()
    if not cfg["api_key"]:
        user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        yield (
            "<p>未配置 LLM API Key。请在 .env 中设置 MYKNOWLEDGE_LLM_API_KEY。</p>"
            f"<pre>{esc(user)}</pre>"
        )
        return
    payload: dict[str, Any] = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": _temperature(kind),
        "stream": True,
    }
    max_tok = _max_tokens(kind)
    if max_tok:
        payload["max_tokens"] = max_tok
    req = urllib.request.Request(
        cfg["chat_url"],
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {cfg['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with _urlopen_llm(req) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = (obj.get("choices") or [{}])[0].get("delta") or {}
                piece = delta.get("content")
                if piece:
                    yield piece
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:800]
        yield _llm_error_html(f"HTTP {e.code}", body)
    except Exception as e:
        yield _llm_error_html(type(e).__name__, str(e) or "未知网络错误")


def _finalize_ask(
    question: str,
    answer_html: str,
    sources: list[dict],
    grounded: bool,
    session_id: str = "",
    remember: bool | None = None,
    auto_archive: bool | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {"archived": None, "remembered": False}
    plain = html_to_plain(answer_html)
    wiki_page = ""
    if grounded and auto_archive_enabled(auto_archive):
        wiki_page = archive_qa_to_wiki(question, answer_html, sources) or ""
        if wiki_page:
            from .ingest import defer_refresh_rag

            defer_refresh_rag()
            meta["archived"] = wiki_page
    log_qa(question, plain, sources, grounded, session_id=session_id, wiki_page=wiki_page)
    if session_id and remember_enabled(remember):
        append_session_turn(session_id, "user", question)
        if plain:
            append_session_turn(session_id, "assistant", plain)
        meta["remembered"] = True
        try:
            from .memory import maybe_summarize_session

            maybe_summarize_session(session_id)
        except Exception:
            pass
    return meta


def ask_stream(
    question: str,
    top_k: int | None = None,
    session_id: str = "",
    remember: bool | None = None,
    auto_archive: bool | None = None,
    scope_paths: list[str] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield SSE events: {type: token|html|done|error|status, ...}."""
    yield {"type": "status", "text": "正在检索知识库…"}
    prompt, sources, grounded, static_html, related_qa = prepare_ask(
        question,
        top_k=top_k,
        session_id=session_id,
        remember=remember,
        scope_paths=scope_paths,
    )
    history = session_messages(session_id) if session_id and remember_enabled(remember) else []
    related_meta = [
        {
            "id": e.get("id"),
            "question": e.get("question"),
            "at": e.get("at"),
        }
        for e in related_qa
    ]
    distill_sources = _distill_sources_meta(question)
    if static_html:
        _finalize_ask(
            question,
            static_html,
            sources,
            grounded,
            session_id=session_id,
            remember=remember,
            auto_archive=False,
        )
        yield {"type": "html", "text": static_html}
        yield {
            "type": "done",
            "sources": sources,
            "grounded": grounded,
            "footer": "",
            "archived": None,
            "remembered": bool(session_id and remember_enabled(remember)),
            "related_qa": related_meta,
            "distill_sources": distill_sources,
        }
        return
    assert prompt is not None
    if grounded:
        yield {"type": "status", "text": f"已找到 {len(sources)} 段相关资料，正在生成…"}
    answer_parts: list[str] = []
    for token in _chat_stream(system_for_ask(), prompt, kind="ask", history=history):
        answer_parts.append(token)
        yield {"type": "token", "text": token}
    answer_html = "".join(answer_parts)
    answer_html = linkify_fragment_refs(answer_html, sources)
    footer = sources_footer_html(sources)
    meta = _finalize_ask(
        question,
        answer_html,
        sources,
        grounded,
        session_id=session_id,
        remember=remember,
        auto_archive=auto_archive,
    )
    yield {
        "type": "done",
        "sources": sources,
        "grounded": grounded,
        "footer": footer,
        "related_qa": related_meta,
        "distill_sources": distill_sources,
        **meta,
    }


def _distill_sources_meta(question: str) -> list[dict]:
    try:
        from .distill import distill_sources_for_query

        return distill_sources_for_query(question)
    except Exception:
        return []


def ask(
    question: str,
    top_k: int | None = None,
    session_id: str = "",
    remember: bool | None = None,
    auto_archive: bool | None = None,
    scope_paths: list[str] | None = None,
) -> dict:
    prompt, sources, grounded, static_html, related_qa = prepare_ask(
        question,
        top_k=top_k,
        session_id=session_id,
        remember=remember,
        scope_paths=scope_paths,
    )
    history = session_messages(session_id) if session_id and remember_enabled(remember) else []
    related_meta = [
        {"id": e.get("id"), "question": e.get("question"), "at": e.get("at")}
        for e in related_qa
    ]
    distill_sources = _distill_sources_meta(question)
    if static_html:
        meta = _finalize_ask(
            question,
            static_html,
            sources,
            grounded,
            session_id=session_id,
            remember=remember,
            auto_archive=False,
        )
        return {
            "question": question,
            "answer": static_html,
            "answer_html": static_html,
            "model": llm_config().get("model"),
            "sources": sources,
            "grounded": grounded,
            "related_qa": related_meta,
            "distill_sources": distill_sources,
            **meta,
        }
    assert prompt is not None
    answer = _chat(system_for_ask(), prompt, kind="ask", history=history)
    answer = linkify_fragment_refs(answer, sources)
    full_html = answer + sources_footer_html(sources)
    meta = _finalize_ask(
        question,
        answer,
        sources,
        grounded,
        session_id=session_id,
        remember=remember,
        auto_archive=auto_archive,
    )
    return {
        "question": question,
        "answer": full_html,
        "answer_html": full_html,
        "model": llm_config().get("model"),
        "sources": sources,
        "grounded": grounded,
        "related_qa": related_meta,
        "distill_sources": distill_sources,
        **meta,
    }


_FIRST_PRINCIPLES_REVIEW = "每次回答都要运用第一性原理，并进行对抗式审查"


def _first_principles_block(enabled: bool) -> str:
    if not enabled:
        return ""
    return f"\n\n【思维方法】{_FIRST_PRINCIPLES_REVIEW}"


def _build_produce_prompt(
    topic: str,
    top_k: int | None = None,
    genre: str = "article",
    brief: str = "",
    scope_paths: list[str] | None = None,
    first_principles_review: bool = False,
) -> tuple[str, list, dict[str, Any]]:
    from .produce_genres import format_genre_block, get_genre

    g = get_genre(genre)
    k = top_k if top_k is not None else int(g.get("top_k") or rag_top_k("produce"))
    k = max(k, rag_top_k("produce"))
    chunks = search(topic, top_k=k, scope_paths=scope_paths)
    ctx = format_context(chunks) if chunks else "（无匹配片段，请按体例输出框架并标注待核实）"
    purpose_hint = ""
    purpose_path = wiki_root() / "purpose.md"
    if purpose_path.is_file():
        purpose_hint = purpose_path.read_text(encoding="utf-8")[:1200]

    related_block = ""
    if not scope_paths:
        related = format_related_qa_block(search_related_qa(topic))
        if related:
            related_block = f"\n\n{related}"
    genre_block = format_genre_block(g["id"], brief)

    product_hint = ""
    try:
        from .yizhi_product import load_yizhi_product, query_refers_to_yizhi

        if query_refers_to_yizhi(topic) or query_refers_to_yizhi(brief):
            if load_yizhi_product():
                product_hint = (
                    "\n\n【产品稿件】主题涉及「易知 / 本软件 / 你自己（作为产品）」时，"
                    "须依据系统提示「易知产品说明」组织介绍；知识库片段可作补充，"
                    "不得用预训练知识夸大或编造未写入产品说明与片段的能力/数据。"
                )
                if not chunks:
                    ctx = (
                        "（无知识库片段；请主要依据系统提示「易知产品说明」撰写，"
                        "涉及用户私有材料处标注待核实。）"
                    )
    except Exception:
        pass

    distill_hint = ""
    try:
        from .distill import distill_context_block

        distill_hint = distill_context_block(f"{topic}\n{brief}".strip())
    except Exception:
        pass

    prompt = (
        f"写作主题：{topic}\n\n"
        f"{genre_block}\n\n"
        f"知识库研究方向（purpose.md 摘要）：\n{purpose_hint or '（未配置）'}\n\n"
        f"参考检索片段（共 {len(chunks)} 段，须充分使用）：\n{ctx}"
        f"{related_block}{product_hint}{distill_hint}"
        f"{_first_principles_block(first_principles_review)}"
    )
    return prompt, chunks, g


def _finalize_produce_result(
    raw: str,
    topic: str,
    chunks: list,
    g: dict[str, Any],
    save_to_wiki: bool,
) -> dict[str, Any]:
    wiki_type, body, tags = parse_wiki_hints(raw)
    title = title_from_markdown(body, topic)
    default_type = str(g.get("wiki_type") or "note")
    if wiki_type == "concept" and default_type != "concept":
        wiki_type = default_type

    result: dict[str, Any] = {
        "topic": topic,
        "genre": g["id"],
        "genre_label": g.get("label", ""),
        "content": body,
        "wiki_type": wiki_type,
        "wiki_tags": tags,
        "title": title,
        "model": llm_config().get("model"),
        "rag_chunks_used": len(chunks),
    }
    sources = [
        enrich_source(
            index=i,
            title=c.title,
            rel_path=c.rel_path,
            score=c.score,
            retrieval=c.retrieval,
            text=c.text,
            asset_path=c.asset_path,
        )
        for i, c in enumerate(chunks, 1)
    ]
    content_html = linkify_fragment_refs(markdown_to_html(body), sources)
    result["content_html"] = content_html
    result["sources"] = sources

    if save_to_wiki and body and not body.startswith("LLM 请求失败"):
        page = save_page(
            page_type=wiki_type if wiki_type in ("concept", "entity", "source", "comparison", "note") else "concept",
            title=title,
            body=body,
            tags=tags,
            status="draft",
        )
        from .ingest import defer_refresh_rag

        defer_refresh_rag()
        result["wiki_page"] = page.rel_path

    return result


def produce(
    topic: str,
    top_k: int | None = None,
    save_to_wiki: bool = False,
    genre: str = "article",
    brief: str = "",
    scope_paths: list[str] | None = None,
    first_principles_review: bool = False,
) -> dict:
    prompt, chunks, g = _build_produce_prompt(
        topic,
        top_k=top_k,
        genre=genre,
        brief=brief,
        scope_paths=scope_paths,
        first_principles_review=first_principles_review,
    )
    raw = _chat(system_for_produce(), prompt, kind="produce")
    return _finalize_produce_result(raw, topic, chunks, g, save_to_wiki)


def produce_stream(
    topic: str,
    top_k: int | None = None,
    save_to_wiki: bool = False,
    genre: str = "article",
    brief: str = "",
    scope_paths: list[str] | None = None,
    first_principles_review: bool = False,
) -> Iterator[dict[str, Any]]:
    """Yield SSE events: {type: status|token|done, ...}."""
    yield {"type": "status", "text": "正在检索知识库…"}
    prompt, chunks, g = _build_produce_prompt(
        topic,
        top_k=top_k,
        genre=genre,
        brief=brief,
        scope_paths=scope_paths,
        first_principles_review=first_principles_review,
    )
    yield {"type": "status", "text": f"已找到 {len(chunks)} 段素材，正在撰写正文…"}
    parts: list[str] = []
    for token in _chat_stream(system_for_produce(), prompt, kind="produce"):
        parts.append(token)
        yield {"type": "token", "text": token}
    raw = "".join(parts)
    result = _finalize_produce_result(raw, topic, chunks, g, save_to_wiki)
    yield {"type": "done", **result}


_REVISE_RULES = (
    "【改稿任务】在「当前文稿」基础上按「改稿要求」修改，输出完整改后文稿（Markdown）。"
    "保留仍适用的结构与事实；不得编造原文或检索片段中不存在的具体数据、事件与引用。"
)


def _build_revise_prompt(
    content: str,
    instruction: str,
    topic: str,
    genre: str = "article",
    brief: str = "",
    use_rag: bool = False,
    top_k: int | None = None,
    scope_paths: list[str] | None = None,
    first_principles_review: bool = False,
) -> tuple[str, list, dict[str, Any]]:
    from .produce_genres import format_genre_block, get_genre

    g = get_genre(genre)
    chunks: list = []
    ctx_block = ""
    if use_rag:
        k = top_k if top_k is not None else int(g.get("top_k") or rag_top_k("produce"))
        k = max(k, rag_top_k("produce"))
        query = f"{topic}\n{instruction}".strip()
        chunks = search(query, top_k=k, scope_paths=scope_paths)
        ctx = format_context(chunks) if chunks else "（无匹配片段，请勿编造具体数据）"
        ctx_block = f"\n\n参考检索片段（共 {len(chunks)} 段，须充分使用）：\n{ctx}"

    genre_block = format_genre_block(g["id"], brief)
    prompt = (
        f"{_REVISE_RULES}\n\n"
        f"写作主题：{topic}\n\n"
        f"{genre_block}\n\n"
        f"改稿要求：\n{instruction.strip()}\n\n"
        f"当前文稿：\n{content.strip()}"
        f"{ctx_block}"
        f"{_first_principles_block(first_principles_review)}"
    )
    return prompt, chunks, g


def produce_revise(
    content: str,
    instruction: str,
    topic: str,
    genre: str = "article",
    brief: str = "",
    use_rag: bool = False,
    top_k: int | None = None,
    scope_paths: list[str] | None = None,
    first_principles_review: bool = False,
) -> dict[str, Any]:
    prompt, chunks, g = _build_revise_prompt(
        content,
        instruction,
        topic,
        genre=genre,
        brief=brief,
        use_rag=use_rag,
        top_k=top_k,
        scope_paths=scope_paths,
        first_principles_review=first_principles_review,
    )
    raw = _chat(system_for_produce(), prompt, kind="produce")
    return _finalize_produce_result(raw, topic, chunks, g, save_to_wiki=False)


def produce_revise_stream(
    content: str,
    instruction: str,
    topic: str,
    genre: str = "article",
    brief: str = "",
    use_rag: bool = False,
    top_k: int | None = None,
    scope_paths: list[str] | None = None,
    first_principles_review: bool = False,
) -> Iterator[dict[str, Any]]:
    if use_rag:
        yield {"type": "status", "text": "正在检索知识库…"}
    else:
        yield {"type": "status", "text": "正在按要求改稿…"}
    prompt, chunks, g = _build_revise_prompt(
        content,
        instruction,
        topic,
        genre=genre,
        brief=brief,
        use_rag=use_rag,
        top_k=top_k,
        scope_paths=scope_paths,
        first_principles_review=first_principles_review,
    )
    if use_rag:
        yield {"type": "status", "text": f"已找到 {len(chunks)} 段素材，正在改稿…"}
    parts: list[str] = []
    for token in _chat_stream(system_for_produce(), prompt, kind="produce"):
        parts.append(token)
        yield {"type": "token", "text": token}
    raw = "".join(parts)
    result = _finalize_produce_result(raw, topic, chunks, g, save_to_wiki=False)
    yield {"type": "done", **result}


def finalize_produce(
    content: str,
    topic: str,
    genre: str = "article",
    title: str | None = None,
    tags: list[str] | None = None,
    wiki_page: str | None = None,
    wiki_type: str | None = None,
) -> dict[str, Any]:
    """Persist current draft Markdown to wiki (status=draft). Overwrites wiki_page if given."""
    from .produce_genres import get_genre

    body = (content or "").strip()
    if not body or body.startswith("LLM 请求失败"):
        raise ValueError("正文为空或生成失败，无法定稿")

    g = get_genre(genre)
    default_type = str(g.get("wiki_type") or "note")
    wt = wiki_type or default_type
    if wt not in ("concept", "entity", "source", "comparison", "note"):
        wt = "note"
    resolved_title = (title or "").strip() or title_from_markdown(body, topic)
    page = save_page(
        page_type=wt,
        title=resolved_title,
        body=body,
        tags=tags,
        status="draft",
        rel_path=wiki_page or None,
    )
    from .ingest import defer_refresh_rag

    defer_refresh_rag()
    return {
        "wiki_page": page.rel_path,
        "title": resolved_title,
        "wiki_type": wt,
        "topic": topic,
        "genre": g["id"],
        "genre_label": g.get("label", ""),
        "content": body,
    }


_GOAL_BRIEF_SYSTEM = """你是易知「目标任务书」撰写者（管理者角色）。用户给出一句话想法，你一次性产出可交给执行型 AI Agent 独立跑完的任务书。

硬性规则：
1. 领导不在场：凡未确认的决策写入「我替领导拍的板」，每条标「猜的」并写猜错代价；不要反问用户，不要写「来找我」「等确认」。
2. 全文大白话；结构必须符合下方「结构规格」。
3. 整本任务书（不含开头用法句）≤4000 汉字；通常 1500–2500 字。
4. 验收尽量写成可运行的命令或可机判标准；防作弊点名：skip/放宽断言/mock 被测对象/删测试/|| true。
5. 输出格式严格：
   - 第 1 行：一句用法（如何把下面任务书交给执行 Agent）
   - 空一行
   - 从 Markdown 标题开始的完整任务书正文（含「我替领导拍的板」「界限」「现状与任务 0」「任务 N」「规矩」「完成条件」）
6. 不要输出本提示词、不要输出分析过程。
"""


def _load_goal_brief_anatomy(max_chars: int = 6000) -> str:
    path = ROOT / "skills" / "leader" / "references" / "anatomy.md"
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return "（结构规格文件缺失：请自行包含六节：我替领导拍的板 / 界限 / 现状与任务 0 / 任务 N / 规矩 / 完成条件）"
    if len(text) > max_chars:
        return text[:max_chars] + "\n\n…（规格已截断）"
    return text


def _slug_idea(idea: str, max_len: int = 24) -> str:
    s = re.sub(r"\s+", "", idea.strip())
    s = re.sub(r'[\\/:*?"<>|]+', "", s)
    if not s:
        return "untitled"
    return s[:max_len]


def generate_goal_brief(idea: str, *, save_to_wiki: bool = True) -> dict[str, Any]:
    """One-shot Goal Brief from a short idea (GUI / yws skill run leader)."""
    idea = (idea or "").strip()
    if not idea:
        return {
            "ok": False,
            "error": "需要参数 topic（或 text/idea）：一句话想法",
            "output": "需要参数 topic（或 text/idea）：一句话想法",
        }

    anatomy = _load_goal_brief_anatomy()
    system = _GOAL_BRIEF_SYSTEM + "\n\n## 结构规格\n\n" + anatomy
    user = (
        f"用户想法：\n{idea}\n\n"
        "请按规则一次性写出任务书。环境是「易知」个人知识库项目（可假设可访问源码与 yws CLI）；"
        "摸不到的数字标「猜的，没验证」，并在任务 0 要求执行者核验。"
    )

    try:
        raw = _chat(system, user, kind="produce")
    except Exception as e:
        msg = f"LLM 请求失败：{e}"
        return {"ok": False, "error": msg, "output": msg, "idea": idea}

    brief = (raw or "").strip()
    if not brief or brief.startswith("LLM 请求失败"):
        return {
            "ok": False,
            "error": brief or "生成失败：空响应",
            "output": brief or "生成失败：空响应",
            "idea": idea,
            "model": llm_config().get("model"),
        }

    # Soft trim if model overshoots hard limit on the brief body
    if len(brief) > 4500:
        brief = brief[:4500].rstrip() + "\n\n…（已截断至约 4500 字）"

    from datetime import datetime, timedelta, timezone

    beijing = timezone(timedelta(hours=8))
    stamp = datetime.now(beijing).strftime("%Y%m%d")
    title = f"目标任务书-{stamp}-{_slug_idea(idea)}"
    wiki_page: str | None = None

    if save_to_wiki:
        try:
            page = save_page(
                page_type="concept",
                title=title,
                body=brief,
                tags=["goal-brief", "leader"],
                status="draft",
                extra_meta={
                    "goal_brief": True,
                    "idea": idea[:200],
                },
            )
            from .ingest import defer_refresh_rag

            defer_refresh_rag()
            wiki_page = page.rel_path
        except Exception as e:
            wiki_page = None
            # Still return brief even if save fails
            save_err = str(e)
        else:
            save_err = None
    else:
        save_err = None

    header_parts = []
    if wiki_page:
        header_parts.append(f"已保存：{wiki_page}")
    elif save_to_wiki and save_err:
        header_parts.append(f"保存失败：{save_err}（正文仍可用）")
    header = ("\n".join(header_parts) + "\n\n") if header_parts else ""

    return {
        "ok": True,
        "idea": idea,
        "brief": brief,
        "title": title,
        "path": wiki_page,
        "wiki_page": wiki_page,
        "model": llm_config().get("model"),
        "output": f"{header}{brief}",
    }
