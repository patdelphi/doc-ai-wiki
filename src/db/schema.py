"""程序说明：定义 SQLite 初始化所需的表结构。"""

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS knowledge_bases (
    knowledge_base_id TEXT PRIMARY KEY,
    knowledge_base_name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    doc_uid TEXT PRIMARY KEY,
    knowledge_base_id TEXT NOT NULL DEFAULT 'default',
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
    updated_at TEXT NOT NULL,
    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases (knowledge_base_id)
);

CREATE INDEX IF NOT EXISTS idx_documents_knowledge_base_id ON documents (knowledge_base_id);
CREATE INDEX IF NOT EXISTS idx_documents_doc_id ON documents (doc_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents (ingest_status);
CREATE INDEX IF NOT EXISTS idx_documents_source_hash ON documents (source_hash);

CREATE TABLE IF NOT EXISTS document_sections (
    section_id TEXT PRIMARY KEY,
    doc_uid TEXT NOT NULL,
    section_title TEXT NOT NULL,
    section_level INTEGER NOT NULL,
    heading_path TEXT,
    source_start_line INTEGER,
    source_end_line INTEGER,
    source_anchor TEXT,
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
    heading_path TEXT,
    source_start_line INTEGER,
    source_end_line INTEGER,
    page_no INTEGER,
    chunk_type TEXT NOT NULL DEFAULT 'paragraph',
    content_hash TEXT,
    source_anchor TEXT,
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
    knowledge_base_id TEXT NOT NULL DEFAULT 'default',
    input_text TEXT NOT NULL,
    template_id TEXT,
    template_name TEXT,
    overall_verdict TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    summary TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases (knowledge_base_id)
);

CREATE INDEX IF NOT EXISTS idx_quality_checks_knowledge_base_id ON quality_checks (knowledge_base_id);

CREATE TABLE IF NOT EXISTS quality_claims (
    claim_id TEXT PRIMARY KEY,
    check_id TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    verdict TEXT NOT NULL,
    risk_level TEXT NOT NULL DEFAULT 'medium',
    confidence REAL NOT NULL,
    evidence TEXT NOT NULL,
    evidence_details_json TEXT NOT NULL DEFAULT '[]',
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
    created_at TEXT NOT NULL,
    FOREIGN KEY (claim_id) REFERENCES quality_claims (claim_id) ON DELETE CASCADE
);

-- M6 修复：为高频查询列补充索引
CREATE INDEX IF NOT EXISTS idx_quality_claims_check_id ON quality_claims (check_id);
CREATE INDEX IF NOT EXISTS idx_quality_claims_review_status ON quality_claims (review_status);
CREATE INDEX IF NOT EXISTS idx_rule_hits_check_id ON rule_hits (check_id);
CREATE INDEX IF NOT EXISTS idx_review_records_claim_id ON review_records (claim_id);
"""
