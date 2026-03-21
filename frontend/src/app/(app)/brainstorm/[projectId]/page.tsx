"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  apiBrainstormStream,
  evaluateBrainstorm,
  addBibleEntry,
  fetchProject,
  type ProjectDetail,
  type BrainstormDoneData,
  type IdeaEvaluation,
} from "@/lib/api";

const THOUGHT_BLOCK_RE = /<thought_process>[\s\S]*?<\/thought_process>/g;

function stripThoughtBlocks(text: string): string {
  let cleaned = text.replace(THOUGHT_BLOCK_RE, "");
  const openIdx = cleaned.indexOf("<thought_process>");
  if (openIdx !== -1) {
    cleaned = cleaned.substring(0, openIdx);
  }
  return cleaned;
}

interface Message {
  role: "user" | "assistant";
  content: string;
}

export default function BrainstormPage() {
  const params = useParams<{ projectId: string }>();
  const router = useRouter();
  const projectId = params.projectId;

  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [userInput, setUserInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [questionsAsked, setQuestionsAsked] = useState(0);
  const [evaluation, setEvaluation] = useState<IdeaEvaluation | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [error, setError] = useState("");

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);

  // Load project on mount
  useEffect(() => {
    fetchProject(projectId).then(setProject).catch(() => {});
  }, [projectId]);

  // Start session
  const startSession = useCallback(async () => {
    setError("");
    setStreaming(true);
    setStreamingText("");
    setMessages([]);
    setEvaluation(null);

    let accumulated = "";
    try {
      await apiBrainstormStream(
        "/api/brainstorm/start",
        {
          project_id: projectId,
          genre: project?.genre,
          distribution_format: project?.distribution_format,
        },
        (token) => {
          accumulated += token;
          setStreamingText(stripThoughtBlocks(accumulated));
        },
        (data: BrainstormDoneData) => {
          const clean = accumulated.replace(THOUGHT_BLOCK_RE, "").trim();
          setMessages([{ role: "assistant", content: clean }]);
          setStreamingText("");
          setSessionId(data.session_id ?? null);
          setQuestionsAsked(data.questions_asked);
        }
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start brainstorm.");
    } finally {
      setStreaming(false);
      inputRef.current?.focus();
    }
  }, [projectId, project]);

  // Send message
  const sendMessage = useCallback(
    async (message: string) => {
      if (!sessionId || streaming || !message.trim()) return;

      setError("");
      setStreaming(true);
      setStreamingText("");
      setMessages((prev) => [...prev, { role: "user", content: message }]);
      setUserInput("");

      let accumulated = "";
      try {
        await apiBrainstormStream(
          "/api/brainstorm/respond",
          { session_id: sessionId, message: message.trim() },
          (token) => {
            accumulated += token;
            setStreamingText(stripThoughtBlocks(accumulated));
          },
          (data: BrainstormDoneData) => {
            const clean = accumulated.replace(THOUGHT_BLOCK_RE, "").trim();
            setMessages((prev) => [
              ...prev,
              { role: "assistant", content: clean },
            ]);
            setStreamingText("");
            setQuestionsAsked(data.questions_asked);
          }
        );
      } catch (e) {
        setError(e instanceof Error ? e.message : "Brainstorm error.");
      } finally {
        setStreaming(false);
        inputRef.current?.focus();
      }
    },
    [sessionId, streaming]
  );

  // Evaluate
  const handleEvaluate = useCallback(async () => {
    if (!sessionId || evaluating) return;
    setEvaluating(true);
    setError("");

    try {
      const result = await evaluateBrainstorm(sessionId);
      setEvaluation(result.evaluation);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Evaluation failed.");
    } finally {
      setEvaluating(false);
    }
  }, [sessionId, evaluating]);

  // Approve bible entries from evaluation
  const approveBibleEntries = useCallback(async () => {
    if (!evaluation?.extracted_bible_entries) return;
    const entries = evaluation.extracted_bible_entries;

    try {
      for (const [section, items] of Object.entries(entries)) {
        for (const item of items as Record<string, unknown>[]) {
          await addBibleEntry(projectId, section, {
            ...item,
            id: `${section}_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
            source: "brainstorm",
          });
        }
      }
      router.push(`/project/${projectId}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save bible entries.");
    }
  }, [evaluation, projectId, router]);

  // Handle Enter key
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(userInput);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-zinc-950">
      {/* Header */}
      <div className="border-b border-zinc-800 px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-medium text-zinc-100">
            Story Architect
          </h1>
          <p className="text-xs text-zinc-500">
            {project?.title ?? "Loading..."}
            {questionsAsked > 0 && ` — ${questionsAsked} questions deep`}
          </p>
        </div>
        <div className="flex gap-2">
          {sessionId && !streaming && (
            <button
              onClick={handleEvaluate}
              disabled={evaluating || questionsAsked < 2}
              className="text-sm px-3 py-1.5 rounded bg-indigo-600/20 text-indigo-400 hover:bg-indigo-600/30 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {evaluating ? "Evaluating..." : "Evaluate Idea"}
            </button>
          )}
          <button
            onClick={() => router.push(`/project/${projectId}`)}
            className="text-sm px-3 py-1.5 rounded bg-zinc-800 text-zinc-400 hover:text-zinc-200"
          >
            Back to Project
          </button>
        </div>
      </div>

      {/* Chat area */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-5">
        {!sessionId && !streaming && (
          <div className="flex flex-col items-center justify-center h-full gap-4">
            <p className="text-zinc-400 text-center max-w-md">
              Start a brainstorming session to develop your story concept.
              The Story Architect will ask probing questions to help you
              discover your story — without writing it for you.
            </p>
            <button
              onClick={startSession}
              className="px-5 py-2.5 rounded-lg bg-indigo-600 text-white font-medium hover:bg-indigo-500"
            >
              Start Brainstorming
            </button>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i}>
            {msg.role === "assistant" ? (
              <div className="max-w-2xl">
                <p className="text-zinc-200 leading-relaxed whitespace-pre-wrap">
                  {msg.content}
                </p>
              </div>
            ) : (
              <div className="max-w-2xl ml-auto">
                <div className="bg-zinc-900 rounded-lg p-4">
                  <p className="text-zinc-300 whitespace-pre-wrap">{msg.content}</p>
                </div>
              </div>
            )}
          </div>
        ))}

        {streamingText && (
          <div className="max-w-2xl">
            <p className="text-zinc-200 leading-relaxed whitespace-pre-wrap">
              {streamingText}
              <span className="inline-block w-1.5 h-4 bg-zinc-400 ml-0.5 animate-pulse" />
            </p>
          </div>
        )}

        {error && (
          <p className="text-red-400 text-sm">{error}</p>
        )}

        {/* Evaluation Results */}
        {evaluation && (
          <EvaluationPanel
            evaluation={evaluation}
            onApproveEntries={approveBibleEntries}
          />
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input bar */}
      {sessionId && (
        <div className="border-t border-zinc-800 px-6 py-4">
          <div className="flex gap-3 max-w-2xl">
            <textarea
              ref={inputRef}
              value={userInput}
              onChange={(e) => setUserInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Answer the question..."
              disabled={streaming}
              rows={2}
              className="flex-1 bg-zinc-900 border border-zinc-700 rounded-lg px-4 py-2.5 text-zinc-200 placeholder-zinc-600 resize-none focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
            />
            <button
              onClick={() => sendMessage(userInput)}
              disabled={streaming || !userInput.trim()}
              className="px-4 py-2 rounded-lg bg-indigo-600 text-white font-medium hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed self-end"
            >
              Send
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// --- Evaluation Panel ---

function EvaluationPanel({
  evaluation,
  onApproveEntries,
}: {
  evaluation: IdeaEvaluation;
  onApproveEntries: () => void;
}) {
  const hasEntries = Object.values(
    evaluation.extracted_bible_entries ?? {}
  ).some((arr) => (arr as unknown[]).length > 0);

  return (
    <div className="max-w-2xl bg-zinc-900/80 border border-zinc-700/50 rounded-lg p-5 space-y-4">
      <h3 className="text-sm font-semibold text-zinc-300 uppercase tracking-wide">
        Idea Evaluation
      </h3>

      {/* Scores */}
      <div className="grid grid-cols-3 gap-3">
        <ScoreCard label="Premise" score={evaluation.premise_clarity} />
        <ScoreCard label="Stakes" score={evaluation.stakes_strength} />
        <ScoreCard label="Conflict" score={evaluation.conflict_depth} />
      </div>

      {/* Meta */}
      <div className="flex gap-4 text-xs text-zinc-500">
        <span>Genre fit: <strong className="text-zinc-300">{evaluation.genre_fit}</strong></span>
        <span>Series: <strong className="text-zinc-300">{evaluation.series_potential}</strong></span>
      </div>
      {evaluation.target_audience && (
        <p className="text-xs text-zinc-400">
          Audience: {evaluation.target_audience}
        </p>
      )}

      {/* Unresolved */}
      {evaluation.unresolved_questions.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-zinc-400 mb-1">
            Still to decide:
          </h4>
          <ul className="space-y-1">
            {evaluation.unresolved_questions.map((q, i) => (
              <li key={i} className="text-xs text-zinc-500 pl-3 relative">
                <span className="absolute left-0">-</span> {q}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Bible entries */}
      {hasEntries && (
        <button
          onClick={onApproveEntries}
          className="text-sm px-4 py-2 rounded bg-emerald-600/20 text-emerald-400 hover:bg-emerald-600/30"
        >
          Add extracted entries to Story Bible
        </button>
      )}
    </div>
  );
}

function ScoreCard({ label, score }: { label: string; score: number }) {
  const color =
    score >= 7
      ? "text-emerald-400"
      : score >= 4
        ? "text-amber-400"
        : "text-red-400";

  return (
    <div className="bg-zinc-800/60 rounded-lg p-3 text-center">
      <div className={`text-2xl font-bold ${color}`}>{score}</div>
      <div className="text-[10px] text-zinc-500 uppercase tracking-wider">
        {label}
      </div>
    </div>
  );
}
