// The page's standing methodology row.
//
// These three notes are about the WHOLE workspace — what Tracked Value is, what
// the Market Index neutralises, and why two long windows have different names —
// so unlike the per-group notes they belong on the page rather than inside a
// group's ⓘ. They stay at the bottom, after the research, not between the
// controls.
const HELP_TRACKED_VALUE = "Tracked Value is the current dollar value of the tracked basket. It moves both because prices move and because constituents enter or leave the tracked universe.";
const HELP_INDEX = "Market Index measures price performance from a base of 100 while neutralizing constituent additions and removals. An index of 106.18 means that market is 6.18% above its own index base — not that every card or product in it rose 6.18%.";
const HELP_WINDOWS = "Every timeframe is measured over the selected market's OWN history: 7D reaches seven elapsed calendar days back, and All reaches that market's tracking start, so All reconciles with its Market Index. Markets began tracking on different dates, so All spans differ between them and is not a like-for-like cross-market comparison.";

const NOTES = [
  { title: "Tracked Value.", body: HELP_TRACKED_VALUE },
  { title: "Market Index.", body: HELP_INDEX },
  { title: "Time windows.", body: HELP_WINDOWS },
];

export default function MarketExplorerMethodology() {
  return (
    <div data-market-explorer-methodology className="grid grid-cols-1 gap-2.5 desk:grid-cols-3 desk:gap-3">
      {NOTES.map((note) => (
        <p
          key={note.title}
          className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/25 px-3 py-2.5 text-[11px] leading-relaxed text-[var(--text-secondary)]"
        >
          <span className="font-semibold text-[var(--text-primary)]">{note.title}</span> {note.body}
        </p>
      ))}
    </div>
  );
}
