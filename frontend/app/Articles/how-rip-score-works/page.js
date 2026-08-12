import Link from "next/link";
import { buildRouteMetadata } from "@/lib/seo/routeMetadata.mjs";

// Descriptive only. This must never name a production weight, a blend split or
// a formula — the page itself deliberately withholds them, and metadata is the
// most widely republished text on the site.
//
// NAMING: "Overall RIP" is the public name of the headline metric. It is the
// name this page uses throughout, and articlesRoutes.contract.test.mjs asserts
// that the retired label does not appear anywhere in this file — metadata
// included, which is why the wording below matches the page copy exactly.
//
// ROUTE HISTORY: this content shipped at /Research, which was a top-level
// product section. Articles is now the content destination and methodology is
// an article inside it. /Research is a permanent redirect to this URL
// (next.config.mjs) so there is exactly ONE indexable copy.
export const metadata = buildRouteMetadata({
  path: "/Articles/how-rip-score-works",
  title: "How the RIP Score Works — inDex",
  description:
    "Why Expected Value alone was not enough to rank Pokémon sets, what Overall RIP measures instead, and what the one million opening simulation behind it can and cannot tell you.",
  ogTitle: "How the RIP Score Works",
});

const FINANCIAL_COMPONENTS = [
  ["True Win Frequency", "How often a modeled opening returns at least the current pack cost."],
  ["Typical Retention", "How much of pack cost the median modeled opening retains."],
  ["Loss Resilience", "How much losing openings return, and how often those losses are near-misses rather than hard losses."],
  ["Strong Upside Quality", "The quality of the strongest 5% of modeled outcomes, after excluding the exceptional top 1% jackpot tail."],
  ["Jackpot Upside", "That exceptional top 1%, controlled so one enormous chase cannot dominate the score."],
  ["Base Economic Efficiency", "Average return relative to cost with the top 1% excluded, which keeps ordinary opening economics visible."],
];

const OUTCOME_METRICS = [
  ["Expected Value", "The arithmetic mean across every modeled opening. It describes a long-run average, not the result you are most likely to get from one pack."],
  ["Typical Opening", "The median, or P50. Half of the modeled openings finished below this and half finished above it."],
  ["Strong Upside", "The P95 threshold, which is where the strongest 5% of modeled openings begins."],
  ["Jackpot Upside", "The P99 threshold, which is where the top 1% begins."],
];

function DefinitionGrid({ items, columns = "sm:grid-cols-2" }) {
  return (
    <dl className={`mt-5 grid gap-3 ${columns}`}>
      {items.map(([name, description]) => (
        <div key={name} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 p-4">
          <dt className="font-semibold text-[var(--text-primary)]">{name}</dt>
          <dd className="mt-1 text-sm leading-6">{description}</dd>
        </div>
      ))}
    </dl>
  );
}

function Heading({ children }) {
  return (
    <h2 className="mt-12 text-2xl font-semibold tracking-tight text-[var(--text-primary)] sm:text-3xl">{children}</h2>
  );
}

