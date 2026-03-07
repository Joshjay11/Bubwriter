"use client";

import { useState, useCallback } from "react";
import type { PipelineStage } from "./StageIndicator";

interface PromptBarProps {
  prompt: string;
  onPromptChange: (value: string) => void;
  onGenerate: () => void;
  onContinue: () => void;
  onRegenerate: () => void;
  onRefine: (feedback: string) => void;
  stage: PipelineStage;
  hasActiveScene: boolean;
  hasVoiceProfile: boolean;
}

export function PromptBar({
  prompt,
  onPromptChange,
  onGenerate,
  onContinue,
  onRegenerate,
  onRefine,
  stage,
  _hasActiveScene,
  hasVoiceProfile,
}: PromptBarProps) {
  const [showRefine, setShowRefine] = useState(false);
  const [refineFeedback, setRefineFeedback] = useState("");

  const isGenerating =
    stage === "brain" || stage === "voice" || stage === "polish";
  const isComplete = stage === "complete";

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && e.ctrlKey) {
        e.preventDefault();
        if (prompt.trim() && hasVoiceProfile && !isGenerating) {
          onGenerate();
        }
      }
    },
    [prompt, hasVoiceProfile, isGenerating, onGenerate]
  );

  const handleRefineSubmit = useCallback(() => {
    if (refineFeedback.trim()) {
      onRefine(refineFeedback.trim());
      setRefineFeedback("");
      setShowRefine(false);
    }
  }, [refineFeedback, onRefine]);

  return (
    <div className="flex-shrink-0 border border-zinc-800 bg-zinc-900 rounded-b-lg">
      {/* No voice profile warning */}
      {!hasVoiceProfile && (
        <div className="px-4 py-2 border-b border-zinc-800 bg-zinc-900/80">
          <p className="text-amber-400/80 text-xs">
            No voice assigned. Your prose won&apos;t sound like you.
          </p>
        </div>
      )}

      {/* Action bar (after completion) */}
      {isComplete && (
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-zinc-800">
          <button
            onClick={onContinue}
            className="rounded-md bg-zinc-800 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-700 transition-colors"
          >
            Continue
          </button>
          <button
            onClick={onRegenerate}
            disabled={!prompt.trim()}
            className="rounded-md bg-zinc-800 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-700 transition-colors disabled:opacity-40"
          >
            Regenerate
          </button>
          <button
            onClick={() => setShowRefine(!showRefine)}
            className="rounded-md bg-zinc-800 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-700 transition-colors"
          >
            Refine
          </button>
          <button
            onClick={() => {
              const content = document.querySelector("textarea")?.value;
              if (content) navigator.clipboard.writeText(content);
            }}
            className="rounded-md bg-zinc-800 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-700 transition-colors"
          >
            Copy
          </button>
        </div>
      )}

      {/* Refine input */}
      {showRefine && (
        <div className="px-4 py-2.5 border-b border-zinc-800 flex gap-2">
          <input
            type="text"
            value={refineFeedback}
            onChange={(e) => setRefineFeedback(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                handleRefineSubmit();
              }
            }}
            placeholder="Make the dialogue sharper, less description..."
            autoFocus
            className="flex-1 bg-zinc-800 rounded-md px-3 py-1.5 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-zinc-700"
          />
          <button
            onClick={handleRefineSubmit}
            disabled={!refineFeedback.trim()}
            className="rounded-md bg-zinc-100 px-4 py-1.5 text-sm text-zinc-900 font-medium hover:bg-zinc-200 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Refine
          </button>
        </div>
      )}

      {/* Prompt input */}
      <div className="p-4">
        <textarea
          value={prompt}
          onChange={(e) => onPromptChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Describe your scene... (e.g., 'Marcus finds the artifact in the Vault')"
          disabled={isGenerating}
          rows={2}
          className="w-full bg-transparent text-zinc-100 placeholder:text-zinc-600 resize-none focus:outline-none disabled:opacity-50 text-sm"
        />
        <div className="flex justify-between items-center mt-2">
          <span className="text-xs text-zinc-600">
            Ctrl+Enter to generate
          </span>
          <button
            onClick={onGenerate}
            disabled={
              !prompt.trim() || !hasVoiceProfile || isGenerating
            }
            className="rounded-lg bg-zinc-100 px-5 py-2 text-sm text-zinc-900 font-medium hover:bg-zinc-200 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {isGenerating ? "Generating..." : "Generate"}
          </button>
        </div>
      </div>
    </div>
  );
}
