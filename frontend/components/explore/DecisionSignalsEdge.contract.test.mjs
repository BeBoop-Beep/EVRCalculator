// Decision Signals (Overview, below 1200px) — trailing-edge / clipping fix.
//
// THE DEFECT
// ----------
// The compact rows were `w-full` AND carried `-ml-1.5`. Because the row is
// border-box, `width: 100%` already resolves to the container's content width
// exactly — so the negative margin did not widen the row, it SLID it 6px left.
// Measured live at 320/390/834px, restoring the old two declarations moves each
// row's right edge to `listRight - 6px`. The consequences were:
//
//   * every row (and the accent edge on its left) bled 6px into the page
//     gutter, because the mobile feed reset zeroes this card's horizontal
//     padding (`[data-mobile-feed] .set-glass-surface { padding-inline: 0 }` in
//     globals.css), so there was nothing left to bleed into but the gutter;
//   * each row stopped 6px SHORT of the right edge that the aria-hidden column
//     header and the shared detail region below both reach — a mismatched inset
//     rather than one clean list edge;
//   * `pr-0` pinned the rank hard against that short trailing edge, so the
//     selected row's accent wash terminated immediately after the rank instead
//     of running out to the list edge. That is the "highlight ends abruptly
//     near the trailing rank" symptom.
//
// It never showed on desktop: the desktop tree is a different component
// (DecisionSignalRow), and at 1200px+ the section card keeps its own padding.
//
// THE FIX
// -------
// No negative margins anywhere in the list; symmetric `pl-1.5 pr-1.5`; the
// accent edge is a border every row reserves as transparent, so selection is a
// colour change and never a layout shift; and the numeric tracks were widened
// so the tier pill and the rank each own their column outright.
//
// RipStatisticsPageClient.jsx is not importable outside the Next build (it uses
// extensionless "@/..." specifiers the bundler resolves), so these are source
// assertions, matching every other contract test for this page. The file also
// carries mixed CRLF/LF, so it is normalised before any multi-line anchor.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { selectDecisionSignals } from "./decisionSignalsSelector.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (rel) => fs.readFileSync(path.resolve(here, rel), "utf8").replace(/\r\n/g, "\n");

const source = read("RipStatisticsPageClient.jsx");
const css = read("../../app/styles/globals.css");

const between = (text, startToken, endToken) => {
  const start = text.indexOf(startToken);
  assert.ok(start >= 0, `missing ${startToken}`);
  const end = text.indexOf(endToken, start);
  assert.ok(end > start, `missing ${endToken} after ${startToken}`);
  return text.slice(start, end);
};

const compactList = between(source, "function DecisionSignalsCompactList(", "function DecisionSignalRow(");
const desktopRow = between(source, "function DecisionSignalRow(", "function DecisionSignalsCard(");
const card = between(source, "function DecisionSignalsCard(", "// A Profit / Safety / Stability card.");

// The row `<button>` open tag, and the aria-hidden column header.
const rowTag = between(compactList, "data-decision-signal-row", "\n      >");
const headerTag = between(compactList, 'aria-hidden="true"', "\n      >");

const GRID = "grid-cols-[minmax(0,1fr)_3rem_3.75rem_2.5rem]";

// ---------------------------------------------------------------------------
// The clipping itself
// ---------------------------------------------------------------------------

test("no negative horizontal margin survives anywhere in the compact list", () => {
  // This is the whole defect. `-ml-*` on a border-box `w-full` row is not an
  // inset — it slides the row out of alignment with its own header, and no
  // amount of trailing padding compensates for it.
  assert.ok(!/-m[lrx]-/.test(compactList), "a negative horizontal margin re-creates the overflow");
  assert.ok(!compactList.includes("-ml-1.5"), "the specific margin that caused the clipping is gone");
});

test("the row is inset on BOTH sides so the trailing rank keeps safe space", () => {
  assert.ok(rowTag.includes("pl-1.5 pr-1.5"), "symmetric padding, so neither end is flush against the gutter");
  assert.ok(!/-m[lrx]-/.test(rowTag), "and the inset is padding, not a margin that moves the box");
  assert.ok(!rowTag.includes("pr-0"), "the trailing padding may not be dropped again");
  assert.ok(rowTag.includes("w-full"), "the row still spans the intended list width");
});

test("the accent edge is reserved by every row, so selection never shifts a column", () => {
  // Both states declare the same 2px left border; only its colour changes.
  assert.ok(rowTag.includes("border-l-2"), "the edge is reserved on the row, not added on selection");
  assert.ok(rowTag.includes("border-l-[var(--accent)]"), "the selected edge is the accent");
  assert.ok(rowTag.includes("border-l-transparent"), "the unselected edge is reserved but invisible");
  // The selected branch must not reintroduce geometry of its own. Matched on
  // class-name boundaries so the `color-mix()` in the wash is not read as a
  // margin utility.
  const selectedBranch = between(rowTag, "isSelected\n            ?", ": \"border-l-transparent");
  assert.ok(
    !/(^|[\s"])-?[mp][lrxy]?-|(^|[\s"])w-/.test(selectedBranch),
    "selection changes colour only, never box metrics"
  );
});

