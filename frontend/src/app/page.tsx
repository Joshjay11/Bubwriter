import Link from "next/link";

export default function LandingPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <div className="max-w-2xl text-center">
        <h1 className="mb-4 text-5xl font-bold tracking-tight">BUB Writer</h1>
        <p className="mb-8 text-xl text-foreground/70">
          Discover your unique literary voice. Write fiction that sounds like
          you.
        </p>
        <div className="flex gap-4 justify-center">
          <Link
            href="/login"
            className="rounded-lg bg-foreground px-6 py-3 text-background font-medium hover:opacity-90 transition-opacity"
          >
            Get Started
          </Link>
          <Link
            href="/analyze"
            className="rounded-lg border border-foreground/20 px-6 py-3 font-medium hover:bg-foreground/5 transition-colors"
          >
            Try DNA Analyzer
          </Link>
        </div>
      </div>
    </main>
  );
}
