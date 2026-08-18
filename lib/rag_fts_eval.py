"""Evaluate whether SQLite FTS5 keyword index is recommended."""

from __future__ import annotations

FTS5_CHUNK_THRESHOLD = 20_000


def fts5_recommendation(chunk_count: int) -> dict[str, object]:
    recommended = chunk_count >= FTS5_CHUNK_THRESHOLD
    return {
        "fts5_threshold": FTS5_CHUNK_THRESHOLD,
        "fts5_recommended": recommended,
        "fts5_status": "recommended" if recommended else "not_needed",
        "note": (
            f"当前 {chunk_count} 段，已达到 FTS5 评估阈值（≥{FTS5_CHUNK_THRESHOLD}），"
            "建议后续版本启用 SQLite FTS5 替代全量 TF 扫描。"
            if recommended
            else f"当前 {chunk_count} 段，暂无需 FTS5（阈值 {FTS5_CHUNK_THRESHOLD}）。"
        ),
    }
