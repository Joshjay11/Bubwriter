"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { finalizeStoryDna, type StoryDnaFinalizeResponse } from "@/lib/api";

export default function StoryDnaResultsPage() {
  const router = useRouter();
  const params = useParams();
  const sessionId = (params?.sessionId as string) ?? "";

  const [data, setData] = useState<StoryDnaFinalizeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        // /finalize is idempotent — re-calling on a finalized session
        // returns the cached profile + concepts.
        const result = await finalizeStoryDna(sessionId);
        if (!cancelled) {
          setData(result);
          setLoading(false);
        }
      } catch (e) {
        if (!cancelled) {
          const msg = e instanceof Error ? e.message : "Could not load your DNA.";
          setError(msg);
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const handlePickConcept = (conceptId: string) => {
    // Stash the pending session for the post-signup migration handler.
    sessionStorage.setItem("pending_dna_session_id", sessionId);
    sessionStorage.setItem("pending_dna_concept_id", conceptId);
    router.push(`/signup?session_id=${sessionId}&concept_id=${conceptId}`);
  };

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-foreground/70">Generating your Story DNA…</p>
      </main>
    );
  }

  if (error || !data) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center px-6">
        <p className="mb-4 text-red-500">{error || "Could not load your DNA."}</p>
        <button
          onClick={() => router.push("/story-dna")}
          className="rounded-lg bg-foreground px-6 py-3 text-background font-medium"
        >
          Retake the test
        </button>
      </main>
    );
  }

  const profile = data.story_dna_profile;

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="text-4xl font-bold mb-2">Your Story DNA</h1>
      <p className="text-foreground/70 mb-10">
        Here&apos;s what we read in your answers — and 3 to 5 stories built for
        the way you think.
      </p>

      <section className="mb-12 space-y-6">
        {profile.genre_sweet_spot && (
          <div>
            <h2 className="text-sm uppercase tracking-wide text-foreground/50 mb-1">
              Genre sweet spot
            </h2>
            <p>{profile.genre_sweet_spot}</p>
          </div>
        )}
        {profile.thematic_obsessions && profile.thematic_obsessions.length > 0 && (
          <div>
            <h2 className="text-sm uppercase tracking-wide text-foreground/50 mb-1">
              Thematic obsessions
            </h2>
            <div className="flex flex-wrap gap-2">
              {profile.thematic_obsessions.map((t, i) => (
                <span
                  key={i}
                  className="rounded-full bg-foreground/10 px-3 py-1 text-sm"
                >
                  {t}
                </span>
              ))}
            </div>
          </div>
        )}
        {profile.character_instincts && (
          <div>
            <h2 className="text-sm uppercase tracking-wide text-foreground/50 mb-1">
              Character instincts
            </h2>
            <p>{profile.character_instincts}</p>
          </div>
        )}
        {profile.world_building_style && (
          <div>
            <h2 className="text-sm uppercase tracking-wide text-foreground/50 mb-1">
              World-building style
            </h2>
            <p>{profile.world_building_style}</p>
          </div>
        )}
        {profile.anti_preferences && profile.anti_preferences.length > 0 && (
          <div>
            <h2 className="text-sm uppercase tracking-wide text-foreground/50 mb-1">
              You refuse
            </h2>
            <ul className="list-disc list-inside space-y-1">
              {profile.anti_preferences.map((a, i) => (
                <li key={i}>{a}</li>
              ))}
            </ul>
          </div>
        )}
        {profile.influences_decoded && (
          <div>
            <h2 className="text-sm uppercase tracking-wide text-foreground/50 mb-1">
              Your influences, decoded
            </h2>
            <p>{profile.influences_decoded}</p>
          </div>
        )}
      </section>

      <section>
        <h2 className="text-2xl font-bold mb-6">Stories built for you</h2>
        <div className="space-y-6">
          {data.concepts.map((concept) => (
            <div
              key={concept.concept_id}
              className="rounded-lg border border-foreground/10 p-6"
            >
              <div className="flex items-baseline justify-between gap-4 mb-2">
                <h3 className="text-xl font-semibold">
                  {concept.working_title}
                </h3>
                <span className="text-xs text-foreground/50">
                  {concept.genre}
                </span>
              </div>
              <p className="text-foreground/80 italic mb-3">{concept.hook}</p>
              <p className="mb-3 text-sm">{concept.premise}</p>
              <p className="text-xs text-foreground/60 mb-4">
                <strong>Why this fits your DNA:</strong>{" "}
                {concept.why_this_fits_your_dna}
              </p>
              <button
                onClick={() => handlePickConcept(concept.concept_id)}
                className="rounded-lg bg-foreground px-5 py-2 text-background text-sm font-medium hover:opacity-90 transition-opacity"
              >
                Build this into a novel →
              </button>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
