"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function WritePageFallback() {
  const router = useRouter();

  useEffect(() => {
    // No project selected — redirect to project list
    router.replace("/dashboard");
  }, [router]);

  return (
    <div className="flex items-center justify-center py-20 bg-zinc-950 min-h-screen">
      <p className="text-zinc-500 text-sm">
        No project selected. Redirecting...
      </p>
    </div>
  );
}
