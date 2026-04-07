"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  fetchProject,
  fetchOutline,
  compileOutline,
  updateOutline,
  lockOutline,
  fetchOutlineTemplates,
  type ProjectDetail,
  type Outline,
  type OutlineBeat,
  type StructureTemplate,
} from "@/lib/api";

// --- Beat Status Badge ---

function StatusBadge({ status }: { status: OutlineBeat["status"] }) {
  const styles: Record<string, string> = {
    pending: "bg-gray-700 text-gray-300",
    generating: "bg-amber-900 text-amber-300 animate-pulse",
    generated: "bg-green-900 text-green-300",
    revised: "bg-blue-900 text-blue-300",
  };

  return (
    <span
      className={`text-xs px-2 py-0.5 rounded-full ${styles[status] || styles.pending}`}
    >
      {status}
    </span>
  );
}

// --- Beat Editor ---

function BeatCard({
  beat,
  chapterNumber,
  isLocked,
  onUpdate,
  onGenerate,
}: {
  beat: OutlineBeat;
  chapterNumber: number;
  isLocked: boolean;
  onUpdate: (beatId: string, description: string) => void;
  onGenerate: (beatId: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState(beat.description);

  const handleSave = () => {
    onUpdate(beat.beat_id, editText);
    setEditing(false);
  };

  return (
    <div className="border border-gray-700 rounded-lg p-4 bg-gray-800/50">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-400">
            {beat.template_beat}
          </span>
          <StatusBadge status={beat.status} />
        </div>
        <span className="text-xs text-gray-500">
          ~{beat.estimated_words.toLocaleString()} words
        </span>
      </div>

      {beat.pov_character && (
        <p className="text-xs text-purple-400 mb-2">
          POV: {beat.pov_character}
        </p>
      )}

      {editing ? (
        <div className="space-y-2">
          <textarea
            className="w-full bg-gray-900 border border-gray-600 rounded p-2 text-sm text-gray-200 min-h-[80px]"
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
          />
          <div className="flex gap-2">
            <button
              className="text-xs px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700"
              onClick={handleSave}
            >
              Save
            </button>
            <button
              className="text-xs px-3 py-1 bg-gray-600 text-gray-300 rounded hover:bg-gray-500"
              onClick={() => {
                setEditText(beat.description);
                setEditing(false);
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm text-gray-300 leading-relaxed">
            {beat.description}
          </p>
          <div className="flex gap-1 shrink-0">
            {!isLocked && (
              <button
                className="text-xs px-2 py-1 text-gray-400 hover:text-white hover:bg-gray-700 rounded"
                onClick={() => setEditing(true)}
              >
                Edit
              </button>
            )}
            {isLocked && beat.status === "pending" && (
              <button
                className="text-xs px-3 py-1 bg-purple-600 text-white rounded hover:bg-purple-700"
                onClick={() => onGenerate(beat.beat_id)}
              >
                Generate
              </button>
            )}
            {isLocked && beat.status === "generated" && (
              <button
                className="text-xs px-2 py-1 text-gray-400 hover:text-white hover:bg-gray-700 rounded"
                onClick={() => onGenerate(beat.beat_id)}
              >
                Regenerate
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// --- Main Outline Page ---

export default function OutlinePage() {
  const params = useParams<{ projectId: string }>();
  const router = useRouter();
  const projectId = params.projectId;

  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [outline, setOutline] = useState<Outline | null>(null);
  const [templates, setTemplates] = useState<Record<
    string,
    StructureTemplate
  > | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [compiling, setCompiling] = useState(false);
  const [locking, setLocking] = useState(false);
  const [error, setError] = useState("");

  // Load project + existing outline + templates on mount
  useEffect(() => {
    async function load() {
      try {
        const [proj, tmpl] = await Promise.all([
          fetchProject(projectId),
          fetchOutlineTemplates(),
        ]);
        setProject(proj);
        setTemplates(tmpl);

        try {
          const existing = await fetchOutline(projectId);
          setOutline(existing);
          setSelectedTemplate(existing.structure_template);
        } catch {
          // No outline yet — that's fine
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load project");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [projectId]);

  const [saving, setSaving] = useState(false);

  const handleCompile = useCallback(async () => {
    setCompiling(true);
    setError("");
    try {
      const result = await compileOutline(projectId, {
        structure_override: selectedTemplate || undefined,
      });
      setOutline(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Compilation failed");
    } finally {
      setCompiling(false);
    }
  }, [projectId, selectedTemplate]);

  const handleSaveDraft = useCallback(async () => {
    if (!outline) return;
    setSaving(true);
    setError("");
    try {
      await updateOutline(projectId, outline);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save outline");
    } finally {
      setSaving(false);
    }
  }, [outline, projectId]);

  const handleBeatUpdate = useCallback(
    async (beatId: string, description: string) => {
      if (!outline) return;

      const updated = structuredClone(outline);
      for (const part of updated.parts) {
        for (const chapter of part.chapters) {
          for (const beat of chapter.beats) {
            if (beat.beat_id === beatId) {
              beat.description = description;
            }
          }
        }
      }

      try {
        await updateOutline(projectId, updated);
        setOutline(updated);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to save changes");
      }
    },
    [outline, projectId]
  );

  const handleLock = useCallback(async () => {
    if (!outline) return;
    setLocking(true);
    setError("");
    try {
      // Save current state first so the backend has something to lock
      await updateOutline(projectId, outline);
      const locked = await lockOutline(projectId);
      setOutline(locked);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to lock outline");
    } finally {
      setLocking(false);
    }
  }, [outline, projectId]);

  const handleGenerate = useCallback(
    (beatId: string) => {
      // Navigate to the write page with beat context
      router.push(`/write/${projectId}?beat=${beatId}`);
    },
    [projectId, router]
  );

  // Stats
  const totalChapters = outline?.total_chapters ?? 0;
  const totalWords =
    outline?.parts.reduce(
      (sum, part) =>
        sum +
        part.chapters.reduce(
          (cSum, ch) =>
            cSum + ch.beats.reduce((bSum, b) => bSum + b.estimated_words, 0),
          0
        ),
      0
    ) ?? 0;
  const totalParts = outline?.parts.length ?? 0;

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-950 text-gray-100 flex items-center justify-center">
        <p className="text-gray-400">Loading...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <div className="max-w-4xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold mb-1">
            Story Outline: {project?.title ?? "Untitled"}
          </h1>

          {/* Template selector */}
          <div className="flex items-center gap-3 mt-4">
            <label className="text-sm text-gray-400">Structure:</label>
            <select
              className="bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-200"
              value={selectedTemplate}
              onChange={(e) => setSelectedTemplate(e.target.value)}
              disabled={outline?.locked || compiling}
            >
              <option value="">Auto-recommend</option>
              {templates &&
                Object.entries(templates).map(([key, tmpl]) => (
                  <option key={key} value={key}>
                    {tmpl.name} ({tmpl.beat_count} beats)
                  </option>
                ))}
            </select>

            {!outline?.locked && (
              <button
                className="px-4 py-1.5 bg-purple-600 text-white text-sm rounded hover:bg-purple-700 disabled:opacity-50"
                onClick={handleCompile}
                disabled={compiling}
              >
                {compiling
                  ? "Compiling..."
                  : outline
                    ? "Recompile"
                    : "Build Outline"}
              </button>
            )}
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-6 p-3 bg-red-900/50 border border-red-700 rounded text-red-200 text-sm">
            {error}
          </div>
        )}

        {/* Genre recommendation */}
        {outline?.genre_recommendation && (
          <div className="mb-6 p-3 bg-blue-900/30 border border-blue-700 rounded text-blue-200 text-sm">
            Recommended genre: {outline.genre_recommendation}
          </div>
        )}

        {/* Outline Content */}
        {outline ? (
          <div className="space-y-8">
            {outline.parts.map((part) => (
              <div key={part.part_number}>
                <h2 className="text-lg font-semibold text-gray-200 mb-4 uppercase tracking-wide">
                  Part {part.part_number}: {part.title}
                </h2>

                <div className="space-y-4 ml-2">
                  {part.chapters.map((chapter) => (
                    <div
                      key={chapter.chapter_number}
                      className="border border-gray-700/50 rounded-lg overflow-hidden"
                    >
                      <div className="flex items-center justify-between px-4 py-3 bg-gray-800/70">
                        <h3 className="font-medium text-gray-200">
                          Chapter {chapter.chapter_number}: {chapter.title}
                        </h3>
                        <span className="text-xs text-gray-500">
                          ~
                          {chapter.beats
                            .reduce((s, b) => s + b.estimated_words, 0)
                            .toLocaleString()}{" "}
                          words
                        </span>
                      </div>

                      <div className="p-3 space-y-3">
                        {chapter.beats.map((beat) => (
                          <BeatCard
                            key={beat.beat_id}
                            beat={beat}
                            chapterNumber={chapter.chapter_number}
                            isLocked={outline.locked}
                            onUpdate={handleBeatUpdate}
                            onGenerate={handleGenerate}
                          />
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}

            {/* Stats & Lock */}
            <div className="border-t border-gray-700 pt-6 mt-8">
              <div className="flex items-center justify-between">
                <p className="text-sm text-gray-400">
                  {totalParts} parts | {totalChapters} chapters |{" "}
                  ~{totalWords.toLocaleString()} words
                </p>

                {!outline.locked ? (
                  <div className="flex items-center gap-3">
                    <button
                      className="px-4 py-2 bg-zinc-700 text-zinc-200 rounded-lg hover:bg-zinc-600 disabled:opacity-50 text-sm"
                      onClick={handleSaveDraft}
                      disabled={saving || locking}
                    >
                      {saving ? "Saving..." : "Save draft"}
                    </button>
                    <button
                      className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 font-medium"
                      onClick={handleLock}
                      disabled={locking || saving}
                    >
                      {locking
                        ? "Locking..."
                        : "Lock Outline & Continue to Voice Discovery"}
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center gap-3">
                    <span className="text-sm text-green-400">
                      Locked{" "}
                      {outline.locked_at &&
                        new Date(outline.locked_at).toLocaleDateString()}
                    </span>
                    <button
                      className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 font-medium"
                      onClick={() => router.push("/voice")}
                    >
                      Continue to Voice Discovery
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="text-center py-16 text-gray-500">
            <p className="text-lg mb-2">No outline yet</p>
            <p className="text-sm">
              Select a structure template and click "Build Outline" to get
              started.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
