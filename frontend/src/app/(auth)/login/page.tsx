"use client";

import { createClient } from "@/lib/supabase/client";

export default function LoginPage() {
  const handleGoogleLogin = async () => {
    const supabase = createClient();
    await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${window.location.origin}/callback`,
      },
    });
  };

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <div className="max-w-md w-full text-center">
        <h1 className="mb-2 text-3xl font-bold tracking-tight">
          Welcome to BUB Writer
        </h1>
        <p className="mb-8 text-foreground/70">
          Sign in to discover your literary voice.
        </p>
        <button
          onClick={handleGoogleLogin}
          className="w-full rounded-lg bg-foreground px-6 py-3 text-background font-medium hover:opacity-90 transition-opacity"
        >
          Continue with Google
        </button>
      </div>
    </main>
  );
}
