"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { migrateStoryDnaSession, createProjectFromDna } from "@/lib/api";

export default function AuthCallbackPage() {
  const router = useRouter();
  const [statusMessage, setStatusMessage] = useState("Completing sign in…");

  useEffect(() => {
    const supabase = createClient();

    const handleSignedIn = async () => {
      const sessionId = sessionStorage.getItem("pending_dna_session_id");
      const conceptId = sessionStorage.getItem("pending_dna_concept_id");

      if (!sessionId || !conceptId) {
        router.replace("/dashboard");
        return;
      }

      // Always clear the pending state — even on failure — so the user
      // doesn't get stuck in a loop on the next sign-in.
      sessionStorage.removeItem("pending_dna_session_id");
      sessionStorage.removeItem("pending_dna_concept_id");

      try {
        setStatusMessage("Saving your Story DNA…");
        const migrate = await migrateStoryDnaSession(sessionId);

        setStatusMessage("Setting up your project…");
        const created = await createProjectFromDna({
          dna_profile_id: migrate.dna_profile_id,
          concept_id: conceptId,
        });

        router.replace(`/brainstorm/${created.project_id}`);
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Could not finish setup.";
        // 404 from migrate-session = expired anonymous session
        if (msg.toLowerCase().includes("expired") || msg.toLowerCase().includes("not found")) {
          setStatusMessage(
            "Your Story DNA session expired. Redirecting you to retake the test…"
          );
          setTimeout(() => router.replace("/story-dna"), 2000);
          return;
        }
        setStatusMessage(msg);
        setTimeout(() => router.replace("/dashboard"), 2000);
      }
    };

    const { data: subscription } = supabase.auth.onAuthStateChange((event) => {
      if (event === "SIGNED_IN") {
        handleSignedIn();
      }
    });

    // Also handle the case where the user is already signed in when this
    // page loads (e.g., re-entering /callback after the auth fragment was
    // already processed).
    supabase.auth.getSession().then(({ data }) => {
      if (data.session) {
        handleSignedIn();
      }
    });

    return () => {
      subscription.subscription.unsubscribe();
    };
  }, [router]);

  return (
    <main className="flex min-h-screen items-center justify-center">
      <p className="text-foreground/70">{statusMessage}</p>
    </main>
  );
}
