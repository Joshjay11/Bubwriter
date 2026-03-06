"use client";

export type PipelineStage =
  | "idle"
  | "brain"
  | "voice"
  | "polish"
  | "complete"
  | "error";

export const BRAIN_MESSAGES = [
  "Analyzing your story context...",
  "Designing scene structure...",
  "Building tension arc...",
  "Mapping character dynamics...",
  "Plotting emotional beats...",
];

export function StageIndicator({
  stage,
  message,
  brainMessageIdx,
}: {
  stage: PipelineStage;
  message: string;
  brainMessageIdx: number;
}) {
  const displayMessage =
    stage === "brain" ? BRAIN_MESSAGES[brainMessageIdx] : message;

  return (
    <div className="flex items-center gap-2">
      <div className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
      <span className="text-zinc-400 text-sm">{displayMessage}</span>
    </div>
  );
}
