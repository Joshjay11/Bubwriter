"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import type { ProjectDetail } from "@/lib/api";
import type { PipelineStage } from "./StageIndicator";
import { StageIndicator } from "./StageIndicator";

interface VoiceProfile {
  id: string;
  profile_name: string;
}

interface ProjectHeaderProps {
  project: ProjectDetail;
  profiles: VoiceProfile[];
  selectedProfileId: string;
  onProfileChange: (id: string) => void;
  onTitleChange: (title: string) => void;
  totalWords: number;
  stage: PipelineStage;
  stageMessage: string;
  brainMessageIdx: number;
}

export function ProjectHeader({
  project,
  profiles,
  selectedProfileId,
  onProfileChange,
  onTitleChange,
  totalWords,
  stage,
  stageMessage,
  brainMessageIdx,
}: ProjectHeaderProps) {
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(project.title);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editing]);

  const handleSaveTitle = () => {
    const trimmed = editTitle.trim();
    if (trimmed && trimmed !== project.title) {
      onTitleChange(trimmed);
    } else {
      setEditTitle(project.title);
    }
    setEditing(false);
  };

  const isGenerating =
    stage === "brain" || stage === "voice" || stage === "polish";

  return (
    <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 flex-shrink-0 bg-zinc-950">
      <div className="flex items-center gap-4 min-w-0">
        <Link
          href="/dashboard"
          className="text-zinc-500 hover:text-zinc-300 transition-colors text-sm flex-shrink-0"
        >
          &larr; Projects
        </Link>

        {editing ? (
          <input
            ref={inputRef}
            type="text"
            value={editTitle}
            onChange={(e) => setEditTitle(e.target.value)}
            onBlur={handleSaveTitle}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSaveTitle();
              if (e.key === "Escape") {
                setEditTitle(project.title);
                setEditing(false);
              }
            }}
            className="bg-zinc-800 rounded px-2 py-1 text-sm font-semibold text-zinc-100 focus:outline-none focus:ring-1 focus:ring-zinc-600 min-w-[100px]"
          />
        ) : (
          <button
            onClick={() => setEditing(true)}
            className="text-sm font-semibold text-zinc-100 hover:text-zinc-300 truncate max-w-[200px]"
            title="Click to rename"
          >
            {project.title}
          </button>
        )}

        <select
          value={selectedProfileId}
          onChange={(e) => onProfileChange(e.target.value)}
          disabled={isGenerating}
          className="bg-zinc-900 text-zinc-400 text-xs rounded px-2 py-1 border border-zinc-800 focus:outline-none focus:ring-1 focus:ring-zinc-700 max-w-[180px]"
        >
          <option value="">No voice</option>
          {profiles.map((p) => (
            <option key={p.id} value={p.id}>
              {p.profile_name}
            </option>
          ))}
        </select>
      </div>

      <div className="flex items-center gap-4 text-sm text-zinc-500 flex-shrink-0">
        {totalWords > 0 && (
          <span>{totalWords.toLocaleString()} words</span>
        )}
        {isGenerating && (
          <StageIndicator
            stage={stage}
            message={stageMessage}
            brainMessageIdx={brainMessageIdx}
          />
        )}
        {project.genre && (
          <span className="inline-block text-xs px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-500">
            {project.genre}
          </span>
        )}
      </div>
    </div>
  );
}
