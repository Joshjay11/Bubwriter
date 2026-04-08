import { createClient } from "@/lib/supabase/client";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface ApiError {
  detail: string;
}

async function getAuthHeaders(): Promise<Record<string, string>> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session?.access_token) {
    return { "Content-Type": "application/json" };
  }

  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${session.access_token}`,
  };
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      ...headers,
      ...(options.headers as Record<string, string>),
    },
  });

  if (!response.ok) {
    const error: ApiError = await response.json().catch(() => ({
      detail: `Request failed with status ${response.status}`,
    }));
    throw new Error(error.detail);
  }

  return response.json() as Promise<T>;
}

export async function apiStream(
  path: string,
  body: Record<string, unknown>,
  onChunk: (content: string) => void,
  onDone?: () => void
): Promise<void> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const error: ApiError = await response.json().catch(() => ({
      detail: `Request failed with status ${response.status}`,
    }));
    throw new Error(error.detail);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const data = JSON.parse(line.slice(6));
      if (data.done) {
        onDone?.();
        return;
      }
      if (data.content) {
        onChunk(data.content);
      }
    }
  }

  onDone?.();
}

// --- Conversation Import (file upload + SSE) ---

export interface ConversationImportStats {
  total_conversations: number;
  messages_analyzed: number;
  words_analyzed: number;
}

export async function apiConversationImport(
  file: File,
  sessionId: string,
  onProgress: (percent: number, detail: string) => void,
  onDone: (stats: ConversationImportStats) => void,
  onError: (detail: string) => void
): Promise<void> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  const formData = new FormData();
  formData.append("file", file);
  formData.append("session_id", sessionId);

  const headers: Record<string, string> = {};
  if (session?.access_token) {
    headers.Authorization = `Bearer ${session.access_token}`;
  }
  // Do NOT set Content-Type — the browser sets it with the multipart boundary

  const response = await fetch(
    `${API_URL}/api/voice-discovery/import-conversations`,
    {
      method: "POST",
      headers,
      body: formData,
    }
  );

  if (!response.ok) {
    const error: ApiError = await response.json().catch(() => ({
      detail: `Upload failed with status ${response.status}`,
    }));
    throw new Error(error.detail);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        const data = JSON.parse(line.slice(6));
        if (data.type === "progress") {
          onProgress(data.percent ?? 0, data.detail ?? "");
        } else if (data.type === "done") {
          onDone(data.stats ?? {});
          return;
        } else if (data.type === "error") {
          onError(data.detail ?? "Import failed.");
          return;
        }
      } catch (e) {
        if (e instanceof SyntaxError) continue;
        throw e;
      }
    }
  }
}

// --- Generation Stream ---

export interface SlopScoreResult {
  passed: boolean;
  violation_count: number;
  violations: SlopViolation[];
  slop_score: number;
  word_count: number;
}

export interface SlopViolation {
  type: string;
  matches: string[];
  count: number;
}

export interface GenerationEvent {
  type:
    | "stage"
    | "skeleton"
    | "token"
    | "polish_complete"
    | "bible_suggestions"
    | "slop_score"
    | "done"
    | "error";
  stage?: string;
  message?: string;
  content?: string;
  data?: string | SlopScoreResult;
  suggestions?: ExtractionSuggestions;
  metadata?: {
    word_count: number;
    generation_id: string;
  };
}

// --- Extraction Loop Types ---

export interface CharacterSuggestion {
  name: string;
  description: string;
  role: string;
  first_appearance: string;
}

export interface LocationSuggestion {
  name: string;
  description: string;
  sensory_details: Record<string, string>;
  first_appearance: string;
}

export interface CharacterUpdate {
  character_name: string;
  character_id: string | null;
  update_type: string;
  detail: string;
}

export interface WorldRuleSuggestion {
  category: string;
  rule: string;
  exceptions: string[];
  implications: string;
}

export interface PlotBeatSuggestion {
  beat: string;
  characters_involved: string[];
  consequences: string[];
}

export interface KnowledgeEvent {
  type: string; // "secret_established", "knowledge_gained", "pov_leak_warning"
  summary: string;
  character_names: string[];
  witnesses: string[];
  non_witnesses: string[];
  method: string | null;
  issue: string | null; // for pov_leak_warning
}

export interface TimelineEvent {
  event: string;
  when: string;
  characters_present: string[];
}

export interface StateChange {
  entity_type: string; // "character", "object", "location"
  entity_name: string;
  state_type: string; // "physical", "emotional", "resource", "relationship"
  description: string;
  previous_state: string | null;
}

export interface ContradictionWarning {
  issue: string;
  conflicting_fact: string;
  established_in: string;
}

export interface ExtractionSuggestions {
  new_characters: CharacterSuggestion[];
  new_locations: LocationSuggestion[];
  character_updates: CharacterUpdate[];
  new_world_rules: WorldRuleSuggestion[];
  plot_beats: PlotBeatSuggestion[];
  knowledge_events: KnowledgeEvent[];
  timeline_events: TimelineEvent[];
  state_changes: StateChange[];
  contradiction_warnings: ContradictionWarning[];
}

export async function apiGenerationStream(
  path: string,
  body: Record<string, unknown>,
  onEvent: (event: GenerationEvent) => void
): Promise<void> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const error: ApiError = await response.json().catch(() => ({
      detail: `Request failed with status ${response.status}`,
    }));
    throw new Error(error.detail);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        const event = JSON.parse(line.slice(6)) as GenerationEvent;
        onEvent(event);
        if (event.type === "done" || event.type === "error") return;
      } catch (e) {
        if (e instanceof SyntaxError) continue;
        throw e;
      }
    }
  }
}

// --- Interview Stream ---

interface InterviewDoneData {
  interview_complete: boolean;
  question_number: number;
}

export async function apiInterviewStream(
  path: string,
  body: Record<string, unknown>,
  onToken: (content: string) => void,
  onDone: (data: InterviewDoneData) => void
): Promise<void> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const error: ApiError = await response.json().catch(() => ({
      detail: `Request failed with status ${response.status}`,
    }));
    throw new Error(error.detail);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        const data = JSON.parse(line.slice(6));
        if (data.type === "token" && data.content) {
          onToken(data.content);
        } else if (data.type === "done") {
          onDone({
            interview_complete: data.interview_complete ?? false,
            question_number: data.question_number ?? 0,
          });
          return;
        } else if (data.type === "error") {
          throw new Error(data.content ?? "Interview error");
        }
      } catch (e) {
        if (e instanceof SyntaxError) continue;
        throw e;
      }
    }
  }
}

// --- Projects API ---

export interface ProjectListItem {
  id: string;
  title: string;
  genre: string | null;
  distribution_format: string | null;
  voice_profile_id: string | null;
  voice_profile_name: string | null;
  scene_count: number;
  total_words: number;
  last_generated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectDetail {
  id: string;
  title: string;
  genre: string | null;
  distribution_format: string | null;
  voice_profile_id: string | null;
  voice_profile_name: string | null;
  story_bible: Record<string, unknown>;
  scene_count: number;
  total_words: number;
  created_at: string;
  updated_at: string;
}

export interface SceneListItem {
  id: string;
  user_prompt: string;
  scene_label: string | null;
  word_count: number | null;
  is_pinned: boolean;
  scene_order: number | null;
  has_polish: boolean;
  created_at: string;
}

export interface SceneDetail {
  id: string;
  user_prompt: string;
  scene_label: string | null;
  voice_output: string;
  polish_output: string | null;
  brain_output: string | null;
  word_count: number | null;
  is_pinned: boolean;
  scene_order: number | null;
  created_at: string;
}

export async function fetchProjects(): Promise<ProjectListItem[]> {
  const data = await apiFetch<{ projects: ProjectListItem[] }>("/api/projects");
  return data.projects;
}

export async function createProject(body: {
  title: string;
  genre?: string;
  voice_profile_id?: string;
}): Promise<ProjectDetail> {
  return apiFetch<ProjectDetail>("/api/projects", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchProject(projectId: string): Promise<ProjectDetail> {
  return apiFetch<ProjectDetail>(`/api/projects/${projectId}`);
}

export async function updateProject(
  projectId: string,
  body: {
    title?: string;
    genre?: string;
    voice_profile_id?: string;
    story_bible?: Record<string, unknown>;
  }
): Promise<ProjectDetail> {
  return apiFetch<ProjectDetail>(`/api/projects/${projectId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteProject(projectId: string): Promise<void> {
  await apiFetch<{ deleted: boolean }>(`/api/projects/${projectId}`, {
    method: "DELETE",
  });
}

export async function fetchScenes(
  projectId: string
): Promise<SceneListItem[]> {
  const data = await apiFetch<{ scenes: SceneListItem[] }>(
    `/api/projects/${projectId}/scenes`
  );
  return data.scenes;
}

export async function fetchScene(
  projectId: string,
  sceneId: string
): Promise<SceneDetail> {
  return apiFetch<SceneDetail>(
    `/api/projects/${projectId}/scenes/${sceneId}`
  );
}

export async function updateScene(
  projectId: string,
  sceneId: string,
  body: {
    scene_label?: string;
    scene_order?: number;
    is_pinned?: boolean;
    voice_output?: string;
  }
): Promise<SceneDetail> {
  return apiFetch<SceneDetail>(
    `/api/projects/${projectId}/scenes/${sceneId}`,
    { method: "PATCH", body: JSON.stringify(body) }
  );
}

export async function deleteScene(
  projectId: string,
  sceneId: string
): Promise<void> {
  await apiFetch<{ deleted: boolean }>(
    `/api/projects/${projectId}/scenes/${sceneId}`,
    { method: "DELETE" }
  );
}

export async function reorderScenes(
  projectId: string,
  sceneIds: string[]
): Promise<void> {
  await apiFetch<{ reordered: boolean }>(
    `/api/projects/${projectId}/scenes/reorder`,
    { method: "POST", body: JSON.stringify({ scene_ids: sceneIds }) }
  );
}

// --- Story Bible Entry ---

export async function addBibleEntry(
  projectId: string,
  section: string,
  entry: Record<string, unknown>
): Promise<void> {
  await apiFetch<{ added: boolean }>(
    `/api/projects/${projectId}/bible/entry`,
    {
      method: "POST",
      body: JSON.stringify({ section, entry }),
    }
  );
}

// --- Brainstorm API ---

export interface BrainstormDoneData {
  session_id?: string;
  questions_asked: number;
}

export interface IdeaEvaluation {
  premise_clarity: number;
  stakes_strength: number;
  conflict_depth: number;
  genre_fit: string;
  series_potential: string;
  target_audience: string;
  unresolved_questions: string[];
  extracted_bible_entries: Record<string, unknown[]>;
}

export async function apiBrainstormStream(
  path: string,
  body: Record<string, unknown>,
  onToken: (content: string) => void,
  onDone: (data: BrainstormDoneData) => void
): Promise<void> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const error: ApiError = await response.json().catch(() => ({
      detail: `Request failed with status ${response.status}`,
    }));
    throw new Error(error.detail);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        const data = JSON.parse(line.slice(6));
        if (data.type === "token" && data.content) {
          onToken(data.content);
        } else if (data.type === "done") {
          onDone({
            session_id: data.session_id,
            questions_asked: data.questions_asked ?? 0,
          });
          return;
        } else if (data.type === "error") {
          throw new Error(data.content ?? "Brainstorm error");
        }
      } catch (e) {
        if (e instanceof SyntaxError) continue;
        throw e;
      }
    }
  }
}

