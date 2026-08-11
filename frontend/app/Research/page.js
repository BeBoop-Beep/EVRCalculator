import Link from "next/link";

export const metadata = {
  title: "Research & Methodology — inDex",
  description: "How inDex calculates RIP Score, Financial RIP, Collector Appeal, and modeled Pokémon opening outcomes.",
};

const FINANCIAL_COMPONENTS = [
  ["True Win Frequency", "How often a modeled opening returns at least the current pack cost."],
  ["Typical Retention", "How much of pack cost the median modeled opening retains."],
  ["Loss Resilience", "How much losing openings return and how often those losses are near-misses rather than hard losses."],
  ["Realistic Upside", "The quality of good-but-not-miraculous outcomes below the exceptional jackpot tail."],
  ["Jackpot Upside", "The exceptional top 1% of modeled outcomes, controlled so one enormous chase cannot dominate the score."],
  ["Base Economic Efficiency", "Average return relative to cost after excluding the top 1%, keeping ordinary opening economics visible."],
];

const OUTCOME_METRICS = [
  ["Expected Value", "The arithmetic mean value across all modeled openings. It describes a long-run average, not the most likely single-pack result."],
  ["Typical Opening", "The median, or P50. Half of modeled openings finish below this value and half finish above it."],
  ["Strong Upside", "The P95 threshold: the value where the strongest 5% of modeled openings begins."],
  ["Jackpot Upside", "The P99 threshold: the value where the top 1% of modeled openings begins."],
];

function Section({ eyebrow, title, children }) {
  return (
    <section className="set-glass-surface rounded-2xl border p-5 sm:p-6">
      <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[var(--accent)]">{eyebrow}</p>
      <h2 className="mt-1 text-xl font-semibold tracking-tight text-[var(--text-primary)] sm:text-2xl">{title}</h2>
      <div className="mt-3 space-y-3 text-sm leading-6 text-[var(--text-secondary)]">{children}</div>
    </section>
  );
}

export default function ResearchPage() {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 pb-24 pt-8 sm:px-6 lg:px-8">
      <header className="mx-auto max-w-3xl text-center">
        <p className="text-xs font-bold uppercase tracking-[0.2em] text-[var(--accent)]">inDex methodology</p>
        <h1 className="mt-3 text-4xl font-semibold tracking-tight text-[var(--text-primary)] sm:text-5xl">Research</h1>
        <p className="mt-4 text-base leading-7 text-[var(--text-secondary)] sm:text-lg">inDex combines modeled opening economics with collector-oriented set structure to answer one question: what Pokémon set is worth ripping right now?</p>
      </header>

      <div className="mt-10 space-y-5">
        <Section eyebrow="The headline score" title="RIP Score">
          <p>RIP Score combines <strong className="text-[var(--text-primary)]">Financial RIP</strong> with <strong className="text-[var(--text-primary)]">Collector Appeal</strong>. Financial RIP measures the modeled outcome profile relative to pack cost; Collector Appeal measures whether the set&apos;s desirable roster and opening structure make those outcomes compelling to collectors.</p>
          <p>The public RIP Score is the set&apos;s cohort-relative position on a 0–100 scale. The strongest eligible set in the current comparison group is 100. This relative score is a presentation of position, not the underlying absolute model score, and can move when the eligible cohort changes.</p>
        </Section>

        <Section eyebrow="Opening economics" title="Financial RIP">
          <p>Financial RIP combines several dimensions of opening economics derived from simulated outcome values and pack cost. These include normal outcomes, downside protection, win frequency, upside, and economic efficiency.</p>
          <dl className="grid gap-3 sm:grid-cols-2">
            {FINANCIAL_COMPONENTS.map(([name, description]) => <div key={name} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 p-4"><dt className="font-semibold text-[var(--text-primary)]">{name}</dt><dd className="mt-1 text-sm leading-5">{description}</dd></div>)}
          </dl>
          <p>Missing required inputs make Financial RIP unavailable; missing data is not replaced with a neutral score.</p>
        </Section>

        <Section eyebrow="Collector structure" title="Collector Appeal">
          <p>Collector Appeal uses three canonical, price-independent factors:</p>
          <ul className="grid gap-3 sm:grid-cols-3">
            <li className="rounded-xl border border-[var(--border-subtle)] p-4"><strong className="block text-[var(--text-primary)]">Roster desirability</strong><span>How compelling the Pokémon and cards represented in the set are to collectors.</span></li>
            <li className="rounded-xl border border-[var(--border-subtle)] p-4"><strong className="block text-[var(--text-primary)]">Desirable outcome frequency</strong><span>How often the modeled pack delivers a desirable card.</span></li>
            <li className="rounded-xl border border-[var(--border-subtle)] p-4"><strong className="block text-[var(--text-primary)]">Dual-path depth</strong><span>Whether desirable subjects offer both an attainable printing and a genuine elite chase.</span></li>
          </ul>
          <p>Collector Appeal does not read card prices, Expected Value, pack cost, profitability, or another market proxy. A missing required factor makes the score unavailable rather than substituting zero or a fallback.</p>
        </Section>

        <Section eyebrow="Modeled openings" title="Opening simulation">
          <p>inDex models possible pack outcomes using the set&apos;s configured pack structure, card pools, modeled pull-rate assumptions, and current market values. The resulting distribution powers the outcome metrics and Financial RIP inputs; it is not a prediction for a particular pack.</p>
          <dl className="grid gap-3 sm:grid-cols-2">
            {OUTCOME_METRICS.map(([name, description]) => <div key={name} className="rounded-xl border border-[var(--border-subtle)] p-4"><dt className="font-semibold text-[var(--text-primary)]">{name}</dt><dd className="mt-1">{description}</dd></div>)}
          </dl>
          <p>Set pages disclose the modeled pull-rate inputs and assumptions available for that set. These are inDex modeling assumptions and should not be presented as official Pokémon pull rates.</p>
        </Section>

        <Section eyebrow="Use responsibly" title="Limitations & interpretation">
          <ul className="list-disc space-y-2 pl-5 marker:text-[var(--accent)]">
            <li>A high relative RIP Score means a set compares strongly with the current eligible cohort; it does not promise absolute profitability.</li>
            <li>Market prices, eligible sets, modeled inputs, and data coverage change. Scores and ranks can change when those inputs change.</li>
            <li>Expected Value is a long-run average and can be heavily influenced by rare outcomes. Typical Opening is often more representative of one opening.</li>
            <li>Simulation results are modeled estimates, not guarantees, forecasts, financial advice, or official Pokémon pull-rate statements.</li>
          </ul>
        </Section>
      </div>

      <div className="mt-8 flex flex-wrap justify-center gap-3">
        <Link href="/Rankings" className="inline-flex min-h-11 items-center rounded-xl bg-[var(--accent)] px-5 py-2.5 text-sm font-semibold text-[var(--surface-page)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]">View Rankings</Link>
        <Link href="/Market" className="inline-flex min-h-11 items-center rounded-xl border border-[var(--border-subtle)] px-5 py-2.5 text-sm font-semibold text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]">View Market</Link>
      </div>
    </div>
  );
}
