"use client";

import { useState, useEffect, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { streamStoryDnaRespond, finalizeStoryDna } from "@/lib/api";

interface Turn {
  role: "assistant" | "user";
  content: string;
}

export default function StoryDnaSessionPage() {
  const router = useRouter();
  const params = useParams();
  const sessionId = (params?.sessionId as string) ?? "";

  const [turns, setTurns] = useState<Turn[]>([]);
  const [streamingText, setStreamingText] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [input, setInput] = useState("");
  const [readyForFinalize, setReadyForFinalize] = useState(false);
  const [finalizing, setFinalizing] = useState(false);
  const [error, setError] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  // Pull the first question stashed by the entry page
  useEffect(() => {
    const key = `sdna_first_${sessionId}`;
    const first = sessionStorage.getItem(key);
    if (first) {
      setTurns([{ role: "assistant", content: first }]);
      sessionStorage.removeItem(key);
    } else {
      // If a user reloaded directly into a session URL, we have no way to
      // recover the first question — bounce them back to the entry page.
      setError("This Story DNA session expired or can't be resumed. Please start again.");
    }
  }, [sessionId]);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, streamingText]);

  const handleSend = async () => {
    if (!input.trim() || streaming) return;
    const answer = input.trim();
    setInput("");
    setTurns((prev) => [...prev, { role: "user", content: answer }]);
    setStreaming(true);
    setStreamingText("");
    setError("");

    let accumulated = "";
    try {
      await streamStoryDnaRespond(
        sessionId,
        answer,
        (token) => {
          accumulated += token;
          setStreamingText(accumulated);
        },
        (data) => {
          setTurns((prev) => [
            ...prev,
            { role: "assistant", content: accumulated },
          ]);
          setStreamingText("");
          setReadyForFinalize(data.ready_for_finalize);
        }
      );
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Story DNA interrupted.";
      setError(msg);
    } finally {
      setStreaming(false);
    }
  };

  const handleFinalize = async () => {
    setFinalizing(true);
    setError("");
    try {
      // Trigger synthesis — results page will re-call finalize (it's
      // idempotent) so we don't need to pass any state.
      await finalizeStoryDna(sessionId);
      router.push(`/story-dna/results/${sessionId}`);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Could not generate your DNA.";
      setError(msg);
      setFinalizing(false);
    }
  };

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col px-6 py-12">
      <h1 className="text-2xl font-bold mb-6">Story DNA</h1>

      <div className="flex-1 space-y-4 mb-6">
        {turns.map((turn, i) => (
          <div
            key={i}
            className={
              turn.role === "assistant"
                ? "rounded-lg bg-foreground/5 p-4"
                : "rounded-lg bg-foreground/10 p-4 ml-8"
            }
          >
            <p className="whitespace-pre-wrap">{turn.content}</p>
          </div>
        ))}
        {streamingText && (
          <div className="rounded-lg bg-foreground/5 p-4">
            <p className="whitespace-pre-wrap">{streamingText}</p>
          </div>
        )}
        <div ref={scrollRef} />
      </div>

      {error && (
        <p className="mb-4 text-sm text-red-500">{error}</p>
      )}

      {readyForFinalize ? (
        <button
          onClick={handleFinalize}
          disabled={finalizing}
          className="rounded-lg bg-foreground px-6 py-3 text-background font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
        >
          {finalizing ? "Generating your Story DNA…" : "Generate my Story DNA"}
        </button>
      ) : (
        <div className="flex gap-3">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            disabled={streaming || !!error}
            placeholder="Your answer…"
            rows={3}
            className="flex-1 rounded-lg border border-foreground/20 bg-background p-3 text-sm focus:outline-none focus:border-foreground/40 disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={streaming || !input.trim() || !!error}
            className="self-end rounded-lg bg-foreground px-6 py-3 text-background font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            Send
          </button>
        </div>
      )}
    </main>
  );
}
