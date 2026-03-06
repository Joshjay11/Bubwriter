"use client";

import { useState, useRef } from "react";
import {
  apiConversationImport,
  type ConversationImportStats,
} from "@/lib/api";

interface ConversationImportProps {
  sessionId: string;
  onComplete: () => void;
  onSkip: () => void;
}

type ImportPhase = "upload" | "processing" | "complete" | "error";

export default function ConversationImport({
  sessionId,
  onComplete,
  onSkip,
}: ConversationImportProps) {
  const [phase, setPhase] = useState<ImportPhase>("upload");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [statusText, setStatusText] = useState("");
  const [statusLines, setStatusLines] = useState<string[]>([]);
  const [stats, setStats] = useState<ConversationImportStats | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [showExportHelp, setShowExportHelp] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      setErrorMessage("");
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) return;

    setPhase("processing");
    setProgress(0);
    setStatusText("Starting import...");
    setStatusLines([]);

    try {
      await apiConversationImport(
        selectedFile,
        sessionId,
        (percent, detail) => {
          setProgress(percent);
          setStatusText(detail);
          setStatusLines((prev) => {
            // Avoid duplicate consecutive lines
            if (prev.length > 0 && prev[prev.length - 1] === detail) {
              return prev;
            }
            return [...prev, detail];
          });
        },
        (importStats) => {
          setStats(importStats);
          setPhase("complete");
        },
        (detail) => {
          setErrorMessage(detail);
          setPhase("error");
        }
      );
    } catch (e) {
      setErrorMessage(
        e instanceof Error ? e.message : "Import failed. Please try again."
      );
      setPhase("error");
    }
  };

  const handleRetry = () => {
    setPhase("upload");
    setSelectedFile(null);
    setErrorMessage("");
    setProgress(0);
    setStatusText("");
    setStatusLines([]);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  // --- Upload Prompt ---
  if (phase === "upload") {
    return (
      <div className="bg-zinc-900 rounded-lg p-6 mt-8">
        <h2 className="text-lg font-semibold text-zinc-100 mb-2">
          Want a deeper voice profile?
        </h2>
        <p className="text-zinc-400 text-sm mb-4 leading-relaxed">
          Upload your ChatGPT conversation export and we&apos;ll analyze your
          natural communication patterns for an even more accurate voice match.
        </p>
        <p className="text-zinc-500 text-xs mb-6">
          Your conversations are analyzed and immediately discarded — we never
          store your chat history. Only the personality patterns we extract are
          kept.
        </p>

        {/* File input */}
        <div className="mb-4">
          <input
            ref={fileInputRef}
            type="file"
            accept=".zip"
            onChange={handleFileSelect}
            className="hidden"
            id="conversation-upload"
          />
          <label
            htmlFor="conversation-upload"
            className="block w-full rounded-lg border border-dashed border-zinc-700 p-4 text-center cursor-pointer hover:border-zinc-500 transition-colors"
          >
            {selectedFile ? (
              <span className="text-zinc-200 text-sm">
                {selectedFile.name}{" "}
                <span className="text-zinc-500">
                  ({(selectedFile.size / (1024 * 1024)).toFixed(1)} MB)
                </span>
              </span>
            ) : (
              <span className="text-zinc-500 text-sm">
                Choose ChatGPT export (.zip)
              </span>
            )}
          </label>
        </div>

        {errorMessage && (
          <p className="text-red-400 text-sm mb-4">{errorMessage}</p>
        )}

        {/* Upload button */}
        {selectedFile && (
          <button
            onClick={handleUpload}
            className="w-full rounded-lg bg-zinc-100 px-6 py-3 text-zinc-900 font-medium hover:bg-zinc-200 transition-colors mb-4"
          >
            Analyze My Conversations
          </button>
        )}

        {/* Export help */}
        <div className="mb-4">
          <button
            onClick={() => setShowExportHelp(!showExportHelp)}
            className="text-zinc-500 text-xs hover:text-zinc-300 transition-colors"
          >
            {showExportHelp ? "Hide" : "How to export from ChatGPT"}
          </button>
          {showExportHelp && (
            <div className="mt-2 bg-zinc-800 rounded-lg p-3">
              <ol className="text-zinc-400 text-xs space-y-1 list-decimal list-inside">
                <li>Open ChatGPT and go to Settings</li>
                <li>Click Data Controls</li>
                <li>Click Export Data</li>
                <li>
                  You&apos;ll receive an email with a download link for your
                  export ZIP
                </li>
              </ol>
            </div>
          )}
        </div>

        {/* Skip */}
        <button
          onClick={onSkip}
          className="w-full text-zinc-500 text-sm hover:text-zinc-300 transition-colors py-2"
        >
          Skip this step
        </button>
      </div>
    );
  }

  // --- Processing ---
  if (phase === "processing") {
    return (
      <div className="bg-zinc-900 rounded-lg p-6 mt-8">
        <h2 className="text-lg font-semibold text-zinc-100 mb-4">
          Analyzing your conversations...
        </h2>

        {/* Progress bar */}
        <div className="w-full bg-zinc-800 rounded-full h-2 mb-4">
          <div
            className="bg-zinc-100 h-2 rounded-full transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>

        <p className="text-zinc-300 text-sm mb-3">{statusText}</p>

        {/* Accumulated status lines */}
        {statusLines.length > 1 && (
          <div className="space-y-1">
            {statusLines.slice(0, -1).map((line, i) => (
              <p key={i} className="text-zinc-500 text-xs">
                {line}
              </p>
            ))}
          </div>
        )}
      </div>
    );
  }

  // --- Error ---
  if (phase === "error") {
    return (
      <div className="bg-zinc-900 rounded-lg p-6 mt-8">
        <h2 className="text-lg font-semibold text-red-400 mb-2">
          Import failed
        </h2>
        <p className="text-zinc-400 text-sm mb-4">{errorMessage}</p>
        <div className="flex gap-3">
          <button
            onClick={handleRetry}
            className="flex-1 rounded-lg bg-zinc-100 px-6 py-3 text-zinc-900 font-medium hover:bg-zinc-200 transition-colors"
          >
            Try Again
          </button>
          <button
            onClick={onSkip}
            className="flex-1 rounded-lg border border-zinc-700 px-6 py-3 text-zinc-300 font-medium hover:bg-zinc-800 transition-colors"
          >
            Skip this step
          </button>
        </div>
      </div>
    );
  }

  // --- Complete ---
  return (
    <div className="bg-zinc-900 rounded-lg p-6 mt-8">
      <h2 className="text-lg font-semibold text-zinc-100 mb-2">
        Conversation analysis complete
      </h2>
      {stats && (
        <p className="text-zinc-400 text-sm mb-6 leading-relaxed">
          Analyzed {stats.messages_analyzed.toLocaleString()} messages (
          {stats.words_analyzed.toLocaleString()} words) from{" "}
          {stats.total_conversations.toLocaleString()} conversations. Your voice
          profile will be significantly enriched.
        </p>
      )}
      <button
        onClick={onComplete}
        className="w-full rounded-lg bg-zinc-100 px-6 py-3 text-zinc-900 font-medium hover:bg-zinc-200 transition-colors"
      >
        Continue to Interview
      </button>
    </div>
  );
}
