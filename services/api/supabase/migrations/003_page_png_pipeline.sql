-- Migration: Add columns for PNG pre-rendering pipeline
-- This enables server-side PDF-to-PNG conversion during upload

-- Add new columns to pages table for PNG and OCR storage
ALTER TABLE pages ADD COLUMN IF NOT EXISTS page_image_path TEXT;
ALTER TABLE pages ADD COLUMN IF NOT EXISTS page_image_ready BOOLEAN DEFAULT FALSE;
ALTER TABLE pages ADD COLUMN IF NOT EXISTS full_page_text TEXT;
ALTER TABLE pages ADD COLUMN IF NOT EXISTS ocr_data JSONB;
ALTER TABLE pages ADD COLUMN IF NOT EXISTS processed_ocr BOOLEAN DEFAULT FALSE;

-- Index for finding unprocessed pages efficiently
CREATE INDEX IF NOT EXISTS idx_pages_unprocessed
  ON pages(discipline_id)
  WHERE NOT processed_ocr OR NOT page_image_ready OR NOT processed_pass_1;

-- Comment explaining the new fields
COMMENT ON COLUMN pages.page_image_path IS 'Storage path to pre-rendered PNG (e.g., page-images/{project_id}/{page_id}.png)';
COMMENT ON COLUMN pages.page_image_ready IS 'True when PNG has been generated and uploaded to storage';
COMMENT ON COLUMN pages.full_page_text IS 'Full text extracted from PDF page via PyMuPDF';
COMMENT ON COLUMN pages.ocr_data IS 'JSON array of word positions: [{text, x, y, w, h, confidence}]';
COMMENT ON COLUMN pages.processed_ocr IS 'True when OCR extraction has completed';
