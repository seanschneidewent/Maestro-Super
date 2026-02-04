-- Local dev schema initialization
-- Creates all tables matching production (Supabase) schema
-- Uses UUID types everywhere (matching Supabase's native UUID handling)

CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- Projects
-- ============================================================================
CREATE TABLE projects (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_projects_user_id ON projects(user_id);

-- ============================================================================
-- Disciplines
-- ============================================================================
CREATE TABLE disciplines (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    project_id VARCHAR(36) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    code VARCHAR(5) NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(project_id, code)
);
CREATE INDEX ix_disciplines_project_id ON disciplines(project_id);

-- ============================================================================
-- Pages
-- ============================================================================
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
    -- Legacy OCR
    full_page_text TEXT,
    ocr_data JSONB,
    processed_ocr BOOLEAN NOT NULL DEFAULT false,
    -- Agentic Vision
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
    -- Vector embedding
    page_embedding vector(1024),
    -- Legacy
    semantic_index JSONB,
    context_markdown TEXT,
    details JSONB,
    processing_status VARCHAR(50) DEFAULT 'pending',
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_pages_discipline_id ON pages(discipline_id);

-- ============================================================================
-- Pointers
-- ============================================================================
CREATE TABLE pointers (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    page_id VARCHAR(36) NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    x_norm FLOAT NOT NULL,
    y_norm FLOAT NOT NULL,
    w_norm FLOAT NOT NULL,
    h_norm FLOAT NOT NULL,
    title VARCHAR(255),
    description TEXT,
    snapshot_url VARCHAR(500),
    ai_technical_description TEXT,
    ai_trade_category VARCHAR(10),
    ai_elements JSONB,
    ai_measurements JSONB,
    ai_recommendations TEXT,
    ai_issues JSONB,
    text_content JSONB,
    ocr_data JSONB,
    committed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_pointers_page_id ON pointers(page_id);

-- ============================================================================
-- Pointer References
-- ============================================================================
CREATE TABLE pointer_references (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    pointer_id VARCHAR(36) NOT NULL REFERENCES pointers(id) ON DELETE CASCADE,
    target_page_id VARCHAR(36) NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    reference_text TEXT,
    confidence FLOAT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_pointer_references_pointer_id ON pointer_references(pointer_id);
CREATE INDEX ix_pointer_references_target_page_id ON pointer_references(target_page_id);

-- ============================================================================
-- Conversations
-- ============================================================================
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    project_id VARCHAR(36) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_conversations_user_id ON conversations(user_id);
CREATE INDEX ix_conversations_project_id ON conversations(project_id);

-- ============================================================================
-- Queries
-- ============================================================================
CREATE TABLE queries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    project_id VARCHAR(36) REFERENCES projects(id) ON DELETE CASCADE,
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    query_text TEXT NOT NULL,
    response_text TEXT,
    referenced_pointers JSONB,
    tokens_used INTEGER,
    trace JSONB,
    hidden BOOLEAN NOT NULL DEFAULT false,
    mode VARCHAR(20),
    sequence_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_queries_project_id ON queries(project_id);
CREATE INDEX ix_queries_user_id ON queries(user_id);
CREATE INDEX ix_queries_conversation_id ON queries(conversation_id);

-- ============================================================================
-- Query Pages (junction table)
-- ============================================================================
CREATE TABLE query_pages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_id UUID NOT NULL REFERENCES queries(id) ON DELETE CASCADE,
    page_id VARCHAR(36) NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    relevance_score FLOAT,
    display_order INTEGER NOT NULL DEFAULT 0,
    deep_mode_findings JSONB,
    deep_mode_bboxes JSONB,
    deep_mode_annotated_images JSONB,
    deep_mode_status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_query_pages_query_id ON query_pages(query_id);
CREATE INDEX ix_query_pages_page_id ON query_pages(page_id);

-- ============================================================================
-- Processing Jobs
-- ============================================================================
CREATE TABLE processing_jobs (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    project_id VARCHAR(36) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    job_type VARCHAR(50) NOT NULL DEFAULT 'brain_mode',
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    total_pages INTEGER NOT NULL DEFAULT 0,
    processed_pages INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_processing_jobs_project_id ON processing_jobs(project_id);

-- ============================================================================
-- Usage Events
-- ============================================================================
CREATE TABLE usage_events (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    tokens_input INTEGER,
    tokens_output INTEGER,
    cost_cents INTEGER,
    event_metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_usage_events_user_id ON usage_events(user_id);

-- ============================================================================
-- User Usage (aggregate tracking)
-- ============================================================================
CREATE TABLE user_usage (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id VARCHAR(255) NOT NULL UNIQUE,
    total_queries INTEGER NOT NULL DEFAULT 0,
    total_pages_processed INTEGER NOT NULL DEFAULT 0,
    total_tokens_used INTEGER NOT NULL DEFAULT 0,
    total_cost_cents INTEGER NOT NULL DEFAULT 0,
    last_query_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_user_usage_user_id ON user_usage(user_id);

-- ============================================================================
-- Project Memory Files (Learning System)
-- ============================================================================
CREATE TABLE project_memory_files (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    project_id VARCHAR(36) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    file_type VARCHAR(50) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(project_id, file_type, file_name)
);
CREATE INDEX ix_project_memory_files_project_id ON project_memory_files(project_id);
