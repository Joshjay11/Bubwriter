-- Migration 004: Add missing columns and indexes to generations, voice_profiles, projects
--
-- Fixes identified in March 16 2026 codebase audit:
--   1. generations.user_id — code writes/queries this but column didn't exist
--   2. generations scene columns — scene_label, scene_order, is_pinned for workspace
--   3. Missing indexes on frequently queried foreign keys
--
-- Run in Supabase SQL Editor.

-- ============================================================
-- 1. Fix missing user_id on generations
-- ============================================================
ALTER TABLE generations
  ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id);

-- ============================================================
-- 2. Fix missing scene management columns
-- ============================================================
ALTER TABLE generations
  ADD COLUMN IF NOT EXISTS scene_label TEXT;

ALTER TABLE generations
  ADD COLUMN IF NOT EXISTS scene_order INTEGER DEFAULT 0;

ALTER TABLE generations
  ADD COLUMN IF NOT EXISTS is_pinned BOOLEAN DEFAULT FALSE;

-- ============================================================
-- 3. Add indexes (none exist currently)
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_generations_user_id ON generations(user_id);
CREATE INDEX IF NOT EXISTS idx_generations_project_id ON generations(project_id);
CREATE INDEX IF NOT EXISTS idx_voice_profiles_user_id ON voice_profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id);
