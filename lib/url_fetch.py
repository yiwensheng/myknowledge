"""Fetch URL and convert to Markdown for knowledge base ingest."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse, urlunparse

from .config import ROOT
from .runtime_tools import find_bun

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


@dataclass
class FetchedPage:
    url: str
    title: str
    markdown: str
    method: str


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self._parts: list[str] = []
        self.title = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t in ("script", "style", "noscript"):
            self._skip += 1
        if t in ("p", "br", "div", "h1", "h2", "h3", "h4", "li", "tr"):
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        if t in ("p", "div", "h1", "h2", "h3", "h4", "li", "tr"):
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        text = data.strip()
        if text:
            self._parts.append(text + " ")


def _normalize_url(url: str) -> str:
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    parsed = urlparse(url)
    if "toutiao.com" in parsed.netloc.lower() and "/article/" in parsed.path:
        path = parsed.path.rstrip("/") + "/"
        return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))
    return url


def _toutiao_article_id(url: str) -> str | None:
    m = re.search(r"toutiao\.com/article/(\d+)", url, re.I)
    if m:
        return m.group(1)
    m = re.search(r"toutiao\.com/i(\d+)", url, re.I)
    if m:
        return m.group(1)
    m = re.search(r"toutiao\.com/w/(\d+)", url, re.I)
    if m:
        return m.group(1)
    return None


def _toutiao_canonical(url: str, aid: str) -> str:
    if re.search(r"/w/", url, re.I):
        return f"https://www.toutiao.com/w/{aid}/"
    return f"https://www.toutiao.com/article/{aid}/"


def _html_article_to_text(html: str) -> str:
    html = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    html = re.sub(r"(?i)</p>", "\n\n", html)
    html = re.sub(r"(?i)</div>", "\n", html)
    html = re.sub(r'(?i)<img[^>]+alt="([^"]*)"[^>]*>', r"\n[图: \1]\n", html)
    return _html_to_text(html)


def _fetch_toutiao(url: str) -> FetchedPage | None:
    """Toutiao desktop pages are JS anti-bot; mobile info API returns article JSON."""
    aid = _toutiao_article_id(url)
    if not aid:
        return None
    api = f"https://m.toutiao.com/i{aid}/info/v2/"
    canonical = _toutiao_canonical(url, aid)
    req = urllib.request.Request(
        api,
        headers={
            "User-Agent": USER_AGENT,
            "Referer": canonical,
            "Accept": "application/json, text/plain, */*",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, json.JSONDecodeError):
        return None
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return None
    title = str(data.get("title") or "").strip()
    content_html = str(data.get("content") or "").strip()
    canonical = _toutiao_canonical(url, aid)

    if not content_html:
        thread = data.get("thread")
        if isinstance(thread, dict):
            base = thread.get("thread_base")
            if isinstance(base, dict):
                plain = str(base.get("content") or "").strip()
                if len(plain) >= 20:
                    if not title:
                        title = plain.split("\n", 1)[0].strip()[:80]
                    md = f"# {title or '今日头条微头条'}\n\n来源: {canonical}\n\n{plain}"
                    return FetchedPage(
                        url=canonical,
                        title=title or "今日头条微头条",
                        markdown=md,
                        method="toutiao-api",
                    )

    if not content_html or len(content_html) < 30:
        return None
    body = _html_article_to_text(content_html)
    if len(body) < 50:
        return None
    md = f"# {title or '今日头条文章'}\n\n来源: {canonical}\n\n{body}"
    return FetchedPage(url=canonical, title=title or "今日头条文章", markdown=md, method="toutiao-api")


def _title_from_html(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if not m:
        return ""
    title = re.sub(r"\s+", " ", m.group(1)).strip()
    return _html_unescape(title)[:200]


def _html_unescape(text: str) -> str:
    import html as html_mod

    return html_mod.unescape(text)


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    text = "".join(parser._parts)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _find_baoyu_fetch() -> Path | None:
    env = os.environ.get("BAOYU_FETCH_PATH", "").strip()
    if env and Path(env).is_file():
        return Path(env)
    candidates = [
        ROOT / "third_party" / "baoyu-url-to-markdown" / "scripts" / "baoyu-fetch",
        Path.home() / ".agents" / "skills" / "baoyu-url-to-markdown" / "scripts" / "baoyu-fetch",
        Path.home() / ".baoyu-skills" / "baoyu-url-to-markdown" / "scripts" / "baoyu-fetch",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def _fetch_baoyu(url: str, tmp_out: Path) -> FetchedPage | None:
    reader = _find_baoyu_fetch()
    if not reader:
        return None
    bun = find_bun()
    if not bun:
        return None
    scripts_dir = reader.parent
    if not (scripts_dir / "node_modules").is_dir():
        subprocess.run([bun, "install"], cwd=str(scripts_dir), capture_output=True, timeout=120, check=False)
    try:
        subprocess.run(
            [bun, str(reader), url, "--output", str(tmp_out)],
            cwd=str(scripts_dir),
            capture_output=True,
            timeout=120,
            check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return None
    if not tmp_out.is_file():
        return None
    md = tmp_out.read_text(encoding="utf-8")
    title = ""
    for line in md.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    return FetchedPage(url=url, title=title or urlparse(url).netloc, markdown=md, method="baoyu-fetch")


def _fetch_jina(url: str) -> FetchedPage | None:
    jina_url = f"https://r.jina.ai/{url}"
    headers = {"User-Agent": USER_AGENT, "Accept": "text/plain"}
    key = os.environ.get("MYKNOWLEDGE_JINA_API_KEY", "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(jina_url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    if not text.strip() or len(text.strip()) < 80:
        return None
    title = ""
    body = text
    if text.startswith("Title:"):
        lines = text.splitlines()
        if lines:
            title = lines[0].replace("Title:", "").strip()
        if len(lines) > 1 and lines[1].startswith("URL Source:"):
            body = "\n".join(lines[2:]).strip()
        else:
            body = "\n".join(lines[1:]).strip()
    if not title:
        for line in body.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
    return FetchedPage(url=url, title=title or urlparse(url).netloc, markdown=body, method="jina")


def _fetch_basic(url: str) -> FetchedPage | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            charset = "utf-8"
            ct = resp.headers.get_content_charset()
            if ct:
                charset = ct
            html = raw.decode(charset, errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    title = _title_from_html(html) or urlparse(url).netloc
    text = _html_to_text(html)
    if len(text) < 50:
        return None
    md = f"# {title}\n\n来源: {url}\n\n{text}"
    return FetchedPage(url=url, title=title, markdown=md, method="basic-html")


def _is_weixin_url(url: str) -> bool:
    return "mp.weixin.qq.com" in urlparse(url).netloc.lower()


def _clean_weixin_content(md: str, title: str) -> tuple[str, str]:
    noise = ("微信扫一扫", "扫码分享", "长按识别", "阅读原文", "在看 ")
    lines = [ln for ln in md.splitlines() if not any(n in ln for n in noise)]
    body = "\n".join(lines).strip()
    bad_titles = {"mp.weixin.qq.com", "weixin.qq.com", "微信公众号", ""}
    if title.strip().lower() in bad_titles or title.strip() in bad_titles:
        for line in body.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
    return title, body


def _fetch_weixin(url: str, tmp_out: Path) -> FetchedPage | None:
    page = _fetch_baoyu(url, tmp_out)
    method = "baoyu-fetch"
    if not page or len(page.markdown.strip()) < 120:
        page = _fetch_jina(url)
        method = "jina"
    if not page or not page.markdown.strip():
        return None
    title, md = _clean_weixin_content(page.markdown, page.title)
    if len(md) < 120:
        return None
    if title.lower() in ("mp.weixin.qq.com", "weixin.qq.com") or not title.strip():
        return None
    if md.count("微信扫一扫") >= 2:
        return None
    return FetchedPage(url=url, title=title, markdown=md, method=f"{method}+weixin")


_FETCHER_LABELS = {
    "_fetch_toutiao": "今日头条接口",
    "_fetch_baoyu": "增强抓取",
    "_fetch_jina": "Jina Reader",
    "_fetch_basic": "基础 HTML",
}


def fetch_url(
    url: str,
    tmp_dir: Path | None = None,
    progress: Callable[[str, str], None] | None = None,
) -> FetchedPage:
    """Fetch URL content as Markdown; Bilibili uses subtitles; else toutiao → baoyu → jina → HTML."""
    url = _normalize_url(url)
    tmp_dir = tmp_dir or Path(os.environ.get("TEMP", "/tmp"))
    tmp_out = tmp_dir / f"myk-fetch-{abs(hash(url))}.md"

    from .bilibili_fetch import fetch_bilibili, is_bilibili_url

    if is_bilibili_url(url):
        if progress:
            progress("fetch", "正在获取 B 站字幕…")
        page = fetch_bilibili(url, progress=progress)
        page.title = page.title.strip() or urlparse(url).netloc
        if progress:
            progress("fetch", "抓取成功（B站字幕）")
        return page

    fetchers: list = []
    if _is_weixin_url(url):
        if _find_baoyu_fetch() and not find_bun():
            raise RuntimeError(
                "微信公众号抓取需要 bun（已找到 baoyu-fetch 脚本）。"
                "请打开「设置 → 能力检测」点击「一键修复可选工具」，"
                "或运行：python scripts/setup_optional_tools.py"
            )
        fetchers.append(_fetch_weixin)
    if _toutiao_article_id(url):
        fetchers.append(_fetch_toutiao)
    fetchers.extend([_fetch_baoyu, _fetch_jina, _fetch_basic])

    for fn in fetchers:
        label = _FETCHER_LABELS.get(fn.__name__, fn.__name__)
        if fn is _fetch_weixin:
            label = "微信公众号"
        if progress:
            progress("fetch", f"尝试 {label}…")
        try:
            if fn is _fetch_baoyu or fn is _fetch_weixin:
                page = fn(url, tmp_out)
            else:
                page = fn(url)  # type: ignore[call-arg]
        except Exception:
            page = None
        if page and page.markdown.strip():
            page.title = page.title.strip() or urlparse(url).netloc
            if progress:
                progress("fetch", f"抓取成功（{label}）")
            return page

    hint = ""
    if _toutiao_article_id(url):
        hint = "（今日头条已尝试移动端 API，含微头条 /w/ 与文章页）"
    if _find_baoyu_fetch() and not find_bun():
        hint += (
            "；增强抓取未启用：缺少 bun，请在「设置 → 能力检测」一键修复可选工具"
        )
    raise RuntimeError(
        f"无法抓取 URL 内容: {url}{hint}（已尝试 toutiao-api / baoyu-fetch / jina / 基础 HTML）"
    )
