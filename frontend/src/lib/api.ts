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

export interface GenerationEvent {
  type: "stage" | "skeleton" | "token" | "polish_complete" | "done" | "error";
  stage?: string;
  message?: string;
  content?: string;
  data?: string;
  metadata?: {
    word_count: number;
    generation_id: string;
  };
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