export default function HowRipScoreWorksArticle() {
  return (
    <article className="mx-auto w-full max-w-3xl px-4 pb-24 pt-8 sm:px-6 lg:px-8">
      <header>
        <p className="text-xs font-bold uppercase tracking-[0.2em] text-[var(--accent)]">Methodology</p>
        <h1 className="mt-3 text-4xl font-semibold tracking-tight text-[var(--text-primary)] sm:text-5xl">
          How the RIP Score Works
        </h1>
      </header>

      <div className="mt-8 space-y-5 text-[15px] leading-7 text-[var(--text-secondary)]">
        <p>
          Expected Value was the first thing I calculated when I started building the opening simulator, because it is
          the obvious way to measure a pack financially. It was also the first thing that showed me why EV on its own
          was not going to be enough.
        </p>
        <p>
          The problem is that two sets can land on nearly the same EV and still be completely different to open. Imagine
          a $5 pack with a $4 EV where almost all of that value is sitting in one card you will realistically never
          pull. Now imagine another $5 pack, also $4 EV, where the value is spread across hits you actually hit. Those
          two packs have the same average return. I would not call them the same opening, and if inDex is going to tell
          you which set is worth ripping, it cannot treat them as equivalent.
        </p>
        <p>
          So the question becomes: what else do you have to measure, and how do you combine it into one number without
          the number quietly becoming meaningless? That is what Overall RIP is, and this is what is underneath it.
        </p>

        <Heading>Overall RIP</Heading>
        <p>
          Overall RIP combines <strong className="text-[var(--text-primary)]">Financial RIP</strong>, which measures the
          modeled outcome profile relative to what the pack costs, with{" "}
          <strong className="text-[var(--text-primary)]">Collector Appeal</strong>, which measures whether the set&apos;s
          roster and opening structure make those outcomes something a collector actually wants. The financial side
          answers whether the math works. The collector side answers whether you care.
        </p>
        <p>
          The score you see is on a 0 to 100 scale, and that scale is relative rather than absolute. The strongest
          eligible set in the current comparison group is 100, and everything else is positioned against it. What I
          actually care about here is ordering: given the sets that are in front of you right now, which one is the
          better rip.
        </p>
        <p>
          What this does not mean is that a high score promises you will make money. A set scoring 92 is telling you it
          compares strongly against the current eligible cohort, and nothing more than that. Because the score is
          cohort-relative, it can also move without the set itself changing. If a stronger set becomes eligible, or an
          existing one drops out, everything around it shifts. That is the tradeoff you accept for a score that stays
          interpretable as the market moves, and I would rather be explicit about it than let people read 92 as a
          guarantee.
        </p>
        <p>
          The number on the page is also a presentation of position, not the raw model output the ranking is computed
          from. Those are deliberately different things.
        </p>

        <Heading>Financial RIP</Heading>
        <p>
          Financial RIP is where the EV problem gets solved. Instead of collapsing the simulated distribution into one
          average, it reads several different properties of that distribution against pack cost, so that a set which
          hides all of its value in one unreachable card cannot look the same as a set that spreads it out.
        </p>
        <DefinitionGrid items={FINANCIAL_COMPONENTS} />
        <p>
          The top 1% shows up twice on purpose, once included and once excluded. A single enormous chase card can drag
          an average upward far enough to describe an opening almost nobody experiences, so I wanted the jackpot tail
          measured as its own thing rather than smeared across everything else. Separating it means a set with a
          spectacular chase still gets credit for it without that chase deciding the whole score.
        </p>
        <p>
          If a required input is missing, Financial RIP comes back unavailable. It does not get a neutral score. Filling
          a gap with a middle value sounds harmless, but it produces a set that looks mediocre when the truth is we do
          not know, and those two things should not render identically.
        </p>

        <Heading>Collector Appeal</Heading>
        <p>
          Collector Appeal exists because the financial model cannot see the part of opening that is not financial. It
          uses three canonical factors, and all of them are price-independent:
        </p>
        <ul className="mt-5 grid gap-3 sm:grid-cols-3">
          <li className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 p-4">
            <strong className="block text-[var(--text-primary)]">Roster desirability</strong>
            <span className="mt-1 block text-sm leading-6">How compelling the Pokémon and cards in the set are to collectors.</span>
          </li>
          <li className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 p-4">
            <strong className="block text-[var(--text-primary)]">Desirable outcome frequency</strong>
            <span className="mt-1 block text-sm leading-6">How often the modeled pack actually delivers a desirable card.</span>
          </li>
          <li className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 p-4">
            <strong className="block text-[var(--text-primary)]">Dual-path depth</strong>
            <span className="mt-1 block text-sm leading-6">Whether desirable subjects offer both an attainable printing and a genuine elite chase.</span>
          </li>
        </ul>
        <p>
          Price-independent is the important part, and it was a constraint I had to enforce rather than assume. Collector
          Appeal does not read card prices, Expected Value, pack cost, profitability, or any other market proxy. The
          moment it does, it stops being a second opinion and turns into Financial RIP wearing a different label, which
          means combining the two would just be double-counting the same signal. As with the financial side, a missing
          required factor makes the score unavailable rather than substituting a zero or a fallback.
        </p>

        <Heading>The simulation</Heading>
        <p>
          Everything above needs a distribution to read, and that comes from running one million modeled openings per
          supported set. Each run uses the set&apos;s configured pack structure, its card pools, the modeled pull-rate
          assumptions, and current market values, and the resulting distribution is what the outcome metrics and the
          Financial RIP inputs are computed from.
        </p>
        <DefinitionGrid items={OUTCOME_METRICS} />
        <p>
          A million runs is about sampling error, and nothing else. It gets the tail percentiles stable enough that P99
          does not swing around between runs and reorder the rankings for no reason. It does not make the pull-rate
          assumptions correct. If the model going in is wrong, running it more times gives you a more precise version of
          the wrong answer, which is arguably worse because precision reads as confidence.
        </p>
        <p>
          That is also why the wording on set pages matters to me. Set pages disclose the modeled pull-rate inputs and
          assumptions available for that set, and they are described as modeled inputs because that is what they are.
          They are inDex modeling assumptions and should not be read as official Pokémon pull rates, which are not
          something we have.
        </p>
        <p>
          The other thing the simulation is not doing is predicting your pack. It describes the range of things that
          could happen across a million openings. Any single pack is one draw from that range, and the distribution is
          wide on purpose, because that is what opening packs is actually like.
        </p>

        <Heading>Where the numbers come from</Heading>
        <p>
          Card catalogs, card values, and sealed-product market observations come from the TCGplayer data paths inDex
          records. Set configuration supplies the pack structure and the modeled rarity and pull-rate assumptions the
          simulator runs on. Every public result is tied to a stored calculation snapshot rather than computed live, so
          the number you are looking at came from a specific run against specific inputs, and pricing dates and
          available pull-rate assumptions are shown on the relevant set surfaces wherever the payload provides them.
        </p>
        <p>
          Coverage is uneven, and I would rather show that than paper over it. A set without the required simulation and
          scoring inputs stays unsupported. It is not given substitute outcomes, and it is not given a rank.
        </p>

        <Heading>What this does not account for</Heading>
        <p>
          A few limitations are worth stating directly rather than leaving in the footer.
        </p>
        <p>
          The first is liquidity. A displayed card value is a market observation, not an offer, and it is not a promise
          that you can sell at that price today or at all. Thin markets are exactly where that gap is widest, and thin
          markets are common for the high-value cards doing the most work in a set&apos;s upside.
        </p>
        <p>
          The second is that transaction costs are not guaranteed to be reflected in displayed card values. Seller fees,
          taxes, shipping, and grading all sit between a modeled outcome and money in your hand, and they are not
          uniform across sellers or regions, so the modeled return is best read as a ceiling on what you would realize
          rather than the realized figure itself.
        </p>
        <p>
          The third is drift. Market prices change, the eligible cohort changes, modeled inputs get revised, and data
          coverage expands. Scores and ranks move when those inputs move, which is intended behavior and not a bug, but
          it does mean a score is a statement about a moment rather than a permanent property of a set.
        </p>
        <p>
          And the one people trip on most often: Expected Value is a long-run average and rare outcomes pull it hard.
          Typical Opening is usually the more honest number for a single rip, which is why both are on the page instead
          of just the one that looks better.
        </p>
        <p>
          None of this is financial advice, and none of it is a forecast. It is a model, with the assumptions stated.
        </p>

        <Heading>Why the score is built this way</Heading>
        <p>
          I still show EV prominently, because it is a real number and it answers a real question. I just do not think
          it should be the only number deciding which pack is best to open, and once I accepted that, the rest of this
          followed: measure more than the average, keep the collector side from secretly re-reading prices, run enough
          simulations that the tails hold still, and refuse to score a set when the inputs are not there.
        </p>
      </div>

      <div className="mt-12 flex flex-wrap gap-3 border-t border-[var(--border-subtle)] pt-8">
        <Link href="/Rankings" className="inline-flex min-h-11 items-center rounded-xl bg-[var(--accent)] px-5 py-2.5 text-sm font-semibold text-[var(--surface-page)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]">View Rankings</Link>
        <Link href="/Market" className="inline-flex min-h-11 items-center rounded-xl border border-[var(--border-subtle)] px-5 py-2.5 text-sm font-semibold text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]">View Market</Link>
        <Link href="/Articles" className="inline-flex min-h-11 items-center rounded-xl border border-[var(--border-subtle)] px-5 py-2.5 text-sm font-semibold text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]">All Articles</Link>
      </div>
    </article>
  );
}