export async function evaluateBrainstorm(
  sessionId: string
): Promise<{ evaluation: IdeaEvaluation; questions_asked: number }> {
  return apiFetch<{ evaluation: IdeaEvaluation; questions_asked: number }>(
    "/api/brainstorm/evaluate",
    {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId }),
    }
  );
}

// --- Outline API ---

export interface OutlineBeat {
  beat_id: string;
  template_beat: string;
  description: string;
  pov_character: string | null;
  estimated_words: number;
  status: "pending" | "generating" | "generated" | "revised";
  generation_id: string | null;
}

export interface OutlineChapter {
  chapter_number: number;
  title: string;
  beats: OutlineBeat[];
}

export interface OutlinePart {
  part_number: number;
  title: string;
  chapters: OutlineChapter[];
}

export interface Outline {
  structure_template: string;
  structure_name: string;
  total_chapters: number;
  parts: OutlinePart[];
  locked: boolean;
  locked_at: string | null;
  genre_recommendation?: string;
}

export interface StructureTemplate {
  name: string;
  description: string;
  beat_count: number;
}

// --- Story DNA Analyzer (Phase 2-4) ---

export interface StoryDnaConcept {
  concept_id: string;
  working_title: string;
  hook: string;
  premise: string;
  genre: string;
  distribution_format: string;
  why_this_fits_your_dna: string;
  generated_at?: string;
}

