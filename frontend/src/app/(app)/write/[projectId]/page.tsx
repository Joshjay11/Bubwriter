"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import {
  apiFetch,
  fetchProject,
  fetchScene,
  updateScene,
  apiGenerationStream,
  addBibleEntry,
  type ProjectDetail,
  type GenerationEvent,
  type ExtractionSuggestions,
  type OutlineBeat,
  type OutlineChapter,
  type OutlinePart,
} from "@/lib/api";
import { SuggestionPanel } from "../../project/[id]/components/SuggestionPanel";

// --- Types ---

interface VoiceProfile {
  id: string;
  profile_name: string;
  voice_summary: string | null;
  created_at: string;
  updated_at: string;
}

type WriteStage = "idle" | "brain" | "voice" | "polish" | "complete" | "error";

const BRAIN_MESSAGES = [
  "Analyzing your story context...",
  "Designing scene structure...",
  "Building tension arc...",
  "Mapping character dynamics...",
  "Plotting emotional beats...",
];

// --- Main Page ---

export default function WritePage() {
  const params = useParams<{ projectId: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();

  const projectId = params.projectId;
  const beatId = searchParams.get("beat");

  // --- Data state ---
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [voiceProfile, setVoiceProfile] = useState<VoiceProfile | null>(null);
  const [beat, setBeat] = useState<OutlineBeat | null>(null);
  const [chapter, setChapter] = useState<OutlineChapter | null>(null);
  const [part, setPart] = useState<OutlinePart | null>(null);
  const [outlineLocked, setOutlineLocked] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  // --- Generation state ---
  const [stage, setStage] = useState<WriteStage>("idle");
  const [stageMessage, setStageMessage] = useState("");
  const [brainMessageIdx, setBrainMessageIdx] = useState(0);
  const [prose, setProse] = useState("");
  const [generationId, setGenerationId] = useState<string | null>(null);
  const [generationError, setGenerationError] = useState("");
  const [suggestions, setSuggestions] = useState<ExtractionSuggestions | null>(
    null,
  );
  const proseRef = useRef("");
  const brainTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // --- Save state ---
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved">(
    "idle",
  );
  const lastSavedRef = useRef("");

  // --- Load project, profile, and beat on mount ---
  useEffect(() => {
    if (!projectId) return;

    (async () => {
      try {
        const [proj, profilesData] = await Promise.all([
          fetchProject(projectId),
          apiFetch<{ profiles: VoiceProfile[] }>("/api/voice-profiles"),
        ]);
        setProject(proj);

        // Find the voice profile linked to this project
        if (proj.voice_profile_id) {
          const found = profilesData.profiles.find(
            (p) => p.id === proj.voice_profile_id,
          );
          if (found) setVoiceProfile(found);
        }

        // Find the beat in the outline
        if (beatId) {
          const outline = (proj.story_bible as Record<string, unknown>)
            ?.outline as {
            parts: OutlinePart[];
            locked?: boolean;
          } | null;
          setOutlineLocked(!!outline?.locked);
          if (outline?.parts) {
            for (const p of outline.parts) {
              for (const ch of p.chapters) {
                const found = ch.beats.find((b) => b.beat_id === beatId);
                if (found) {
                  setBeat(found);
                  setChapter(ch);
                  setPart(p);

                  // If already generated, load existing prose
                  if (
                    found.status === "generated" &&
                    found.generation_id
                  ) {
                    try {
                      const scene = await fetchScene(
                        projectId,
                        found.generation_id,
                      );
                      const content =
                        scene.polish_output ?? scene.voice_output ?? "";
                      setProse(content);
                      proseRef.current = content;
                      lastSavedRef.current = content;
                      setGenerationId(found.generation_id);
                      setStage("complete");
                    } catch {
                      // Scene might not exist yet — that's OK
                    }
                  }
                  break;
                }
              }
            }
          }
        }
      } catch (e) {
        setLoadError(
          e instanceof Error ? e.message : "Failed to load project.",
        );
      } finally {
        setLoading(false);
      }
    })();
  }, [projectId, beatId]);

  // --- Brain message rotation ---
  useEffect(() => {
    if (stage === "brain") {
      brainTimerRef.current = setInterval(() => {
        setBrainMessageIdx((i) => (i + 1) % BRAIN_MESSAGES.length);
      }, 3000);
    } else {
      if (brainTimerRef.current) {
        clearInterval(brainTimerRef.current);
        brainTimerRef.current = null;
      }
      setBrainMessageIdx(0);
    }
    return () => {
      if (brainTimerRef.current) clearInterval(brainTimerRef.current);
    };
  }, [stage]);

  // --- Generate from beat ---
  const handleGenerate = useCallback(async () => {
    if (!project || !voiceProfile || !beat) return;

    setGenerationError("");
    setStage("brain");
    setProse("");
    proseRef.current = "";
    setSuggestions(null);
    setGenerationId(null);

    try {
      await apiGenerationStream(
        "/api/generate/from-beat",
        {
          project_id: projectId,
          voice_profile_id: voiceProfile.id,
          beat_id: beat.beat_id,
          include_polish: false,
        },
        (event: GenerationEvent) => {
          switch (event.type) {
            case "stage":
              if (event.stage === "voice") {
                setStage("voice");
                setStageMessage("Writing your scene...");
              } else if (event.stage === "polish") {
                setStage("polish");
                setStageMessage("Polishing...");
              } else if (event.stage === "brain") {
                setStage("brain");
                setStageMessage(event.message ?? "");
              } else if (event.stage === "extraction") {
                setStageMessage("Analyzing your scene...");
              }
              break;
            case "token":
              proseRef.current += event.content ?? "";
              setProse(proseRef.current);
              break;
            case "polish_complete":
              if (event.content) {
                proseRef.current = event.content;
                setProse(event.content);
              }
              break;
            case "bible_suggestions":
              if (event.suggestions) {
                setSuggestions(event.suggestions);
              }
              break;
            case "done":
              setStage("complete");
              setStageMessage("");
              if (event.metadata?.generation_id) {
                setGenerationId(event.metadata.generation_id);
              }
              // Update the local beat status
              setBeat((prev) =>
                prev
                  ? {
                      ...prev,
                      status: "generated" as const,
                      generation_id:
                        event.metadata?.generation_id ?? prev.generation_id,
                    }
                  : prev,
              );
              lastSavedRef.current = proseRef.current;
              break;
            case "error":
              setStage("error");
              setGenerationError(
                event.content ?? event.message ?? "Generation failed.",
              );
              // Beat status rolled back to "pending" by backend
              setBeat((prev) =>
                prev ? { ...prev, status: "pending" as const } : prev,
              );
              break;
          }
        },
      );
    } catch (e) {
      setStage("error");
      setGenerationError(
        e instanceof Error ? e.message : "Generation failed.",
      );
    }
  }, [project, voiceProfile, beat, projectId]);

  // --- Save edits ---
  const handleSave = useCallback(async () => {
    if (!generationId || prose === lastSavedRef.current) return;
    setSaveStatus("saving");
    try {
      await updateScene(projectId, generationId, { voice_output: prose });
      lastSavedRef.current = prose;
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 2000);
    } catch {
      setSaveStatus("idle");
    }
  }, [generationId, prose, projectId]);

  // --- Derived ---
  const isGenerating = stage === "brain" || stage === "voice" || stage === "polish";
  const isEditable = stage === "idle" || stage === "complete";
  const hasProse = prose.length > 0;
  const wordCount = prose ? prose.split(/\s+/).filter(Boolean).length : 0;
  const canGenerate = !!voiceProfile && outlineLocked && !!beat;

  // --- Loading / Error states ---
  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-zinc-950">
        <div className="inline-block w-6 h-6 border-2 border-zinc-600 border-t-zinc-300 rounded-full animate-spin" />
      </div>
    );
  }

  if (loadError || !project) {
    return (
      <div className="flex items-center justify-center h-screen bg-zinc-950">
        <p className="text-red-400">{loadError || "Project not found."}</p>
      </div>
    );
  }

  if (!beat || !chapter) {
    return (
      <div className="flex items-center justify-center h-screen bg-zinc-950">
        <div className="text-center">
          <p className="text-zinc-400 mb-4">
            Beat not found in the project outline.
          </p>
          <button
            className="text-purple-400 hover:text-purple-300 text-sm"
            onClick={() => router.push(`/outline/${projectId}`)}
          >
            Back to outline
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-zinc-950 text-zinc-100">
      {/* --- Left sidebar: Beat context & actions --- */}
      <aside className="w-80 shrink-0 border-r border-zinc-800 flex flex-col">
        <div className="p-5 border-b border-zinc-800">
          <button
            className="text-sm text-zinc-500 hover:text-zinc-300 mb-4 flex items-center gap-1"
            onClick={() => router.push(`/outline/${projectId}`)}
          >
            <span>&larr;</span> Back to outline
          </button>

          <h1 className="text-lg font-semibold text-zinc-200 mb-1">
            {project.title}
          </h1>
          {voiceProfile && (
            <p className="text-xs text-purple-400">
              Voice: {voiceProfile.profile_name}
            </p>
          )}
        </div>

        <div className="p-5 flex-1 overflow-y-auto space-y-4">
          {/* Chapter context */}
          <div>
            <p className="text-xs text-zinc-500 uppercase tracking-wide mb-1">
              {part ? `Part ${part.part_number}` : ""} &middot; Chapter{" "}
              {chapter.chapter_number}
            </p>
            <h2 className="text-sm font-medium text-zinc-300">
              {chapter.title}
            </h2>
          </div>

          {/* Beat info */}
          <div className="bg-zinc-800/50 rounded-lg p-4 border border-zinc-700/50">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-zinc-400">
                {beat.template_beat}
              </span>
              <BeatStatus status={beat.status} />
            </div>
            <p className="text-sm text-zinc-300 leading-relaxed">
              {beat.description}
            </p>
            {beat.pov_character && (
              <p className="text-xs text-purple-400 mt-2">
                POV: {beat.pov_character}
              </p>
            )}
            {beat.estimated_words && (
              <p className="text-xs text-zinc-500 mt-1">
                Target: ~{beat.estimated_words.toLocaleString()} words
              </p>
            )}
          </div>

          {/* Word count */}
          {hasProse && (
            <div className="text-xs text-zinc-500">
              {wordCount.toLocaleString()} words
              {beat.estimated_words
                ? ` / ~${beat.estimated_words.toLocaleString()} target`
                : ""}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="p-5 border-t border-zinc-800 space-y-2">
          {!outlineLocked && (
            <p className="text-xs text-amber-400 mb-2">
              Outline is not locked. Lock it from the outline page before
              generating.
            </p>
          )}

          {outlineLocked && !voiceProfile && (
            <p className="text-xs text-amber-400 mb-2">
              No voice profile linked to this project. Complete Voice Discovery
              first.
            </p>
          )}

          {!isGenerating && beat.status === "pending" && canGenerate && (
            <button
              className="w-full px-4 py-2.5 bg-purple-600 text-white text-sm rounded-lg hover:bg-purple-700 font-medium"
              onClick={handleGenerate}
            >
              Generate Scene
            </button>
          )}

          {!isGenerating && beat.status === "generated" && canGenerate && (
            <>
              <button
                className="w-full px-4 py-2 bg-zinc-700 text-zinc-200 text-sm rounded-lg hover:bg-zinc-600"
                onClick={handleGenerate}
              >
                Regenerate
              </button>
              {prose !== lastSavedRef.current && (
                <button
                  className="w-full px-4 py-2 bg-emerald-600 text-white text-sm rounded-lg hover:bg-emerald-700"
                  onClick={handleSave}
                >
                  {saveStatus === "saving" ? "Saving..." : "Save edits"}
                </button>
              )}
            </>
          )}

          {isGenerating && (
            <div className="flex items-center gap-2 py-2">
              <div className="w-3 h-3 border-2 border-zinc-600 border-t-purple-400 rounded-full animate-spin" />
              <span className="text-sm text-zinc-400">
                {stage === "brain"
                  ? BRAIN_MESSAGES[brainMessageIdx]
                  : stageMessage}
              </span>
            </div>
          )}

          {saveStatus === "saved" && (
            <p className="text-xs text-emerald-400 text-center">Saved</p>
          )}
        </div>
      </aside>

      {/* --- Center: Prose editor --- */}
      <main className="flex-1 flex flex-col min-w-0">
        <div className="flex-1 overflow-y-auto">
          {/* Brain loading state */}
          {stage === "brain" && !hasProse && (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <div className="inline-block w-6 h-6 border-2 border-zinc-600 border-t-zinc-300 rounded-full animate-spin mb-3" />
                <p className="text-zinc-400 text-sm animate-pulse">
                  {BRAIN_MESSAGES[brainMessageIdx]}
                </p>
              </div>
            </div>
          )}

          {/* Polish overlay */}
          {stage === "polish" && hasProse && (
            <div className="absolute inset-0 bg-zinc-950/60 flex items-center justify-center z-10">
              <div className="text-center">
                <div className="inline-block w-6 h-6 border-2 border-zinc-600 border-t-zinc-300 rounded-full animate-spin mb-3" />
                <p className="text-zinc-400 text-sm">
                  Polishing your prose...
                </p>
              </div>
            </div>
          )}

          {/* Streaming display (read-only) */}
          {hasProse && !isEditable && (
            <div className="max-w-[680px] mx-auto px-8 py-6">
              <div className="text-zinc-200 leading-relaxed whitespace-pre-wrap font-serif text-[1.05rem]">
                {prose}
                {stage === "voice" && (
                  <span className="inline-block w-0.5 h-5 bg-zinc-400 animate-pulse ml-0.5 align-text-bottom" />
                )}
              </div>
            </div>
          )}

          {/* Editable prose */}
          {hasProse && isEditable && (
            <div className="max-w-[680px] mx-auto px-8 py-6">
              <textarea
                value={prose}
                onChange={(e) => setProse(e.target.value)}
                className="w-full bg-transparent text-zinc-200 leading-relaxed whitespace-pre-wrap font-serif text-[1.05rem] resize-none focus:outline-none min-h-[calc(100vh-8rem)]"
                spellCheck
              />
            </div>
          )}

          {/* Empty state */}
          {!hasProse && stage === "idle" && (
            <div className="flex items-center justify-center h-full">
              <div className="text-center max-w-md">
                <p className="text-zinc-400 text-lg mb-2">
                  Ready to write this beat.
                </p>
                <p className="text-zinc-600 text-sm">
                  Click <strong>Generate Scene</strong> to create prose from the
                  beat description.
                </p>
              </div>
            </div>
          )}

          {/* Error display */}
          {generationError && (
            <div className="max-w-[680px] mx-auto px-8 pb-6">
              <div className="p-4 bg-red-950/50 border border-red-900 rounded-lg">
                <p className="text-red-400 text-sm">{generationError}</p>
                {beat.status === "pending" && voiceProfile && (
                  <button
                    className="mt-2 text-xs text-red-300 hover:text-red-200 underline"
                    onClick={handleGenerate}
                  >
                    Try again
                  </button>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Bible suggestions */}
        {suggestions && (
          <SuggestionPanel
            projectId={projectId}
            suggestions={suggestions}
            onClose={() => setSuggestions(null)}
          />
        )}
      </main>
    </div>
  );
}

// --- Beat Status Badge ---

function BeatStatus({ status }: { status: OutlineBeat["status"] }) {
  const styles: Record<string, string> = {
    pending: "bg-zinc-700 text-zinc-400",
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
