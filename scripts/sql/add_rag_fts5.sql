-- RAG FTS5 keyword index (idempotent). Run via scripts/migrate_rag_fts5.py
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    chunk_id UNINDEXED,
    rel_path UNINDEXED,
    title,
    content,
    tokenize='trigram'
);