export interface StoryDnaProfile {
  genre_sweet_spot?: string;
  thematic_obsessions?: string[];
  character_instincts?: string;
  world_building_style?: string;
  anti_preferences?: string[];
  influences_decoded?: string;
  voice_signal?: Record<string, string>;
}

export interface StoryDnaStartResponse {
  session_id: string;
  first_question: string;
  question_count: number;
}

export interface StoryDnaFinalizeResponse {
  session_id: string;
  story_dna_profile: StoryDnaProfile;
  concepts: StoryDnaConcept[];
  cta_paywall: string;
}

export interface StoryDnaRespondDoneData {
  ready_for_finalize: boolean;
  question_count: number;
}

async function anonFetch<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  if (!response.ok) {
    const error: ApiError = await response.json().catch(() => ({
      detail: `Request failed with status ${response.status}`,
    }));
    throw new Error(error.detail);
  }
  return response.json() as Promise<T>;
}

export async function startStoryDna(): Promise<StoryDnaStartResponse> {
  return anonFetch<StoryDnaStartResponse>("/api/story-dna/start", {});
}

export async function finalizeStoryDna(
  sessionId: string
): Promise<StoryDnaFinalizeResponse> {
  return anonFetch<StoryDnaFinalizeResponse>("/api/story-dna/finalize", {
    session_id: sessionId,
  });
}

