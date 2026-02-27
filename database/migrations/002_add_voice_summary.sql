-- Phase 1: Add voice_summary column to voice_profiles
-- Run this in the Supabase SQL editor after 001_initial_schema.sql

ALTER TABLE voice_profiles ADD COLUMN IF NOT EXISTS voice_summary TEXT;
