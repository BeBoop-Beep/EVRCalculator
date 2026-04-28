import Image from "next/image";
import Link from "next/link";

const TOPICS = [
  {
    title: "Top 10",
    description:
      "Explore the strongest rankings across sets, cards, pack scores, market value, and chase potential.",
    cta: "View Top 10",
    href: "/Explore/top-10",
    imageSrc: "/images/explore/top-10.svg",
    imageAlt: "Leaderboard preview for Top 10 explore rankings",
  },
  {
    title: "RIP Statistics",
    description:
      "Understand pack-opening outcomes, Pack Score, profit potential, safety, stability, hit rates, and risk.",
    cta: "View RIP Statistics",
    href: "/Explore/rip-statistics",
    imageSrc: "/images/explore/rip-statistics.svg",
    imageAlt: "Distribution chart preview for RIP Statistics",
  },
];

export default function ExplorePage() {
  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="dashboard-container space-y-6">
        <section className="page-hero-panel rounded-2xl px-6 py-7">
          <div>
            <h1 className="text-2xl font-semibold text-[var(--text-primary)]">Explore</h1>
            <p className="mt-2 text-sm text-[var(--text-secondary)]">
              Discover rankings, trends, and pack-ripping analytics.
            </p>
          </div>
        </section>

        <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {TOPICS.map((topic) => (
            <article
              key={topic.href}
              className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-5 sm:p-6"
            >
              <div className="relative mb-5 overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] aspect-[16/9]">
                <Image
                  src={topic.imageSrc}
                  alt={topic.imageAlt}
                  fill
                  className="object-cover"
                  sizes="(max-width: 768px) 100vw, 50vw"
                />
              </div>
              <h2 className="text-xl font-semibold text-[var(--text-primary)]">{topic.title}</h2>
              <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">{topic.description}</p>

              <div className="mt-5">
                <Link
                  href={topic.href}
                  className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-4 py-2 text-sm font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-hover)]"
                >
                  {topic.cta}
                  <span aria-hidden="true">→</span>
                </Link>
              </div>
            </article>
          ))}
        </section>
      </div>
    </main>
  );
}
