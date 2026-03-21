"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useParams } from "next/navigation";
import {
  apiFetch,
  fetchProject,
  fetchScenes,
  fetchScene,
  updateProject,
  updateScene,
  deleteScene,
  reorderScenes,
  apiGenerationStream,
  type ProjectDetail,
  type SceneListItem,
  type GenerationEvent,
  type ExtractionSuggestions,
} from "@/lib/api";
import type { PipelineStage } from "./components/StageIndicator";
import { ProjectHeader } from "./components/ProjectHeader";
import { SceneSidebar } from "./components/SceneSidebar";
import { Editor } from "./components/Editor";
import { PromptBar } from "./components/PromptBar";
import { SuggestionPanel } from "./components/SuggestionPanel";

interface VoiceProfile {
  id: string;
  profile_name: string;
}

export default function ProjectPage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id;

  // --- Data state ---
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [scenes, setScenes] = useState<SceneListItem[]>([]);
  const [profiles, setProfiles] = useState<VoiceProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  // --- Workspace state ---
  const [activeSceneId, setActiveSceneId] = useState<string | null>(null);
  const [editorContent, setEditorContent] = useState("");
  const [prompt, setPrompt] = useState("");
  const [selectedProfileId, setSelectedProfileId] = useState("");

  // --- Generation state machine ---
  const [stage, setStage] = useState<PipelineStage>("idle");
  const [stageMessage, setStageMessage] = useState("");
  const [brainMessageIdx, setBrainMessageIdx] = useState(0);
  const [generationError, setGenerationError] = useState("");
  const brainTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // --- Extraction suggestions state ---
  const [suggestions, setSuggestions] = useState<ExtractionSuggestions | null>(null);

  // --- Save state ---
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved">("idle");
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSavedContentRef = useRef("");

  // --- Load project, scenes, and profiles on mount ---
  useEffect(() => {
    async function load() {
      try {
        const [projectData, scenesData, profilesData] = await Promise.all([
          fetchProject(projectId),
          fetchScenes(projectId),
          apiFetch<{ profiles: VoiceProfile[] }>("/api/voice-profiles"),
        ]);
        setProject(projectData);
        setScenes(scenesData);
        setProfiles(profilesData.profiles);
        setSelectedProfileId(projectData.voice_profile_id ?? "");
      } catch (e) {
        setLoadError(e instanceof Error ? e.message : "Failed to load project.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [projectId]);

  // --- Auto-save editor content (debounced) ---
  useEffect(() => {
    if (!activeSceneId || stage !== "idle" && stage !== "complete") return;
    if (editorContent === lastSavedContentRef.current) return;

    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);

    saveTimerRef.current = setTimeout(async () => {
      setSaveStatus("saving");
      try {
        await updateScene(projectId, activeSceneId, {
          voice_output: editorContent,
        });
        lastSavedContentRef.current = editorContent;
        setSaveStatus("saved");
        // Update word count in sidebar
        setScenes((prev) =>
          prev.map((s) =>
            s.id === activeSceneId
              ? { ...s, word_count: editorContent.split(/\s+/).filter(Boolean).length }
              : s
          )
        );
        setTimeout(() => setSaveStatus("idle"), 2000);
      } catch {
        setSaveStatus("idle");
      }
    }, 1500);

    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, [editorContent, activeSceneId, stage, projectId]);

  // --- Brain message rotation ---
  useEffect(() => {
    if (stage === "brain") {
      brainTimerRef.current = setInterval(() => {
        setBrainMessageIdx((i) => (i + 1) % 5);
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

  // --- Scene selection: load full scene content ---
  const handleSceneSelect = useCallback(
    async (sceneId: string) => {
      if (sceneId === activeSceneId) return;
      setActiveSceneId(sceneId);
      setGenerationError("");
      setStage("idle");
      try {
        const detail = await fetchScene(projectId, sceneId);
        const content = detail.polish_output ?? detail.voice_output ?? "";
        setEditorContent(content);
        lastSavedContentRef.current = content;
        setPrompt(detail.user_prompt);
      } catch {
        setEditorContent("");
        lastSavedContentRef.current = "";
      }
    },
    [activeSceneId, projectId]
  );

  // --- New scene: deselect, clear editor ---
  const handleNewScene = useCallback(() => {
    setActiveSceneId(null);
    setEditorContent("");
    lastSavedContentRef.current = "";
    setPrompt("");
    setStage("idle");
    setGenerationError("");
  }, []);

  // --- Scene CRUD ---
  const handleSceneDelete = useCallback(
    async (sceneId: string) => {
      try {
        await deleteScene(projectId, sceneId);
        setScenes((prev) => prev.filter((s) => s.id !== sceneId));
        if (activeSceneId === sceneId) {
          handleNewScene();
        }
      } catch {
        // silent
      }
    },
    [projectId, activeSceneId, handleNewScene]
  );

  const handleScenePin = useCallback(
    async (sceneId: string, pinned: boolean) => {
      try {
        await updateScene(projectId, sceneId, { is_pinned: pinned });
        setScenes((prev) =>
          prev.map((s) => (s.id === sceneId ? { ...s, is_pinned: pinned } : s))
        );
      } catch {
        // silent
      }
    },
    [projectId]
  );

  const handleSceneRename = useCallback(
    async (sceneId: string, label: string) => {
      try {
        await updateScene(projectId, sceneId, { scene_label: label });
        setScenes((prev) =>
          prev.map((s) => (s.id === sceneId ? { ...s, scene_label: label } : s))
        );
      } catch {
        // silent
      }
    },
    [projectId]
  );

  const handleScenesReorder = useCallback(
    async (orderedIds: string[]) => {
      // Optimistic reorder
      setScenes((prev) => {
        const map = new Map(prev.map((s) => [s.id, s]));
        return orderedIds.map((id) => map.get(id)!).filter(Boolean);
      });
      try {
        await reorderScenes(projectId, orderedIds);
      } catch {
        // revert by re-fetching
        const fresh = await fetchScenes(projectId);
        setScenes(fresh);
      }
    },
    [projectId]
  );

  // --- Header actions ---
  const handleTitleChange = useCallback(
    async (title: string) => {
      try {
        const updated = await updateProject(projectId, { title });
        setProject(updated);
      } catch {
        // silent
      }
    },
    [projectId]
  );

  const handleProfileChange = useCallback(
    async (profileId: string) => {
      setSelectedProfileId(profileId);
      try {
        await updateProject(projectId, {
          voice_profile_id: profileId || undefined,
        });
        setProject((prev) =>
          prev ? { ...prev, voice_profile_id: profileId || null } : prev
        );
      } catch {
        // silent
      }
    },
    [projectId]
  );

  // --- Generation ---
  const runGeneration = useCallback(
    async (path: string, body: Record<string, unknown>) => {
      setGenerationError("");
      setStage("brain");
      setEditorContent("");
      lastSavedContentRef.current = "";
      setSuggestions(null);

      try {
        await apiGenerationStream(path, body, (event: GenerationEvent) => {
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
              }
              break;
            case "token":
              setEditorContent((prev) => prev + (event.content ?? ""));
              break;
            case "polish_complete":
              if (event.content) {
                setEditorContent(event.content);
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
              // Refresh scenes list to pick up the new scene
              if (event.metadata?.generation_id) {
                setActiveSceneId(event.metadata.generation_id);
              }
              fetchScenes(projectId).then(setScenes).catch(() => {});
              break;
            case "error":
              setStage("error");
              setGenerationError(event.content ?? event.message ?? "Generation failed.");
              break;
          }
        });
      } catch (e) {
        setStage("error");
        setGenerationError(e instanceof Error ? e.message : "Generation failed.");
      }
    },
    [projectId]
  );

  const handleGenerate = useCallback(() => {
    if (!prompt.trim()) return;
    const body: Record<string, unknown> = {
      project_id: projectId,
      prompt: prompt.trim(),
    };
    if (selectedProfileId) body.voice_profile_id = selectedProfileId;
    runGeneration("/api/generate", body);
  }, [prompt, projectId, selectedProfileId, runGeneration]);

  const handleContinue = useCallback(() => {
    if (!activeSceneId) return;
    runGeneration("/api/generate/continue", {
      project_id: projectId,
      scene_id: activeSceneId,
    });
  }, [activeSceneId, projectId, runGeneration]);

  const handleRegenerate = useCallback(() => {
    if (!prompt.trim()) return;
    const body: Record<string, unknown> = {
      project_id: projectId,
      prompt: prompt.trim(),
    };
    if (selectedProfileId) body.voice_profile_id = selectedProfileId;
    if (activeSceneId) body.scene_id = activeSceneId;
    runGeneration("/api/generate", body);
  }, [prompt, projectId, selectedProfileId, activeSceneId, runGeneration]);

  const handleRefine = useCallback(
    (feedback: string) => {
      if (!activeSceneId) return;
      runGeneration("/api/generate/refine", {
        project_id: projectId,
        scene_id: activeSceneId,
        feedback,
      });
    },
    [activeSceneId, projectId, runGeneration]
  );

  // --- Computed values ---
  const totalWords = scenes.reduce((sum, s) => sum + (s.word_count ?? 0), 0);
  const isGenerating = stage === "brain" || stage === "voice" || stage === "polish";

  // --- Loading / error states ---
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

  return (
    <div className="flex flex-col h-screen bg-zinc-950">
      <ProjectHeader
        project={project}
        profiles={profiles}
        selectedProfileId={selectedProfileId}
        onProfileChange={handleProfileChange}
        onTitleChange={handleTitleChange}
        totalWords={totalWords}
        stage={stage}
        stageMessage={stageMessage}
        brainMessageIdx={brainMessageIdx}
      />

      <div className="flex flex-1 min-h-0">
        <SceneSidebar
          scenes={scenes}
          activeSceneId={activeSceneId}
          onSceneSelect={handleSceneSelect}
          onSceneDelete={handleSceneDelete}
          onScenePin={handleScenePin}
          onSceneRename={handleSceneRename}
          onScenesReorder={handleScenesReorder}
          onNewScene={handleNewScene}
          isGenerating={isGenerating}
        />

        <div className="flex-1 flex flex-col min-w-0">
          <Editor
            content={editorContent}
            onChange={setEditorContent}
            stage={stage}
            brainMessageIdx={brainMessageIdx}
            error={generationError}
            hasActiveScene={activeSceneId !== null}
            saveStatus={saveStatus}
          />

          {suggestions && (
            <SuggestionPanel
              projectId={projectId}
              suggestions={suggestions}
              onClose={() => setSuggestions(null)}
            />
          )}

          <PromptBar
            prompt={prompt}
            onPromptChange={setPrompt}
            onGenerate={handleGenerate}
            onContinue={handleContinue}
            onRegenerate={handleRegenerate}
            onRefine={handleRefine}
            stage={stage}
            hasActiveScene={activeSceneId !== null}
            hasVoiceProfile={!!selectedProfileId}
          />
        </div>
      </div>
    </div>
  );
}
