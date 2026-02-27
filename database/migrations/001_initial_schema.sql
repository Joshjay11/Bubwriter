-- BUB Writer: Initial Schema
-- Run this in the Supabase SQL editor

-- Voice DNA profiles
CREATE TABLE voice_profiles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  profile_name TEXT NOT NULL,
  literary_dna JSONB NOT NULL,
  influences JSONB DEFAULT '{}',
  anti_slop JSONB DEFAULT '{}',
  voice_instruction TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Writing projects
CREATE TABLE projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  voice_profile_id UUID REFERENCES voice_profiles(id),
  title TEXT NOT NULL,
  genre TEXT,
  story_bible JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Generated scenes (history)
CREATE TABLE generations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id),
  user_prompt TEXT NOT NULL,
  brain_output TEXT,
  voice_output TEXT NOT NULL,
  polish_output TEXT,
  word_count INTEGER,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- User subscriptions
CREATE TABLE subscriptions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  stripe_customer_id TEXT,
  stripe_subscription_id TEXT,
  tier TEXT NOT NULL DEFAULT 'free',
  status TEXT NOT NULL DEFAULT 'active',
  current_period_end TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Enable RLS on all tables
ALTER TABLE voice_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE generations ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;

-- voice_profiles policies
CREATE POLICY "Users can view own voice profiles"
  ON voice_profiles FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can create own voice profiles"
  ON voice_profiles FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own voice profiles"
  ON voice_profiles FOR UPDATE
  USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own voice profiles"
  ON voice_profiles FOR DELETE
  USING (auth.uid() = user_id);

-- projects policies
CREATE POLICY "Users can view own projects"
  ON projects FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can create own projects"
  ON projects FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own projects"
  ON projects FOR UPDATE
  USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own projects"
  ON projects FOR DELETE
  USING (auth.uid() = user_id);

-- generations policies (access through project ownership)
CREATE POLICY "Users can view own generations"
  ON generations FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = generations.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can create generations in own projects"
  ON generations FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = generations.project_id
      AND projects.user_id = auth.uid()
    )
  );

-- subscriptions policies
CREATE POLICY "Users can view own subscription"
  ON subscriptions FOR SELECT
  USING (auth.uid() = user_id);
