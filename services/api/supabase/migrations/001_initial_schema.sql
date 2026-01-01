-- Maestro Super Database Schema
-- Run this in Supabase SQL Editor to set up the database

-- ============================================
-- STEP 1: Enable Extensions
-- ============================================
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================
-- STEP 2: Drop Existing Tables (if any)
-- ============================================
DROP TABLE IF EXISTS usage_events CASCADE;
DROP TABLE IF EXISTS queries CASCADE;
DROP TABLE IF EXISTS pointer_references CASCADE;
DROP TABLE IF EXISTS pointers CASCADE;
DROP TABLE IF EXISTS pages CASCADE;
DROP TABLE IF EXISTS disciplines CASCADE;
DROP TABLE IF EXISTS projects CASCADE;

-- Also drop old tables from previous schema
DROP TABLE IF EXISTS context_pointers CASCADE;
DROP TABLE IF EXISTS page_contexts CASCADE;
DROP TABLE IF EXISTS discipline_contexts CASCADE;
DROP TABLE IF EXISTS project_files CASCADE;

-- ============================================
-- STEP 3: Create Tables
-- ============================================

-- 1. Projects
CREATE TABLE projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- 2. Disciplines
CREATE TABLE disciplines (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL,           -- "architectural", "structural", "mep"
  display_name TEXT NOT NULL,   -- "Architectural", "Structural", "MEP"
  summary TEXT,                 -- AI-generated discipline context
  processed BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- 3. Pages
CREATE TABLE pages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  discipline_id UUID NOT NULL REFERENCES disciplines(id) ON DELETE CASCADE,
  page_name TEXT NOT NULL,      -- "A1.01"
  file_path TEXT NOT NULL,
  initial_context TEXT,         -- Pass 1 AI summary
  full_context TEXT,            -- Pass 2 AI summary after pointers
  processed_pass_1 BOOLEAN DEFAULT false,
  processed_pass_2 BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- 4. Pointers
CREATE TABLE pointers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  page_id UUID NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  description TEXT NOT NULL,    -- AI-generated description
  text_spans TEXT[],            -- array of extracted text elements
  bbox_x FLOAT NOT NULL,
  bbox_y FLOAT NOT NULL,
  bbox_width FLOAT NOT NULL,
  bbox_height FLOAT NOT NULL,
  png_path TEXT,                -- path to cropped image
  embedding vector(1024),       -- Voyage embeddings
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- 5. Pointer References
CREATE TABLE pointer_references (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_pointer_id UUID NOT NULL REFERENCES pointers(id) ON DELETE CASCADE,
  target_page_id UUID NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  justification TEXT NOT NULL,  -- the text span that triggered this reference
  created_at TIMESTAMPTZ DEFAULT now()
);

-- 6. Queries (chat history)
CREATE TABLE queries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT NOT NULL,
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  query_text TEXT NOT NULL,
  response_text TEXT,
  referenced_pointers JSONB,    -- [{pointer_id, relevance_score}]
  tokens_used INTEGER,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- 7. Usage Events (billing)
CREATE TABLE usage_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT NOT NULL,
  event_type TEXT NOT NULL,     -- 'gemini_extraction', 'claude_query', 'ocr_page', 'voyage_embedding'
  tokens_input INTEGER,
  tokens_output INTEGER,
  cost_cents INTEGER,
  metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================
-- STEP 4: Create Indexes
-- ============================================

-- Foreign key indexes
CREATE INDEX idx_disciplines_project ON disciplines(project_id);
CREATE INDEX idx_pages_discipline ON pages(discipline_id);
CREATE INDEX idx_pointers_page ON pointers(page_id);
CREATE INDEX idx_refs_source ON pointer_references(source_pointer_id);
CREATE INDEX idx_refs_target ON pointer_references(target_page_id);
CREATE INDEX idx_queries_user ON queries(user_id);
CREATE INDEX idx_queries_project ON queries(project_id);
CREATE INDEX idx_usage_user ON usage_events(user_id);

-- Vector similarity index (ivfflat with cosine distance)
-- Note: This index works best with 1000+ rows. Empty table is fine to start.
CREATE INDEX idx_pointers_embedding ON pointers
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ============================================
-- STEP 5: Create updated_at trigger function
-- ============================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply trigger to tables with updated_at
CREATE TRIGGER update_projects_updated_at
  BEFORE UPDATE ON projects
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_disciplines_updated_at
  BEFORE UPDATE ON disciplines
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_pages_updated_at
  BEFORE UPDATE ON pages
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_pointers_updated_at
  BEFORE UPDATE ON pointers
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