test("the selected highlight ends on the list edge, not before or past it", () => {
  // The wash is a background on the row itself, so once the row's box spans the
  // container's content width exactly, the highlight does too. Verified live:
  // right-edge overshoot is 0px at 320/360/390/430/599/600/834/1199px, and the
  // rank keeps a 6px gap to the list edge.
  assert.ok(rowTag.includes("bg-[color:color-mix(in_srgb,var(--accent)_10%,transparent)]"));
  assert.ok(!compactList.includes("absolute"), "no absolutely-positioned bleed layer draws the highlight");
  assert.ok(!compactList.includes("w-screen"), "the highlight never escapes to the viewport width");
});

test("nothing in the list clips its own content or constrains its width", () => {
  assert.ok(!/overflow-hidden|overflow-x-clip|overflow-clip/.test(compactList), "clipping would hide, not fix, an overflow");
  assert.ok(!/\bmax-w-\[|\bw-\[/.test(compactList), "no fixed measure caps the list narrower than its column");
  assert.ok(compactList.includes('data-decision-signals-compact className="min-w-0"'), "the list may shrink with its column");
});

test("the mobile feed reset that exposes the defect is still the operative context", () => {
  // If this reset ever went away the 6px would be absorbed by card padding
  // again and the regression would become invisible rather than fixed.
  const mobileBlock = between(css, "@media (max-width: 1199.98px) {", "\n}\n");
  assert.ok(mobileBlock.includes("[data-mobile-feed] .set-glass-surface"));
  assert.ok(mobileBlock.includes("padding-inline: 0;"), "the section card has no horizontal padding below 1200px");
  assert.ok(source.includes('data-mobile-feed'), "Decision Signals renders inside the reset feed");
});

// ---------------------------------------------------------------------------
// Columns: enough width for the tier pill and the rank, at 320px
// ---------------------------------------------------------------------------

test("the header and the rows share one column system, including the accent edge", () => {
  assert.equal((compactList.match(new RegExp(GRID.replace(/[[\]().]/g, "\\$&"), "g")) || []).length, 2);
  assert.ok(headerTag.includes(GRID), "the header takes the row grid");
  assert.ok(headerTag.includes("border-l-2"), "the header reserves the same edge width the rows do");
  assert.ok(headerTag.includes("pl-1.5 pr-1.5"), "the header takes the row inset, so labels sit over their columns");
  assert.equal((compactList.match(/gap-x-1\.5/g) || []).length, 2, "one gutter value for header and rows");
});

test("the tier and rank tracks are wider than the content they must hold", () => {
  // `compact` RankBadge = px-2 + 1px border either side + "S Tier" at 10px
  // semibold ≈ 47px, so a 3.25rem (52px) track left ~5px of slack and any font
  // fallback pushed the pill into its neighbours. 3.75rem (60px) is the fix.
  // The rank prints "#18"/"#100" at 11px tabular-nums, comfortably inside
  // 2.5rem (40px), which also clears the uppercase "Rank" header label.
  assert.ok(compactList.includes("_3.75rem_2.5rem]"), "tier 60px, rank 40px");
  assert.ok(!compactList.includes("_3.25rem_2.25rem]"), "the tight tracks are gone");
  assert.ok(compactList.includes('size="compact"'), "the pill is still the dense size, not a shrunken supporting pill");
  assert.ok(!compactList.includes('size="supporting"'));
});

test("the tier pill still refuses to wrap to two lines", () => {
  const rankBadge = read("../ui/RankBadge.jsx");
  assert.equal(
    (rankBadge.match(/whitespace-nowrap/g) || []).length,
    2,
    "both the resolved and the unavailable badge stay on one line"
  );
  assert.ok(rankBadge.includes('compact: {'), "the dense size still exists");
  assert.ok(rankBadge.includes('className: "gap-1 px-2 py-0.5 text-[10px]"'), "and its metrics are unchanged");
});

test("readability was not traded for width", () => {
  // The fix is geometry, not shrinking type. These are the sizes the approved
  // design shipped with and they must not creep downward.
  assert.ok(compactList.includes("truncate text-xs font-medium"), "the signal name stays 12px");
  assert.ok(compactList.includes("text-right text-sm font-semibold"), "the score stays 14px");
  assert.ok(compactList.includes("text-right text-[11px]"), "the rank stays 11px");
  assert.ok(!/text-\[(?:[0-9]|10)px\]/.test(rowTag), "no sub-11px text appears in a row");
});

test("numeric columns keep explicit alignment", () => {
  assert.ok(compactList.includes('<span className="text-right text-sm font-semibold'), "score right-aligned");
  assert.ok(compactList.includes('<span className="flex justify-center">'), "tier centred in its own track");
  assert.ok(compactList.includes('<span className="text-right text-[11px]'), "rank right-aligned");
  const header = between(compactList, 'aria-hidden="true"', "</div>");
  assert.ok(header.includes('<span className="text-right">Score</span>'));
  assert.ok(header.includes('<span className="text-center">Tier</span>'));
  assert.ok(header.includes('<span className="text-right">Rank</span>'));
});

// ---------------------------------------------------------------------------
// Unchanged: structure, behaviour, data, desktop
// ---------------------------------------------------------------------------

test("the approved structured-list layout is preserved", () => {
  assert.ok(compactList.includes('groupLabel("OVERALL RIP")'));
  assert.ok(compactList.includes('groupLabel("CORE")'));
  assert.ok(compactList.includes('groupLabel("ALSO TRACKED")'));
  assert.ok(compactList.includes("overallRows.map(renderRow)"));
  assert.ok(compactList.includes("pillarRows.map(renderRow)"));
  assert.ok(compactList.includes("trackedRows.map(renderRow)"));
  assert.ok(compactList.includes("min-h-14"), "rows stay comfortably touch-safe");
  assert.equal((compactList.match(/data-decision-signal-detail/g) || []).length, 1, "one shared interpretation region");
});

test("row selection and the shared interpretation region are unchanged", () => {
  assert.ok(compactList.includes('type="button"'), "Enter and Space come from a real button");
  assert.ok(compactList.includes("setSelectedLabel((previous) => (previous === signal.label ? null : signal.label))"));
  assert.ok(compactList.includes("allRows.find((signal) => signal.label === selectedLabel)"));
  assert.ok(compactList.includes("aria-expanded={isSelected}"));
  assert.ok(compactList.includes("aria-controls={detailRegionId}"));
  assert.ok(compactList.includes('aria-live="polite"'));
  assert.ok(compactList.includes("focus-visible:ring-2"), "focus stays visible");
  assert.ok(compactList.includes("selectedSignal.detailSummary || selectedSignal.summary"));
  assert.ok(compactList.includes("Select a signal to see what it means for this set."));
});

test("every signal, score, tier, rank and interpretation still renders", () => {
  assert.ok(compactList.includes("{signal.label}"));
  assert.ok(compactList.includes('{signal.scoreText || "—"}'));
  assert.ok(compactList.includes("rank={signal.rankTier}"));
  assert.ok(compactList.includes("`#${rankLabel}`"));
  assert.ok(compactList.includes("toNumber(signal.rankValue)"), "rank read straight off the view model");
  assert.ok(compactList.includes("Math.round(parsedRank)"));
  assert.ok(compactList.includes('aria-label="Rank unavailable"'), "a missing rank says so rather than printing 0");
  assert.ok(!/score\s*[*+/-]/.test(compactList), "no arithmetic is applied to any score");
  assert.ok(!compactList.includes("sort("), "row order is not re-sorted");
  assert.ok(!compactList.includes("|| 0"), "no fake zero is substituted");
});

test("the signal data itself is untouched — the selector still produces the same rows", () => {
  // A CSS fix must not change a single value the rows print, so the shared
  // selector is exercised directly: labels, score text, tiers, ranks and both
  // interpretation strings, in order.
  const pillarSignals = [
    { title: "Profit", score: 74.2, rankValue: 9, rankTier: "A", highlight: "Strong payoff ceiling" },
    { title: "Safety", score: 51.8, rankValue: 61, rankTier: "C", highlight: "Controlled misses" },
    { title: "Stability", score: 63.1, rankValue: 30, rankTier: "B", highlight: "Decent value spread" },
  ];

  const { rows, diagnostics } = selectDecisionSignals({ pillarSignals, summary: {}, requestTimeout: false });

  assert.deepEqual(
    rows.map((r) => [r.label, r.scoreText, r.rankTier, r.rankValue, r.summary, r.detailSummary]),
    [
      ["Profit", "74", "A", 9, "Strong payoff ceiling", "Strong payoff ceiling"],
      ["Safety", "52", "C", 61, "Controlled misses", "Controlled misses"],
      ["Stability", "63", "B", 30, "Decent value spread", "Decent value spread"],
    ]
  );
  assert.equal(diagnostics.status, "ready");
});

test("the 1200px+ presentation is untouched by this fix", () => {
  assert.ok(card.includes('<div className="desk:hidden">'), "the compact list is still the below-desktop tree");
  assert.ok(card.includes('<div className="hidden desk:block">'), "the desktop tree is still gated to desktop");
  assert.ok(desktopRow.includes("set-glass-inner"), "the desktop surface class is unchanged");
  assert.ok(
    desktopRow.includes("desk:grid-cols-[minmax(0,1fr)_4.25rem_5.75rem_3.25rem]"),
    "the desktop four-column grid is unchanged"
  );
  assert.ok(!desktopRow.includes(GRID), "the mobile grid never leaks onto the desktop row");
  // Within Decision Signals the mobile column system exists on exactly two
  // elements: the aria-hidden column header and the row. (The same track widths
  // are also declared once as RIP_COMPACT_GRID for the Insights breakdown —
  // deliberate shared metrics, a different section.)
  assert.equal(
    (compactList.match(new RegExp(GRID.replace(/[[\]().]/g, "\\$&"), "g")) || []).length,
    2,
    "the mobile column system exists only on the compact header and row"
  );
  assert.ok(!card.includes(GRID), "and nowhere else in the Decision Signals card");
});
