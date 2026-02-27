"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

export default function AuthCallbackPage() {
  const router = useRouter();

  useEffect(() => {
    const supabase = createClient();

    supabase.auth.onAuthStateChange((event) => {
      if (event === "SIGNED_IN") {
        router.replace("/dashboard");
      }
    });
  }, [router]);

  return (
    <main className="flex min-h-screen items-center justify-center">
      <p className="text-foreground/70">Completing sign in...</p>
    </main>
  );
}
