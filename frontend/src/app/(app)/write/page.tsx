"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function WritePage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/dashboard");
  }, [router]);

  return (
    <div className="flex items-center justify-center py-20">
      <p className="text-zinc-500 text-sm">Redirecting to Projects...</p>
    </div>
  );
}
