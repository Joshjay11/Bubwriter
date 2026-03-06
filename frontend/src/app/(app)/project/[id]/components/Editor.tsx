"use client";

import { useRef, useEffect, useCallback } from "react";
import type { PipelineStage } from "./StageIndicator";
import { BRAIN_MESSAGES } from "./StageIndicator";

interface EditorProps {
  content: string;
  onChange: (content: string) => void;
  stage: PipelineStage;
  brainMessageIdx: number;
  error: string;
  hasActiveScene: boolean;
  saveStatus: "idle" | "saving" | "saved";
}

export function Editor({
  content,
  onChange,
  stage,
  brainMessageIdx,
  error,
  hasActiveScene,
  saveStatus,
}: EditorProps) {
  const editorRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll during streaming
  useEffect(() => {
    if (stage === "voice" && editorRef.current) {
      editorRef.current.scrollTop = editorRef.current.scrollHeight;
    }
  }, [content, stage]);

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      onChange(e.target.value);
    },
    [onChange]
  );

  const isEditable = stage === "idle" || stage === "complete";
  const showContent = content.length > 0;

  return (
    <div
      ref={editorRef}
      className="flex-1 overflow-y-auto bg-zinc-950 border-x border-zinc-800 min-h-0 relative"
    >
      {/* Save status indicator */}
      {saveStatus !== "idle" && hasActiveScene && isEditable && (
        <div className="absolute top-3 right-4 z-10">
          <span className="text-xs text-zinc-600">
            {saveStatus === "saving" ? "Saving..." : "Saved"}
          </span>
        </div>
      )}

      {/* Brain loading state */}
      {stage === "brain" && !showContent && (
        <div className="flex items-center justify-center h-full">
          <div className="text-center">
            <div className="inline-block w-6 h-6 border-2 border-zinc-600 border-t-zinc-300 rounded-full animate-spin mb-3" />
            <p className="text-zinc-400 text-sm animate-pulse">
              {BRAIN_MESSAGES[brainMessageIdx]}
            </p>
          </div>
        </div>
      )}

      {/* Polish loading overlay */}
      {stage === "polish" && showContent && (
        <div className="absolute inset-0 bg-zinc-950/60 flex items-center justify-center z-10">
          <div className="text-center">
            <div className="inline-block w-6 h-6 border-2 border-zinc-600 border-t-zinc-300 rounded-full animate-spin mb-3" />
            <p className="text-zinc-400 text-sm">Polishing your prose...</p>
          </div>
        </div>
      )}

      {/* Prose display (streaming / read-only) */}
      {showContent && !isEditable && (
        <div className="max-w-[680px] mx-auto px-8 py-6">
          <div className="text-zinc-200 leading-relaxed whitespace-pre-wrap font-serif text-[1.05rem]">
            {content}
            {stage === "voice" && (
              <span className="inline-block w-0.5 h-5 bg-zinc-400 animate-pulse ml-0.5 align-text-bottom" />
            )}
          </div>
        </div>
      )}

      {/* Editable textarea */}
      {showContent && isEditable && (
        <div className="max-w-[680px] mx-auto px-8 py-6">
          <textarea
            ref={textareaRef}
            value={content}
            onChange={handleChange}
            className="w-full bg-transparent text-zinc-200 leading-relaxed whitespace-pre-wrap font-serif text-[1.05rem] resize-none focus:outline-none min-h-[calc(100vh-16rem)]"
            spellCheck
          />
        </div>
      )}

      {/* Empty state */}
      {!showContent && stage === "idle" && (
        <div className="flex items-center justify-center h-full">
          <div className="text-center max-w-md">
            {hasActiveScene ? (
              <p className="text-zinc-700 text-sm">
                This scene has no content yet.
              </p>
            ) : (
              <>
                <p className="text-zinc-400 text-lg mb-3">
                  Write your first scene.
                </p>
                <p className="text-zinc-600 text-sm mb-4">
                  Type a prompt below and hit Generate.
                </p>
                <div className="space-y-2 text-zinc-700 text-sm">
                  <p>&quot;Marcus arrives at the abandoned vault&quot;</p>
                  <p>&quot;Opening scene — Elena gets the call&quot;</p>
                  <p>&quot;The confrontation in the rain&quot;</p>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Error display */}
      {error && (
        <div className="max-w-[680px] mx-auto px-8 pb-6">
          <div className="p-4 bg-red-950/50 border border-red-900 rounded-lg">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        </div>
      )}
    </div>
  );
}
