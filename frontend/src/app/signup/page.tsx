"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

function SignupContent() {
  const searchParams = useSearchParams();
  const [pendingConcept, setPendingConcept] = useState(false);

  // Persist pending DNA context across the OAuth roundtrip via sessionStorage.
  // The /callback page reads these after SIGNED_IN to migrate + create-project.
  useEffect(() => {
    const sessionId = searchParams?.get("session_id");
    const conceptId = searchParams?.get("concept_id");
    if (sessionId && conceptId) {
      sessionStorage.setItem("pending_dna_session_id", sessionId);
      sessionStorage.setItem("pending_dna_concept_id", conceptId);
      setPendingConcept(true);
    } else if (
      sessionStorage.getItem("pending_dna_session_id") &&
      sessionStorage.getItem("pending_dna_concept_id")
    ) {
      setPendingConcept(true);
    }
  }, [searchParams]);

  const handleGoogleSignup = async () => {
    const supabase = createClient();
    await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${window.location.origin}/callback`,
      },
    });
  };

  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-6 py-16">
      <div className="max-w-md w-full text-center">
        <h1 className="text-3xl font-bold tracking-tight mb-2">
          {pendingConcept
            ? "Sign up to build your novel"
            : "Sign up for BUB Writer"}
        </h1>
        <p className="mb-8 text-foreground/70">
          {pendingConcept
            ? "Your Story DNA and chosen concept are ready — sign up and we'll set up your project."
            : "Create an account to start writing with BUB Writer."}
        </p>
        <button
          onClick={handleGoogleSignup}
          className="w-full rounded-lg bg-foreground px-6 py-3 text-background font-medium hover:opacity-90 transition-opacity"
        >
          Continue with Google
        </button>
      </div>
    </main>
  );
}

export default function SignupPage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center">
          <p className="text-foreground/70">Loading…</p>
        </main>
      }
    >
      <SignupContent />
    </Suspense>
  );
}
