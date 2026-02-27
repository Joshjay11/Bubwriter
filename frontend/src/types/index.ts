export interface VoiceProfile {
  id: string;
  user_id: string;
  profile_name: string;
  literary_dna: Record<string, unknown>;
  influences: Record<string, unknown>;
  anti_slop: Record<string, unknown>;
  voice_instruction: string | null;
  created_at: string;
  updated_at: string;
}

export interface Project {
  id: string;
  user_id: string;
  voice_profile_id: string | null;
  title: string;
  genre: string | null;
  story_bible: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface Generation {
  id: string;
  project_id: string;
  user_prompt: string;
  voice_output: string;
  polish_output: string | null;
  word_count: number | null;
  created_at: string;
}

export interface Subscription {
  id: string;
  user_id: string;
  tier: "free" | "writer" | "author";
  status: string;
  current_period_end: string | null;
  created_at: string;
  updated_at: string;
}
