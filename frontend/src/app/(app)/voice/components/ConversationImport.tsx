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

const ACCEPTED_EXTENSIONS = ".zip,.md,.txt,.json,.pdf";

// --- Export Instructions Modal ---

function ExportInstructionsModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70"
        onClick={onClose}
      />
      {/* Modal */}
      <div className="relative bg-zinc-900 border border-zinc-700 rounded-xl max-w-lg w-full mx-4 p-6 shadow-2xl">
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-lg font-semibold text-zinc-100">
            How to export your conversations
          </h3>
          <button
            onClick={onClose}
            className="text-zinc-500 hover:text-zinc-300 transition-colors text-xl leading-none"
          >
            &times;
          </button>
        </div>

        <div className="space-y-5">
          {/* ChatGPT */}
          <div>
            <h4 className="text-sm font-medium text-zinc-200 mb-2">
              ChatGPT
            </h4>
            <ol className="text-zinc-400 text-sm space-y-1 list-decimal list-inside">
              <li>Open ChatGPT &rarr; Settings &rarr; Data Controls</li>
              <li>Click &quot;Export Data&quot;</li>
              <li>Wait for the email with your download link</li>
              <li>Upload the .zip file here</li>
            </ol>
          </div>

          {/* Google Docs */}
          <div>
            <h4 className="text-sm font-medium text-zinc-200 mb-2">
              Google Docs
              <span className="ml-2 text-xs text-emerald-400 font-normal">
                Recommended
              </span>
            </h4>
            <ol className="text-zinc-400 text-sm space-y-1 list-decimal list-inside">
              <li>Open your conversation document in Google Docs</li>
              <li>File &rarr; Download &rarr; Markdown (.md)</li>
              <li>Upload the .md file here</li>
            </ol>
          </div>

          {/* Claude */}
          <div>
            <h4 className="text-sm font-medium text-zinc-200 mb-2">
              Claude
            </h4>
            <p className="text-zinc-500 text-sm">
              Claude doesn&apos;t support conversation export yet (coming
              soon). You can copy-paste conversations into a .txt file as a
              workaround.
            </p>
          </div>

          {/* Generic */}
          <div>
            <h4 className="text-sm font-medium text-zinc-200 mb-2">
              Other sources
            </h4>
            <p className="text-zinc-500 text-sm">
              Any .md, .txt, .json, or .pdf file with your conversations will
              work. Copy-paste your chats into a text file if needed.
            </p>
          </div>
        </div>

        <button
          onClick={onClose}
          className="mt-6 w-full rounded-lg bg-zinc-800 px-4 py-2.5 text-sm text-zinc-200 font-medium hover:bg-zinc-700 transition-colors"
        >
          Got it
        </button>
      </div>
    </div>
  );
}

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
          Upload your conversation export and we&apos;ll analyze your natural
          communication patterns for an even more accurate voice match.
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
            accept={ACCEPTED_EXTENSIONS}
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
                Upload your conversation export (.zip, .md, .pdf, .txt, or .json)
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

        {/* Export help link → opens modal */}
        <div className="mb-4">
          <button
            onClick={() => setShowExportHelp(true)}
            className="text-zinc-500 text-xs hover:text-zinc-300 transition-colors inline-flex items-center gap-1"
          >
            How to export your conversations
            <span className="text-[10px]">&nearr;</span>
          </button>
        </div>

        {showExportHelp && (
          <ExportInstructionsModal onClose={() => setShowExportHelp(false)} />
        )}

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
