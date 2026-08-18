"""Shared list pagination helpers."""

from __future__ import annotations


def paginate(items: list, page: int = 1, size: int = 20, max_size: int = 100) -> dict:
    page = max(1, page)
    size = max(1, min(size, max_size))
    total = len(items)
    start = (page - 1) * size
    pages = max(1, (total + size - 1) // size) if total else 1
    if page > pages:
        page = pages
        start = (page - 1) * size
    return {
        "items": items[start : start + size],
        "total": total,
        "page": page,
        "size": size,
        "pages": pages,
    }
