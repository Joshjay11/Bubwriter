-- Migration 003: Add voice_mode column to generations table
--
-- Tracks which Voice model was used for each generation:
--   'default'    → DeepSeek V3 (fast, high-temperature)
--   'deep_voice' → DeepSeek R1 (slower, more deliberate)
--
-- Run in Supabase SQL Editor.

ALTER TABLE generations
  ADD COLUMN IF NOT EXISTS voice_mode TEXT DEFAULT 'default';

-- Backfill: all existing generations used V3 (the only option in v1)
-- No-op since DEFAULT handles it, but explicit for clarity.
