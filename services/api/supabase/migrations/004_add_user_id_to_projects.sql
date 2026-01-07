-- Migration: Add user_id to projects for data isolation
-- This is a breaking change - existing projects will be deleted

-- Drop existing projects (cascades to disciplines, pages, pointers, etc.)
DELETE FROM projects;

-- Add user_id column
ALTER TABLE projects ADD COLUMN user_id TEXT NOT NULL;

-- Create index for faster lookups by user
CREATE INDEX idx_projects_user_id ON projects(user_id);
