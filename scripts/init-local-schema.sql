-- init-local-schema-v3.sql
-- All IDs and FK references use the SAME type as the SQLAlchemy model declares.
-- Models with String(36) → VARCHAR(36), Models with PGUUID → UUID
-- Cross-type FKs handled by using the PARENT's type for the FK column.
-- PostgreSQL handles varchar↔uuid implicit casting at runtime for String(36) models.

CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- Tables with String(36) IDs
-- ============================================================

CREATE TABLE projects (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_projects_user_id ON projects(user_id);

CREATE TABLE disciplines (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    project_id VARCHAR(36) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    summary TEXT,
    processed BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_disciplines_project_id ON disciplines(project_id);

CREATE TABLE pages (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    discipline_id VARCHAR(36) NOT NULL REFERENCES disciplines(id) ON DELETE CASCADE,
    page_name VARCHAR(100) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    page_index INTEGER NOT NULL DEFAULT 0,
    initial_context TEXT,
    full_context TEXT,
    processed_pass_1 BOOLEAN NOT NULL DEFAULT false,
    processed_pass_2 BOOLEAN NOT NULL DEFAULT false,
    page_image_path VARCHAR(500),
    page_image_ready BOOLEAN NOT NULL DEFAULT false,
    full_page_text TEXT,
    ocr_data JSONB,
    processed_ocr BOOLEAN NOT NULL DEFAULT false,
    regions JSONB,
    sheet_reflection TEXT,
    page_type VARCHAR(50),
    cross_references JSONB,
    sheet_info JSONB,
    master_index JSONB,
    questions_answered JSONB,
    sheet_card JSONB,
    processing_time_ms INTEGER,
    processing_error TEXT,
    page_embedding vector(1024),
    semantic_index JSONB,
    context_markdown TEXT,
    details JSONB,
    processing_status VARCHAR(50) DEFAULT 'pending',
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_pages_discipline_id ON pages(discipline_id);

CREATE TABLE pointers (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    page_id VARCHAR(36) NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    text_spans TEXT[],
    ocr_data JSONB,
    bbox_x DOUBLE PRECISION NOT NULL,
    bbox_y DOUBLE PRECISION NOT NULL,
    bbox_width DOUBLE PRECISION NOT NULL,
    bbox_height DOUBLE PRECISION NOT NULL,
    png_path VARCHAR(500),
    needs_embedding BOOLEAN NOT NULL DEFAULT false,
    embedding vector(1024),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_pointers_page_id ON pointers(page_id);

CREATE TABLE pointer_references (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    source_pointer_id VARCHAR(36) NOT NULL REFERENCES pointers(id) ON DELETE CASCADE,
    target_page_id VARCHAR(36) NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    reference_text VARCHAR(50),
    confidence DOUBLE PRECISION DEFAULT 1.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_pointer_references_source ON pointer_references(source_pointer_id);
CREATE INDEX ix_pointer_references_target ON pointer_references(target_page_id);

CREATE TABLE processing_jobs (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    project_id VARCHAR(36) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    job_type VARCHAR(20) NOT NULL DEFAULT 'brain_mode',
    total_pages INTEGER NOT NULL DEFAULT 0,
    processed_pages INTEGER NOT NULL DEFAULT 0,
    current_page_id VARCHAR(36),
    current_page_name VARCHAR(200),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_processing_jobs_project_id ON processing_jobs(project_id);

CREATE TABLE usage_events (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    model_name VARCHAR(100),
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cost_usd DOUBLE PRECISION DEFAULT 0.0,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_usage_events_user_id ON usage_events(user_id);

CREATE TABLE user_usage (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id VARCHAR(255) NOT NULL UNIQUE,
    total_queries INTEGER NOT NULL DEFAULT 0,
    total_pages_processed INTEGER NOT NULL DEFAULT 0,
    total_input_tokens BIGINT NOT NULL DEFAULT 0,
    total_output_tokens BIGINT NOT NULL DEFAULT 0,
    total_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    last_query_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_user_usage_user_id ON user_usage(user_id);

-- ============================================================
-- Tables with UUID IDs (Conversation/Query models use PGUUID)
-- ============================================================

-- conversations.project_id references projects.id (varchar(36))
-- The PGUUID model sends UUID params; we need UUID column + UUID FK
-- Solution: use UUID column type, but reference projects.id with a CAST
-- Actually PostgreSQL doesn't allow cross-type FKs, so we skip the FK constraint
-- and rely on application-level integrity (same as production Supabase).

CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    project_id UUID NOT NULL,  -- No FK constraint (type mismatch with projects.id varchar)
    title TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_conversations_user_id ON conversations(user_id);
CREATE INDEX ix_conversations_project_id ON conversations(project_id);

CREATE TABLE queries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    project_id UUID,  -- No FK constraint (type mismatch with projects.id varchar)
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    query_text TEXT NOT NULL,
    response_text TEXT,
    display_title VARCHAR(100),
    sequence_order INTEGER,
    referenced_pointers JSONB,
    trace JSONB,
    tokens_used INTEGER,
    hidden BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_queries_user_id ON queries(user_id);
CREATE INDEX ix_queries_project_id ON queries(project_id);
CREATE INDEX ix_queries_conversation_id ON queries(conversation_id);

CREATE TABLE query_pages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_id UUID NOT NULL REFERENCES queries(id) ON DELETE CASCADE,
    page_id UUID NOT NULL,  -- No FK constraint (type mismatch with pages.id varchar)
    page_order INTEGER NOT NULL,
    pointers_shown JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_query_pages_query_id ON query_pages(query_id);
CREATE INDEX ix_query_pages_page_id ON query_pages(page_id);

-- ============================================================
-- Project Memory (Big Maestro learning)
-- ============================================================

CREATE TABLE project_memory_files (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    project_id VARCHAR(36) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    file_type VARCHAR(50) NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_project_memory_project_id ON project_memory_files(project_id);

-- ============================================================
-- Alembic
-- ============================================================

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL
);
INSERT INTO alembic_version VALUES ('head');
