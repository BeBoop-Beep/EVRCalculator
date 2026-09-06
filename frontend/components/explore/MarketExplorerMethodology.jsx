// The page's standing methodology row.
//
// These notes are about the WHOLE workspace — what Market Explorer is, what
// an Active Market means, what Tracked Value and the Market Index measure,
// how constituents and Top N work, how Screens relate to the Builder, and how
// the Per-Set Chase benchmark differs from a custom Global Top 10 query — so
// unlike the per-group notes they belong on the page rather than inside a
// group's ⓘ. They stay at the bottom, after the research, not between the
// controls.
//
// PLAIN LANGUAGE ONLY. This is user-facing product explanation, not an
// implementation writeup — no Postgres, no L1/L2 cache tiers, no RPC names,
// no projection-table vocabulary. A reader should come away understanding
// what the numbers mean and how to trust them, not how the backend computes
// them.
const HELP_WHAT_IS_EXPLORER = "Market Explorer lets you compare card and sealed-product markets side by side — the published Raw, Sealed and Per-Set Chase markets, curated Screens, or a market you filter and build yourself.";
const HELP_ACTIVE_MARKET = "An Active Market is any market currently on the chart — whether you clicked a published market, ran a Screen, or built a custom one. Hiding it removes its line from the chart without dropping it; removing it takes it off the workspace entirely, and you would need to build or select it again to bring it back.";
const HELP_TRACKED_VALUE = "Tracked Value is the current dollar value of the tracked basket. It moves both because prices move and because constituents enter or leave the tracked universe.";
const HELP_INDEX = "Market Index measures price performance from a base of 100 while neutralizing constituent additions and removals. An index of 106.18 means that market is 6.18% above its own index base — not that every card or product in it rose 6.18%.";
const HELP_WINDOWS = "Every timeframe is measured over the selected market's OWN history: 7D reaches seven elapsed calendar days back, and All reaches that market's tracking start, so All reconciles with its Market Index. Markets began tracking on different dates, so All spans differ between them and is not a like-for-like cross-market comparison. Switching timeframes changes what you see, never which market you are looking at.";
const HELP_CONSTITUENTS = "A market's constituents are the individual cards or products your filters resolve to. Filters are always applied first — era, set, rarity, Pokémon, price and release age narrow the eligible universe — and only after that does a ranked market (like Top N) rank what remains. A card that would not qualify under your filters is never added back in to fill out a ranking.";
const HELP_TOP_N = "Top N ranks the filtered universe by price and keeps the top result — currently Top 10. Ranking always happens after filtering, on the exact universe your filters produced, never on a separate or pre-selected shortlist.";
const HELP_UPDATES = "Market data updates once per tracked day, after that day's prices are captured and verified. The as-of date shown with a market's constituents is the date its figures were last computed through.";
const HELP_VARIANTS = "Some cards exist in more than one physical form of the same print — First Edition vs. Unlimited, Shadowless vs. non-Shadowless, Holo vs. Reverse Holo vs. Non-Holo — and these are tracked as separate instruments with separate prices. Where a set has more than one such form, constituent rows say which one they are; where a card has only one recognized form, the label is left off rather than repeated on every row.";
const HELP_SCREENS_VS_BUILDER = "A Screen is a shortcut to a market someone has already defined — a rarity, a price tier, a release-age cohort, or a ranked leaderboard. Selecting one hands the same filters to the same market engine the Builder uses, so a Screen's market behaves exactly like one you built by hand, and an equivalent hand-built market is recognized as the same market rather than added twice.";
const HELP_PER_SET_CHASE = "The Per-Set Chase Market and a custom Top 10 query answer different questions. Per-Set Chase combines each tracked set's OWN chase basket — its highest-value cards, one basket per set, added together. A custom Top 10 ignores set boundaries entirely: it filters the whole eligible universe you specify and then ranks globally, so it can be dominated by a single set if that set happens to have the highest-priced cards. Per-Set Chase is not \"the ten highest-value cards globally,\" and a Global Top 10 is not a per-set basket.";

const NOTES = [
  { title: "What is Market Explorer?", body: HELP_WHAT_IS_EXPLORER },
  { title: "What is an Active Market?", body: HELP_ACTIVE_MARKET },
  { title: "Tracked Value.", body: HELP_TRACKED_VALUE },
  { title: "Market Index.", body: HELP_INDEX },
  { title: "Constituents.", body: HELP_CONSTITUENTS },
  { title: "Top N.", body: HELP_TOP_N },
  { title: "Time windows.", body: HELP_WINDOWS },
  { title: "Data updates.", body: HELP_UPDATES },
  { title: "Variants.", body: HELP_VARIANTS },
  { title: "Screens vs. the Builder.", body: HELP_SCREENS_VS_BUILDER },
  { title: "Per-Set Chase vs. Global Top 10.", body: HELP_PER_SET_CHASE },
];

export default function MarketExplorerMethodology() {
  return (
    <section aria-label="Methodology" className="space-y-2">
      <h2 className="px-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
        Methodology
      </h2>
      <div data-market-explorer-methodology className="grid grid-cols-1 gap-2.5 desk:grid-cols-3 desk:gap-3">
        {NOTES.map((note) => (
          <p
            key={note.title}
            data-market-explorer-methodology-note={note.title}
            className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/25 px-3 py-2.5 text-[11px] leading-relaxed text-[var(--text-secondary)]"
          >
            <span className="font-semibold text-[var(--text-primary)]">{note.title}</span> {note.body}
          </p>
        ))}
      </div>
    </section>
  );
}
