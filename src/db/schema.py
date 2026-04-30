"""程序说明：定义 SQLite 初始化所需的表结构。"""

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS documents (
    doc_uid TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    doc_title TEXT NOT NULL,
    edition TEXT,
    author TEXT,
    source_name TEXT,
    tags_json TEXT,
    source_path TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    ingest_status TEXT NOT NULL,
    index_status TEXT NOT NULL,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_doc_id ON documents (doc_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents (ingest_status);
CREATE INDEX IF NOT EXISTS idx_documents_source_hash ON documents (source_hash);

CREATE TABLE IF NOT EXISTS document_sections (
    section_id TEXT PRIMARY KEY,
    doc_uid TEXT NOT NULL,
    section_title TEXT NOT NULL,
    section_level INTEGER NOT NULL,
    source_span TEXT,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (doc_uid) REFERENCES documents (doc_uid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_uid TEXT NOT NULL,
    section_id TEXT,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    source_span TEXT,
    token_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (doc_uid) REFERENCES documents (doc_uid) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc_uid ON chunks (doc_uid);
CREATE INDEX IF NOT EXISTS idx_chunks_section_id ON chunks (section_id);

CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
    chunk_id UNINDEXED,
    doc_uid UNINDEXED,
    content
);

CREATE TABLE IF NOT EXISTS ingest_jobs (
    job_id TEXT PRIMARY KEY,
    doc_uid TEXT NOT NULL,
    stage TEXT NOT NULL,
    status TEXT NOT NULL,
    error_message TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    FOREIGN KEY (doc_uid) REFERENCES documents (doc_uid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS quality_checks (
    check_id TEXT PRIMARY KEY,
    input_text TEXT NOT NULL,
    overall_verdict TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    summary TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quality_claims (
    claim_id TEXT PRIMARY KEY,
    check_id TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    verdict TEXT NOT NULL,
    confidence REAL NOT NULL,
    evidence TEXT NOT NULL,
    source_doc TEXT,
    source_span TEXT,
    review_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (check_id) REFERENCES quality_checks (check_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS rule_hits (
    rule_hit_id TEXT PRIMARY KEY,
    check_id TEXT NOT NULL,
    claim_id TEXT,
    rule_code TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    hit_level TEXT NOT NULL,
    hit_message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (check_id) REFERENCES quality_checks (check_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS review_records (
    review_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL,
    review_action TEXT NOT NULL,
    reviewed_verdict TEXT,
    review_note TEXT,
    reviewer TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""
