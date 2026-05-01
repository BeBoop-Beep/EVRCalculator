import Link from "next/link";

const TOPICS = [
  {
    title: "RIP Statistics",
    description:
      "Understand pack-opening outcomes, Pack Score, profit potential, safety, stability, hit rates, and risk.",
    cta: "View RIP Statistics",
    href: "/Explore/rip-statistics",
    imageAlt: "Preview of RIP Statistics analytics dashboard",
    artType: "rip-statistics",
  },
  {
    title: "Top 10",
    description:
      "Explore the strongest rankings across sets, cards, pack scores, market value, and chase potential.",
    cta: "Preview Top 10",
    href: "/Explore/top-10",
    imageAlt: "Leaderboard preview for Top 10 explore rankings",
    artType: "top-10",
  },
];

function RipStatisticsCardArt() {
  return (
    <div className="relative h-full w-full bg-[radial-gradient(circle_at_top,_rgba(36,60,88,0.35)_0%,_rgba(9,14,22,0.95)_62%)]">
      <div className="absolute inset-0 opacity-40 [background-image:linear-gradient(rgba(255,255,255,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.05)_1px,transparent_1px)] [background-size:22px_22px]" />

      <div className="relative z-10 flex h-full gap-3 p-3 sm:p-4">
        <div className="flex w-[36%] flex-col gap-2 rounded-lg border border-white/10 bg-black/35 p-2.5">
          <span className="text-[10px] uppercase tracking-[0.1em] text-white/65">Pack Score</span>
          <div className="text-3xl font-semibold leading-none text-white sm:text-4xl">64</div>
          <span className="inline-flex w-fit rounded-full border border-emerald-300/35 bg-emerald-400/15 px-2 py-0.5 text-[10px] font-medium text-emerald-200">
            Rank A
          </span>
        </div>

        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <div className="grid grid-cols-3 gap-2">
            <div className="rounded-md border border-white/10 bg-black/30 p-1.5">
              <div className="h-9 w-full rounded bg-emerald-300/70" />
            </div>
            <div className="rounded-md border border-white/10 bg-black/30 p-1.5">
              <div className="h-9 w-full rounded bg-sky-300/65" />
            </div>
            <div className="rounded-md border border-white/10 bg-black/30 p-1.5">
              <div className="h-9 w-full rounded bg-amber-300/65" />
            </div>
          </div>

          <div className="flex min-h-0 flex-1 items-end gap-1 rounded-md border border-white/10 bg-black/30 px-2 pb-2 pt-3">
            <div className="h-[22%] w-2 rounded-sm bg-slate-200/65" />
            <div className="h-[36%] w-2 rounded-sm bg-slate-200/65" />
            <div className="h-[50%] w-2 rounded-sm bg-slate-200/70" />
            <div className="h-[62%] w-2 rounded-sm bg-slate-100/75" />
            <div className="h-[74%] w-2 rounded-sm bg-white/80" />
            <div className="h-[58%] w-2 rounded-sm bg-slate-100/75" />
            <div className="h-[43%] w-2 rounded-sm bg-slate-200/70" />
            <div className="h-[29%] w-2 rounded-sm bg-slate-200/65" />
          </div>
        </div>
      </div>
    </div>
  );
}

function TopTenCardArt() {
  const rows = [
    {
      rank: "#1",
      nameWidth: "w-[84%]",
      subWidth: "w-[56%]",
      value: "9.8",
      valueTone: "border-emerald-300/45 bg-emerald-300/20 text-emerald-100",
      highlight: true,
    },
    {
      rank: "#2",
      nameWidth: "w-[74%]",
      subWidth: "w-[48%]",
      value: "9.3",
      valueTone: "border-amber-300/45 bg-amber-300/18 text-amber-100",
    },
    {
      rank: "#3",
      nameWidth: "w-[69%]",
      subWidth: "w-[45%]",
      value: "8.9",
      valueTone: "border-sky-300/45 bg-sky-300/20 text-sky-100",
    },
    {
      rank: "#4",
      nameWidth: "w-[62%]",
      subWidth: "w-[40%]",
      value: "8.2",
      valueTone: "border-slate-300/35 bg-slate-300/15 text-slate-100",
    },
    {
      rank: "#5",
      nameWidth: "w-[57%]",
      subWidth: "w-[36%]",
      value: "7.7",
      valueTone: "border-rose-300/40 bg-rose-300/18 text-rose-100",
    },
  ];

  return (
    <div className="relative h-full w-full bg-[radial-gradient(circle_at_20%_0%,_rgba(34,64,102,0.38)_0%,_rgba(9,14,22,0.96)_58%)]">
      <div className="absolute inset-0 opacity-35 [background-image:linear-gradient(rgba(255,255,255,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.05)_1px,transparent_1px)] [background-size:24px_24px]" />

      <div className="relative z-10 h-full p-3 sm:p-4">
        <div className="flex h-full flex-col overflow-hidden rounded-lg border border-white/10 bg-[linear-gradient(180deg,rgba(14,24,38,0.96)_0%,rgba(10,17,28,0.96)_100%)] shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]">
          <div className="flex items-center justify-between border-b border-white/10 px-3 py-2 sm:px-3.5">
            <div className="h-1.5 w-20 rounded-full bg-white/10" />
            <div className="rounded-full border border-sky-300/35 bg-sky-300/15 px-2 py-0.5 text-[10px] font-semibold text-sky-100">
              Top Rankings
            </div>
          </div>

          <div className="flex min-h-0 flex-1 flex-col gap-1.5 p-2 sm:gap-2 sm:p-2.5">
            {rows.map((row) => (
              <div
                key={row.rank}
                className={`grid grid-cols-[auto_1fr_auto] items-center gap-2 rounded-md border px-2 py-1.5 sm:gap-2.5 sm:px-2.5 ${
                  row.highlight ? "border-white/16 bg-white/10" : "border-white/8 bg-white/[0.04]"
                }`}
              >
                <span className="inline-flex h-5 min-w-9 items-center justify-center rounded-full border border-white/15 bg-white/[0.08] px-2 text-[10px] font-semibold text-white/90 sm:text-[11px]">
                  {row.rank}
                </span>

                <div className="min-w-0 space-y-1">
                  <div className={`h-2 rounded-full bg-white/45 ${row.nameWidth}`} />
                  <div className={`h-1.5 rounded-full bg-white/20 ${row.subWidth}`} />
                </div>

                <span
                  className={`inline-flex min-w-11 items-center justify-center rounded-md border px-1.5 py-0.5 text-[10px] font-semibold ${row.valueTone}`}
                >
                  {row.value}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

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
              <div
                className="relative mb-5 overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] aspect-[16/9]"
                role="img"
                aria-label={topic.imageAlt}
              >
                {topic.artType === "rip-statistics" ? <RipStatisticsCardArt /> : <TopTenCardArt />}
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
