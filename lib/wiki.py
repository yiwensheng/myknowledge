"""Wiki Markdown CRUD and YAML parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import CONTENT_DIRS, SCAN_DIRS, TYPE_TO_DIR, wiki_root

BEIJING = timezone(timedelta(hours=8))


@dataclass
class WikiPage:
    path: Path
    rel_path: str
    title: str
    type: str
    tags: list[str]
    created: str
    updated: str
    status: str
    links: list[str]
    body: str
    source_url: str = ""
    asset_path: str = ""
    asset_mime: str = ""
    memo: bool = False
    pinned: bool = False
    folder_ids: list[str] | None = None

    def to_dict(self) -> dict:
        d = {
            "rel_path": self.rel_path,
            "title": self.title,
            "type": self.type,
            "tags": self.tags,
            "created": self.created,
            "updated": self.updated,
            "status": self.status,
            "links": self.links,
            "source_url": self.source_url,
            "memo": self.memo,
            "pinned": self.pinned,
            "folder_ids": list(self.folder_ids or []),
        }
        if self.asset_path:
            d["asset_path"] = self.asset_path
        if self.asset_mime:
            d["asset_mime"] = self.asset_mime
        return d


def today_beijing() -> str:
    return datetime.now(BEIJING).strftime("%Y-%m-%d")


def parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n(.*)", text, re.DOTALL)
    if not m:
        return {}, text
    raw, body = m.group(1), m.group(2)
    try:
        import yaml  # type: ignore

        meta = yaml.safe_load(raw) or {}
        return (meta if isinstance(meta, dict) else {}), body
    except Exception:
        meta: dict = {}
        for line in raw.splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            k, v = k.strip(), v.strip()
            if v.startswith("[") and v.endswith("]"):
                inner = v[1:-1].strip()
                meta[k] = (
                    [x.strip().strip('"').strip("'") for x in inner.split(",") if x.strip()]
                    if inner
                    else []
                )
            else:
                meta[k] = v.strip('"').strip("'")
        return meta, body


def serialize_page(meta: dict, body: str) -> str:
    try:
        import yaml  # type: ignore

        header = yaml.dump(meta, allow_unicode=True, default_flow_style=False, sort_keys=False)
    except Exception:
        lines = ["---"]
        for k, v in meta.items():
            if isinstance(v, list):
                inner = ", ".join(f'"{x}"' for x in v)
                lines.append(f"{k}: [{inner}]")
            else:
                lines.append(f'{k}: "{v}"' if isinstance(v, str) and " " in v else f"{k}: {v}")
        lines.append("---")
        header = "\n".join(lines) + "\n"
    return f"---\n{header.rstrip()}\n---\n{body.lstrip()}"


def slugify(title: str) -> str:
    s = re.sub(r'[<>:"/\\|?*]', "", title.strip())
    s = re.sub(r"\s+", "-", s)
    return s[:80] or "untitled"


def read_page(path: Path, root: Path | None = None) -> WikiPage:
    root = root or wiki_root()
    text = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)
    rel = path.relative_to(root).as_posix()
    return WikiPage(
        path=path,
        rel_path=rel,
        title=str(meta.get("title") or path.stem),
        type=str(meta.get("type") or "note"),
        tags=[str(t) for t in (meta.get("tags") or [])],
        created=str(meta.get("created") or ""),
        updated=str(meta.get("updated") or meta.get("created") or ""),
        status=str(meta.get("status") or "draft"),
        links=[str(x) for x in (meta.get("links") or [])],
        body=body,
        source_url=str(meta.get("source_url") or ""),
        asset_path=str(meta.get("asset_path") or ""),
        asset_mime=str(meta.get("asset_mime") or ""),
        memo=bool(meta.get("memo")),
        pinned=bool(meta.get("pinned")),
        folder_ids=[str(x) for x in (meta.get("folder_ids") or []) if str(x).strip()],
    )


def list_pages(
    root: Path | None = None,
    type_filter: str | None = None,
    include_inbox: bool = True,
) -> list[WikiPage]:
    root = root or wiki_root()
    pages: list[WikiPage] = []
    dirs = list(SCAN_DIRS) if include_inbox else list(CONTENT_DIRS)
    for d in dirs:
        base = root / d
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            if "inbox-processed" in path.parts:
                continue
            p = read_page(path, root)
            if type_filter and p.type != type_filter:
                continue
            pages.append(p)
    return pages


def save_page(
    page_type: str,
    title: str,
    body: str,
    tags: list[str] | None = None,
    status: str = "draft",
    links: list[str] | None = None,
    source_url: str = "",
    asset_path: str = "",
    asset_mime: str = "",
    rel_path: str | None = None,
    root: Path | None = None,
    extra_meta: dict | None = None,
) -> WikiPage:
    root = root or wiki_root()
    dir_name = TYPE_TO_DIR.get(page_type, "notes")
    slug = slugify(title)
    if rel_path:
        path = root / rel_path
    else:
        path = root / dir_name / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)

    existing_meta: dict = {}
    if path.exists():
        existing_meta, _ = parse_frontmatter(path.read_text(encoding="utf-8"))

    today = today_beijing()
    meta = {
        "title": title,
        "type": page_type,
        "tags": tags or existing_meta.get("tags") or [],
        "created": existing_meta.get("created") or today,
        "updated": today,
        "status": status,
        "links": links if links is not None else existing_meta.get("links") or [],
    }
    if source_url or existing_meta.get("source_url"):
        meta["source_url"] = source_url or existing_meta.get("source_url", "")
    ap = asset_path or existing_meta.get("asset_path", "")
    am = asset_mime or existing_meta.get("asset_mime", "")
    if ap:
        meta["asset_path"] = ap
    if am:
        meta["asset_mime"] = am
    if "memo" in existing_meta:
        meta["memo"] = bool(existing_meta.get("memo"))
    if "pinned" in existing_meta:
        meta["pinned"] = bool(existing_meta.get("pinned"))
    if "folder_ids" in existing_meta and (not extra_meta or "folder_ids" not in extra_meta):
        meta["folder_ids"] = [
            str(x) for x in (existing_meta.get("folder_ids") or []) if str(x).strip()
        ]
    if extra_meta:
        meta.update(extra_meta)

    if not existing_meta.get("memo") and not body.lstrip().startswith("#"):
        body = f"# {title}\n\n{body}"

    path.write_text(serialize_page(meta, body), encoding="utf-8")
    return read_page(path, root)


def delete_page(rel_path: str, root: Path | None = None) -> bool:
    root = root or wiki_root()
    rel = rel_path.replace("\\", "/").strip().lstrip("/")
    path = (root / rel).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return False
    if path.is_file():
        path.unlink()
        return True
    return False


def search_keyword(
    query: str,
    root: Path | None = None,
    type_filter: str | None = None,
    limit: int = 20,
) -> list[WikiPage]:
    q = query.lower().strip()
    results: list[tuple[int, WikiPage]] = []
    for p in list_pages(root, type_filter=type_filter, include_inbox=True):
        score = 0
        if q:
            hay = f"{p.title} {' '.join(p.tags)} {p.body}".lower()
            if q in p.title.lower():
                score += 10
            if q in hay:
                score += 2
            if q not in hay:
                continue
        else:
            score = 1
        results.append((score, p))
    results.sort(key=lambda x: (-x[0], x[1].title))
    return [p for _, p in results[:limit]]