/** Anonymous SSE stream for /api/story-dna/respond. */
export async function streamStoryDnaRespond(
  sessionId: string,
  answer: string,
  onToken: (content: string) => void,
  onDone: (data: StoryDnaRespondDoneData) => void
): Promise<void> {
  const response = await fetch(`${API_URL}/api/story-dna/respond`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, answer }),
  });
  if (!response.ok) {
    const error: ApiError = await response.json().catch(() => ({
      detail: `Request failed with status ${response.status}`,
    }));
    throw new Error(error.detail);
  }
  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response body");
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        const data = JSON.parse(line.slice(6));
        if (data.type === "token" && data.content) {
          onToken(data.content);
        } else if (data.type === "done") {
          onDone({
            ready_for_finalize: data.ready_for_finalize ?? false,
            question_count: data.question_count ?? 0,
          });
          return;
        } else if (data.type === "error") {
          throw new Error(data.content ?? "Story DNA error");
        }
      } catch (e) {
        if (e instanceof SyntaxError) continue;
        throw e;
      }
    }
  }
}

export async function migrateStoryDnaSession(
  sessionId: string,
  profileName?: string
): Promise<{ dna_profile_id: string; status: string }> {
  return apiFetch<{ dna_profile_id: string; status: string }>(
    "/api/story-dna/migrate-session",
    {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, profile_name: profileName }),
    }
  );
}

export async function createProjectFromDna(body: {
  dna_profile_id: string;
  concept_id: string;
  project_title?: string;
}): Promise<{ project_id: string; voice_profile_id: string }> {
  return apiFetch<{ project_id: string; voice_profile_id: string }>(
    "/api/story-dna/create-project",
    { method: "POST", body: JSON.stringify(body) }
  );
}

// --- Outline (existing) ---

export async function fetchOutlineTemplates(): Promise<
  Record<string, StructureTemplate>
> {
  const data = await apiFetch<{ templates: Record<string, StructureTemplate> }>(
    "/api/outline/templates"
  );
  return data.templates;
}

export async function compileOutline(
  projectId: string,
  body: {
    brainstorm_decisions?: string[];
    structure_override?: string;
  }
): Promise<Outline> {
  const data = await apiFetch<{ outline: Outline }>(
    `/api/projects/${projectId}/outline/compile`,
    {
      method: "POST",
      body: JSON.stringify(body),
    }
  );
  return data.outline;
}

export async function fetchOutline(projectId: string): Promise<Outline> {
  const data = await apiFetch<{ outline: Outline }>(
    `/api/projects/${projectId}/outline`
  );
  return data.outline;
}

export async function updateOutline(
  projectId: string,
  outline: Outline
): Promise<Outline> {
  const data = await apiFetch<{ outline: Outline }>(
    `/api/projects/${projectId}/outline`,
    {
      method: "PATCH",
      body: JSON.stringify({ outline }),
    }
  );
  return data.outline;
}

export async function lockOutline(projectId: string): Promise<Outline> {
  const data = await apiFetch<{ outline: Outline }>(
    `/api/projects/${projectId}/outline/lock`,
    { method: "POST" }
  );
  return data.outline;
}
