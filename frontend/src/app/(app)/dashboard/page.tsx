"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  apiFetch,
  fetchProjects,
  createProject,
  deleteProject,
  type ProjectListItem,
} from "@/lib/api";

// --- Types ---

interface VoiceProfile {
  id: string;
  profile_name: string;
  voice_summary: string | null;
  created_at: string;
  updated_at: string;
}

const GENRE_OPTIONS = [
  "Fantasy",
  "Romance",
  "Thriller",
  "Science Fiction",
  "LitRPG",
  "Literary Fiction",
  "Horror",
  "Mystery",
  "Historical",
  "Political Thriller",
  "Other",
];

// --- Helpers ---

function timeAgo(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  return `${months}mo ago`;
}

// --- Main Component ---

export default function DashboardPage() {
  const router = useRouter();

  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [profiles, setProfiles] = useState<VoiceProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Create modal state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newGenre, setNewGenre] = useState("");
  const [newVoiceProfileId, setNewVoiceProfileId] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");

  // Delete confirmation
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  // Load data on mount
  useEffect(() => {
    async function load() {
      try {
        const [projectsData, profilesData] = await Promise.all([
          fetchProjects(),
          apiFetch<{ profiles: VoiceProfile[] }>("/api/voice-profiles"),
        ]);
        setProjects(projectsData);
        setProfiles(profilesData.profiles);
      } catch (e) {
        setError(
          e instanceof Error ? e.message : "Failed to load projects."
        );
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  // Create project
  const handleCreate = useCallback(async () => {
    if (!newTitle.trim()) return;
    setCreating(true);
    setCreateError("");

    try {
      const project = await createProject({
        title: newTitle.trim(),
        genre: newGenre || undefined,
        voice_profile_id: newVoiceProfileId || undefined,
      });
      setShowCreateModal(false);
      setNewTitle("");
      setNewGenre("");
      setNewVoiceProfileId("");
      router.push(`/project/${project.id}`);
    } catch (e) {
      setCreateError(
        e instanceof Error ? e.message : "Failed to create project."
      );
    } finally {
      setCreating(false);
    }
  }, [newTitle, newGenre, newVoiceProfileId, router]);

  // Delete project
  const handleDelete = useCallback(
    async (projectId: string) => {
      setDeleting(true);
      try {
        await deleteProject(projectId);
        setProjects((prev) => prev.filter((p) => p.id !== projectId));
        setDeleteConfirmId(null);
      } catch (e) {
        setError(
          e instanceof Error ? e.message : "Failed to delete project."
        );
      } finally {
        setDeleting(false);
      }
    },
    []
  );

  // --- Loading state ---

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-3xl font-bold">Projects</h1>
        </div>
        <div className="flex items-center justify-center py-20">
          <div className="inline-block w-6 h-6 border-2 border-zinc-600 border-t-zinc-300 rounded-full animate-spin" />
        </div>
      </div>
    );
  }

  // --- Empty state (no projects) ---

  if (projects.length === 0) {
    return (
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-3xl font-bold">Projects</h1>
        </div>

        <div className="flex flex-col items-center justify-center py-20 text-center">
          <h2 className="text-xl font-semibold mb-2">
            Welcome to BUB Writer
          </h2>
          <p className="text-zinc-400 mb-6 max-w-md">
            Start by creating your first project. Each project holds your
            scenes and connects to a voice profile.
          </p>
          <button
            onClick={() => setShowCreateModal(true)}
            className="rounded-lg bg-zinc-100 px-6 py-3 text-zinc-900 font-medium hover:bg-zinc-200 transition-colors"
          >
            + Create Project
          </button>

          {profiles.length === 0 && (
            <p className="text-zinc-500 text-sm mt-6">
              Don&apos;t have a voice profile yet?{" "}
              <Link href="/voice" className="text-zinc-300 underline">
                Create one in Voice Discovery
              </Link>
            </p>
          )}
        </div>

        {showCreateModal && (
          <CreateProjectModal
            profiles={profiles}
            newTitle={newTitle}
            setNewTitle={setNewTitle}
            newGenre={newGenre}
            setNewGenre={setNewGenre}
            newVoiceProfileId={newVoiceProfileId}
            setNewVoiceProfileId={setNewVoiceProfileId}
            creating={creating}
            createError={createError}
            onClose={() => setShowCreateModal(false)}
            onCreate={handleCreate}
          />
        )}

        {error && (
          <div className="mt-4 p-4 bg-red-950/50 border border-red-900 rounded-lg">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}
      </div>
    );
  }

  // --- Projects list ---

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-bold">Projects</h1>
        <button
          onClick={() => setShowCreateModal(true)}
          className="rounded-lg bg-zinc-100 px-5 py-2.5 text-sm text-zinc-900 font-medium hover:bg-zinc-200 transition-colors"
        >
          + New Project
        </button>
      </div>

      {profiles.length === 0 && (
        <div className="mb-6 p-4 bg-zinc-900 border border-zinc-800 rounded-lg">
          <p className="text-zinc-400 text-sm">
            You don&apos;t have a voice profile yet. Your writing won&apos;t
            sound like you.{" "}
            <Link href="/voice" className="text-zinc-200 underline">
              Create your Voice Profile
            </Link>
          </p>
        </div>
      )}

      <div className="grid gap-4">
        {projects.map((project) => (
          <div
            key={project.id}
            onClick={() => router.push(`/project/${project.id}`)}
            className="bg-zinc-900 rounded-lg border border-zinc-800 p-6 hover:border-zinc-700 transition-colors cursor-pointer group"
          >
            <div className="flex items-start justify-between">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-3 mb-1">
                  <h3 className="text-lg font-semibold truncate">
                    {project.title}
                  </h3>
                  {project.genre && (
                    <span className="inline-block text-xs px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-400 flex-shrink-0">
                      {project.genre}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-4 text-sm text-zinc-500">
                  <span>
                    Voice:{" "}
                    {project.voice_profile_name || (
                      <span className="text-zinc-600">Not assigned</span>
                    )}
                  </span>
                  <span>
                    {project.scene_count}{" "}
                    {project.scene_count === 1 ? "scene" : "scenes"}
                  </span>
                  <span>
                    {project.total_words.toLocaleString()} words
                  </span>
                  {project.last_generated_at && (
                    <span>Last: {timeAgo(project.last_generated_at)}</span>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-2 ml-4">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    router.push(`/project/${project.id}`);
                  }}
                  className="rounded-md bg-zinc-800 px-4 py-1.5 text-sm text-zinc-300 hover:bg-zinc-700 transition-colors opacity-0 group-hover:opacity-100"
                >
                  Open
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setDeleteConfirmId(project.id);
                  }}
                  className="rounded-md px-2 py-1.5 text-sm text-zinc-500 hover:text-red-400 hover:bg-zinc-800 transition-colors opacity-0 group-hover:opacity-100"
                  title="Delete project"
                >
                  &times;
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Delete confirmation dialog */}
      {deleteConfirmId && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-8 w-full max-w-sm">
            <h3 className="text-lg font-semibold mb-2">Delete Project?</h3>
            <p className="text-zinc-400 text-sm mb-6">
              This will permanently delete the project and all its scenes.
              This cannot be undone.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setDeleteConfirmId(null)}
                disabled={deleting}
                className="rounded-lg px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDelete(deleteConfirmId)}
                disabled={deleting}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm text-white font-medium hover:bg-red-500 transition-colors disabled:opacity-40"
              >
                {deleting ? "Deleting..." : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create modal */}
      {showCreateModal && (
        <CreateProjectModal
          profiles={profiles}
          newTitle={newTitle}
          setNewTitle={setNewTitle}
          newGenre={newGenre}
          setNewGenre={setNewGenre}
          newVoiceProfileId={newVoiceProfileId}
          setNewVoiceProfileId={setNewVoiceProfileId}
          creating={creating}
          createError={createError}
          onClose={() => setShowCreateModal(false)}
          onCreate={handleCreate}
        />
      )}

      {error && (
        <div className="mt-4 p-4 bg-red-950/50 border border-red-900 rounded-lg">
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}
    </div>
  );
}

// --- Create Project Modal ---

function CreateProjectModal({
  profiles,
  newTitle,
  setNewTitle,
  newGenre,
  setNewGenre,
  newVoiceProfileId,
  setNewVoiceProfileId,
  creating,
  createError,
  onClose,
  onCreate,
}: {
  profiles: VoiceProfile[];
  newTitle: string;
  setNewTitle: (v: string) => void;
  newGenre: string;
  setNewGenre: (v: string) => void;
  newVoiceProfileId: string;
  setNewVoiceProfileId: (v: string) => void;
  creating: boolean;
  createError: string;
  onClose: () => void;
  onCreate: () => void;
}) {
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-8 w-full max-w-md">
        <h3 className="text-xl font-semibold mb-6">Create New Project</h3>

        <div className="space-y-4">
          <div>
            <label className="block text-sm text-zinc-400 mb-1.5">Title</label>
            <input
              type="text"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && newTitle.trim()) onCreate();
              }}
              placeholder="My Novel"
              autoFocus
              className="w-full bg-zinc-800 rounded-lg px-4 py-3 text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-zinc-700"
            />
          </div>

          <div>
            <label className="block text-sm text-zinc-400 mb-1.5">
              Genre (optional)
            </label>
            <select
              value={newGenre}
              onChange={(e) => setNewGenre(e.target.value)}
              className="w-full bg-zinc-800 text-zinc-300 rounded-lg px-4 py-3 border border-zinc-700 focus:outline-none focus:ring-1 focus:ring-zinc-700"
            >
              <option value="">Select a genre...</option>
              {GENRE_OPTIONS.map((g) => (
                <option key={g} value={g}>
                  {g}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm text-zinc-400 mb-1.5">
              Voice Profile (optional)
            </label>
            {profiles.length > 0 ? (
              <select
                value={newVoiceProfileId}
                onChange={(e) => setNewVoiceProfileId(e.target.value)}
                className="w-full bg-zinc-800 text-zinc-300 rounded-lg px-4 py-3 border border-zinc-700 focus:outline-none focus:ring-1 focus:ring-zinc-700"
              >
                <option value="">No profile selected</option>
                {profiles.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.profile_name}
                  </option>
                ))}
              </select>
            ) : (
              <p className="text-zinc-500 text-sm">
                No profiles yet.{" "}
                <Link href="/voice" className="text-zinc-300 underline">
                  Create one
                </Link>
              </p>
            )}
          </div>
        </div>

        {createError && (
          <p className="text-red-400 text-sm mt-4">{createError}</p>
        )}

        <div className="flex justify-end gap-3 mt-6">
          <button
            onClick={onClose}
            disabled={creating}
            className="rounded-lg px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onCreate}
            disabled={!newTitle.trim() || creating}
            className="rounded-lg bg-zinc-100 px-5 py-2 text-sm text-zinc-900 font-medium hover:bg-zinc-200 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {creating ? "Creating..." : "Create Project"}
          </button>
        </div>
      </div>
    </div>
  );
}
