import Link from "next/link";

export default function LandingPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-6 py-16">
      <div className="max-w-2xl text-center">
        <h1 className="text-5xl font-bold tracking-tight mb-6">
          What kind of stories live in you?
        </h1>
        <p className="text-xl text-foreground/70 mb-10">
          Take a 2-minute test and discover the stories you&apos;re built to tell —
          then build one into a novel with BUB Writer.
        </p>
        <Link
          href="/story-dna"
          className="inline-block rounded-lg bg-foreground px-8 py-4 text-background text-lg font-medium hover:opacity-90 transition-opacity"
        >
          Take the Story DNA test
        </Link>
        <div className="mt-12 flex justify-center gap-6 text-sm text-foreground/60">
          <Link href="/login" className="hover:text-foreground">
            Sign in
          </Link>
        </div>
      </div>
    </main>
  );
}
