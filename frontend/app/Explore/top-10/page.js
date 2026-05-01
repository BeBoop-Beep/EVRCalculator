import Link from "next/link";

export default function ExploreTop10PlaceholderPage() {
  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="dashboard-container">
        <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-6 py-8 sm:px-8 sm:py-10">
          <div className="mx-auto max-w-2xl text-center">
            <p className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-1 text-xs font-medium uppercase tracking-[0.08em] text-[var(--text-secondary)]">
              Explore Preview
            </p>
            <h1 className="mt-5 text-3xl font-semibold text-[var(--text-primary)] sm:text-4xl">
              Top 10 is coming soon
            </h1>
            <p className="mt-4 text-sm leading-relaxed text-[var(--text-secondary)] sm:text-base">
              We&rsquo;re building ranked views for the strongest sets, cards, Pack Scores, market value, and chase potential.
            </p>

            <div className="mt-8">
              <Link
                href="/Explore"
                className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-4 py-2 text-sm font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-hover)]"
              >
                Back to Explore
              </Link>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
