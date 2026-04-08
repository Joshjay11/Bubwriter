"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { startStoryDna } from "@/lib/api";

export default function StoryDnaEntryPage() {
  const router = useRouter();
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");

  const handleStart = async () => {
    setStarting(true);
    setError("");
    try {
      const result = await startStoryDna();
      // Stash the first question so the session page can render it without
      // re-calling /start (which would burn an IP rate-limit slot).
      sessionStorage.setItem(
        `sdna_first_${result.session_id}`,
        result.first_question
      );
      router.push(`/story-dna/session/${result.session_id}`);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Could not start the test.";
      setError(msg);
      setStarting(false);
    }
  };

  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-6 py-16">
      <div className="max-w-xl text-center">
        <h1 className="text-4xl font-bold mb-4">Story DNA Test</h1>
        <p className="text-foreground/70 mb-8">
          5 to 7 short questions about the stories you love, the characters
          you can&apos;t look away from, and what you refuse in fiction. We&apos;ll
          turn your answers into a Story DNA Profile and 3-5 story concepts
          built for you.
        </p>
        <button
          onClick={handleStart}
          disabled={starting}
          className="rounded-lg bg-foreground px-8 py-4 text-background text-lg font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
        >
          {starting ? "Starting…" : "Start the test"}
        </button>
        {error && (
          <p className="mt-4 text-sm text-red-500">{error}</p>
        )}
      </div>
    </main>
  );
}
