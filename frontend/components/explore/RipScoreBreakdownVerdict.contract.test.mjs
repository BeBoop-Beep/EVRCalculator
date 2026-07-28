// RIP Score Breakdown — the "01 · Verdict" section on the set-page Insights tab.
//
// The section was simplified to a user-facing verdict: score → what it means →
// the three pillars. The formula-construction panel ("How Overall RIP Is Built"
// with its contribution points, the 90/10 blend line and the effective final
// weights) explained how the number is assembled rather than what it means, so
// it is gone from the UI. None of the arithmetic changed: the same backend
// contract, the same selectors, the same scores/ranks/tiers/weights.
//
// The component lives inside RipStatisticsPageClient.jsx and is not exported —
// and that file cannot be imported outside the Next build (it uses extensionless
// "@/..." specifiers that only the bundler resolves), so structural assertions
// here read the rendered JSX source, matching the existing contract tests for
// this page. The value assertions below run the real selectors.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { selectRipScoreBreakdown } from "./ripScoreBreakdownSelector.mjs";
import { RIP_CORE_MODE, RIP_SCORE_MODE, selectRipHeroScoreMode } from "./ripHeroScoreMode.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const clientPath = path.join(here, "RipStatisticsPageClient.jsx");
const source = fs.readFileSync(clientPath, "utf8").replace(/\r\n/g, "\n");

// The rendered body of RipScoreBreakdownModule, in source order.
function verdictSection() {
  const start = source.indexOf("function RipScoreBreakdownModule");
  const end = source.indexOf("function StatTile", start);
  assert.ok(start >= 0 && end > start, "RipScoreBreakdownModule must exist");
  return source.slice(start, end);
}

function orderOf(section, marker) {
  const index = section.indexOf(marker);
  assert.ok(index >= 0, `expected the verdict section to contain ${marker}`);
  return index;
}

// ---------------------------------------------------------------------------
// Removed content
// ---------------------------------------------------------------------------

test("the redundant verdict subtitle is gone and the title block stays", () => {
  const section = verdictSection();

  assert.ok(
    !source.includes("The verdict — how this set scores and why."),
    "the subtitle restated the heading and was removed, not replaced"
  );
  assert.ok(section.includes("<SectionEyebrow>01 · Verdict</SectionEyebrow>"));
  assert.ok(section.includes(">RIP Score Breakdown</h2>"));
});

test("the Overall RIP construction panel is removed from the user-facing section", () => {
  const section = verdictSection();

  for (const forbidden of [
    "How Overall RIP Is Built",
    "Effective final weights",
    "90% Financial RIP + 10% Opening Desirability",
    "Financial RIP × 90%",
    "Opening Desirability × 10%",
    "RipDesirabilityBreakdownStrip",
    "ripDesirabilityBreakdown",
    "contributionLabel",
    "effectiveWeights",
  ]) {
    assert.ok(!source.includes(forbidden), `"${forbidden}" must not appear anywhere on the page`);
    assert.ok(!section.includes(forbidden), `"${forbidden}" must not appear in the verdict section`);
  }
});

test("the construction panel cannot come back through a collapsed or hidden region", () => {
  const section = verdictSection();

  // Not merely hidden: there is no markup for it at all, so no CSS state,
  // score mode, or expanded state can bring it back.
  assert.ok(!section.includes("hidden md:block"), "no display-toggled construction region may remain");
  // The section renders one flat sequence with no score-mode branching, so the
  // layout is identical in RIP Score mode and RIP Core mode.
  assert.ok(!section.includes("scoreMode ==="), "the layout must not branch on score mode");
  assert.ok(!section.includes(RIP_CORE_MODE), "the section must not special-case a score mode");
});

// ---------------------------------------------------------------------------
// Preserved content
// ---------------------------------------------------------------------------

test("the verdict section keeps its score summary, mode toggle and pillar grid", () => {
  const section = verdictSection();

  // Score-mode toggle, wired exactly as before.
  assert.ok(section.includes("<RipScoreModeToggle value={scoreMode} onChange={onScoreModeChange} coreAvailable={coreAvailable} />"));

  // Primary score summary: score, /100, trend, rank badge, interpretation
  // badge and the explanation tooltip.
  assert.ok(section.includes("{formatRawScore(score)}"));
  assert.ok(section.includes(">/100</span>"));
  assert.ok(section.includes("<TrendIndicator trend={scoreTrend}"));
  assert.ok(section.includes("<RankBadge"));
  assert.ok(section.includes('label="Rank"'));
  assert.ok(section.includes("<RecommendationBadge label={verdict} rankTier={rankTier} />"));
  assert.ok(section.includes("{explanation ? <InfoPopover text={explanation} /> : null}"));

  // Pillar grid: three columns where space permits, stacked below that.
  assert.ok(section.includes("sm:grid-cols-3"));
  assert.ok(section.includes("<CompactPillarSignalTile key={`rip-pillar:${pillar.title}`} {...pillar} detailsExpanded={detailsExpanded} />"));
});

test("the pillar cards keep their canonical Profit / Safety / Stability bindings", () => {
  const tilesStart = source.indexOf("const ripPillarTiles = [");
  const tilesEnd = source.indexOf("const overviewPillarSignals", tilesStart);
  assert.ok(tilesStart >= 0 && tilesEnd > tilesStart);
  const tiles = source.slice(tilesStart, tilesEnd);

  assert.ok(tiles.indexOf('title: "Profit"') < tiles.indexOf('title: "Safety"'));
  assert.ok(tiles.indexOf('title: "Safety"') < tiles.indexOf('title: "Stability"'));
  for (const pillar of ["Profit", "Safety", "Stability"]) {
    assert.ok(tiles.includes(`ripBreakdownRowByTitle.get("${pillar}")?.score`));
    assert.ok(tiles.includes(`ripBreakdownRowByTitle.get("${pillar}")?.rankValue`));
    assert.ok(tiles.includes(`ripBreakdownRowByTitle.get("${pillar}")?.rankTier`));
    assert.ok(tiles.includes(`infoText: getFormattedTooltip("${pillar}")`));
  }
});

test("Opening Outlook renders once, from the canonical value handed to the section", () => {
  const section = verdictSection();

  assert.equal(
    (source.match(/data-insights-opening-outlook/g) || []).length,
    1,
    "the outlook must not be duplicated after being moved above the pillars"
  );
  // Canonical text only: no frontend rewriting, no score-range wording, no
  // verdict derived from the pillar scores.
  assert.ok(section.includes("{openingOutlook || \"No opening outlook is available for this set yet.\"}"));
  assert.ok(section.includes("It does not evaluate sealed-product appreciation"));
  assert.ok(!section.includes("<details"), "the outlook stays complete rather than truncated behind a disclosure");
});

test("Opening Outlook reads as a restrained highlighted callout, not a dashboard card", () => {
  const section = verdictSection();
  const start = section.indexOf("data-insights-opening-outlook");
  const callout = section.slice(start, section.indexOf("</div>", section.indexOf("{openingOutlook ||", start)));

  // Small uppercase eyebrow + stronger-than-body copy contrast.
  assert.ok(callout.includes("uppercase tracking-[0.08em]"));
  assert.ok(callout.includes(">Opening Outlook</p>"));
  assert.ok(callout.includes("text-[var(--text-primary)]"), "the copy must be fully opaque primary text");
  assert.ok(callout.includes("text-sm"), "body copy stays at the readable minimum");

  // A narrow rail plus a horizontal wash, both from the shared tier
  // presentation — never a flat fill spanning the content width.
  assert.ok(callout.includes("border-l-2"), "the tier-coloured rail stays");
  assert.ok(section.includes("getRipTierPresentation({ label: verdict, rankTier })"));
  assert.ok(callout.includes("borderLeftColor: outlookAccent.outlookRail.borderLeftColor"));
  assert.ok(callout.includes("backgroundImage: outlookAccent.outlookWash"));
  assert.ok(
    !/backgroundColor:/.test(callout),
    "a uniform background colour would re-create the full-width alert banner"
  );

  // No box: the wash fades out on its own, so nothing draws a right-hand edge.
  assert.ok(!callout.includes("rounded"), "a rounded container would read as an alert box");
  assert.ok(!/\bborder(?![-\w])|border-\[|border-r|border-t|border-b/.test(callout), "only the left rail may draw a border");

  // Not a heavy panel: no glass class, no blur, no parent opacity.
  assert.ok(!callout.includes("set-glass"), "the callout must not reuse the heavy glass surface");
  assert.ok(!callout.includes("backdrop-blur"));
  assert.ok(!/\bopacity-\d/.test(callout), "no parent-level opacity may dim the callout contents");
  // Meaning is not carried by the border colour alone — the label says it.
  assert.ok(callout.includes("Opening Outlook"));
});

test("Opening Outlook keeps the full content width and takes no fixed measure", () => {
  const section = verdictSection();
  const start = section.indexOf("data-insights-opening-outlook");
  const openTag = section.slice(start, section.indexOf(">", section.indexOf("style={{", start)));

  assert.ok(openTag.includes("min-w-0"), "the callout must still shrink with its column");
  assert.ok(
    !/\b(max-w-|w-1\/2|w-\[)/.test(openTag),
    "the container must not be capped at a half or fixed width — only the colour stops early"
  );
});

// ---------------------------------------------------------------------------
// Ordering
// ---------------------------------------------------------------------------

test("the verdict reads heading → details toggle → mode toggle → score → outlook → pillars", () => {
  const section = verdictSection();

  const eyebrow = orderOf(section, "<SectionEyebrow>01 · Verdict</SectionEyebrow>");
  const heading = orderOf(section, ">RIP Score Breakdown</h2>");
  const detailsToggle = orderOf(section, "aria-expanded={detailsExpanded}");
  const modeToggle = orderOf(section, "<RipScoreModeToggle");
  const score = orderOf(section, "{formatRawScore(score)}");
  const outlook = orderOf(section, "data-insights-opening-outlook");
  const pillars = orderOf(section, "{pillars.map((pillar) => (");

  assert.ok(eyebrow < heading, "the chapter marker precedes the heading");
  assert.ok(heading < detailsToggle, "Show Details sits in the header, aligned with the heading block");
  assert.ok(detailsToggle < modeToggle, "the details control precedes the score-mode toggle");
  assert.ok(modeToggle < score, "the score-mode toggle precedes the score it switches");
  assert.ok(score < outlook, "the primary score appears before Opening Outlook");
  assert.ok(outlook < pillars, "Opening Outlook appears before the Profit / Safety / Stability grid");
});

test("nothing renders after the pillar grid", () => {
  const section = verdictSection();
  const afterPillars = section.slice(section.indexOf("<CompactPillarSignalTile") + "<CompactPillarSignalTile".length);

  assert.ok(!/<[A-Z][A-Za-z]*/.test(afterPillars), "the section must end with the pillar grid");
  assert.ok(!afterPillars.includes("How Overall RIP"));
  assert.ok(!afterPillars.includes("data-insights-opening-outlook"), "the old outlook placement must be gone");
});

test("the section header and outlook stay compact rather than reserving deleted space", () => {
  const section = verdictSection();

  // The subtitle's spacing went with the subtitle; the header block is now
  // eyebrow + heading only, and the vertical rhythm below it is uniform.
  assert.ok(!section.includes('className="mt-1 min-w-0 max-w-full text-sm text-[var(--text-secondary)]"'));
  assert.ok(!section.includes("mt-5"), "the old oversized gaps are gone");
  assert.ok(!section.includes("border-t border-[var(--border-subtle)] pt-4"), "the outlook divider is no longer needed");
  // Header wraps cleanly on mobile instead of overlapping the control.
  assert.ok(section.includes("flex-wrap items-start justify-between gap-x-3 gap-y-2"));
  assert.ok(section.includes("inline-flex flex-none items-center"), "the control must not stretch or float");
});

// ---------------------------------------------------------------------------
// Show Details
// ---------------------------------------------------------------------------

test("Show Details still controls real user-facing detail, not the removed panel", () => {
  const section = verdictSection();

  // Semantics and keyboard/focus behaviour preserved.
  assert.ok(section.includes('type="button"'));
  assert.ok(section.includes("aria-expanded={detailsExpanded}"));
  assert.ok(section.includes("focus-visible:ring-2"));
  assert.ok(section.includes('{detailsExpanded ? "Hide Details" : "Show Details"}'));
  assert.ok(section.includes('aria-hidden="true"'), "the chevron stays decorative");

  // What it expands: the supporting per-pillar metric rows, which are
  // user-facing values — not formula contributions or effective weights.
  assert.ok(section.includes("detailsExpanded={detailsExpanded}"));

  const tileStart = source.indexOf("function CompactPillarSignalTile");
  const tileEnd = source.indexOf("\n}\n", tileStart);
  assert.ok(tileStart >= 0 && tileEnd > tileStart);
  const tile = source.slice(tileStart, tileEnd);
  assert.ok(tile.includes("{detailsExpanded && metrics.length > 0 ? ("), "no empty details region may render");
  assert.ok(tile.includes("<MetricRow"));

  // The tile is handed `weight` and `contribution` by the shared selector (they
  // stay on the view model for Explore and diagnostics) but reads neither, so
  // no formula math can reach the expanded state.
  const signature = tile.slice(0, tile.indexOf("}) {"));
  assert.ok(!signature.includes("weight"), "the tile must not read the formula weight prop");
  assert.ok(!signature.includes("contribution"), "the tile must not read the contribution prop");
});

test("expanded pillar detail is real user-facing supporting data", () => {
  const metricsStart = source.indexOf("const stabilityPillarMetrics = [");
  const metricsEnd = source.indexOf("];", metricsStart);
  const metrics = source.slice(metricsStart, metricsEnd);

  assert.ok(metrics.includes('label: "Cards Carrying Value"'));
  assert.ok(metrics.includes('label: "Top Chase Share"'));
  assert.ok(!metrics.includes("Effective"), "no effective-weight rows may hide under the toggle");
});

// ---------------------------------------------------------------------------
// Missing optional data
// ---------------------------------------------------------------------------

test("a missing Opening Outlook degrades to the existing unavailable copy", () => {
  const section = verdictSection();

  // The existing unavailable-data convention is kept, so the callout is never
  // empty and never prints `undefined`.
  assert.ok(section.includes('"No opening outlook is available for this set yet."'));
  assert.ok(!section.includes("{openingOutlook}"), "the raw value is never rendered unguarded");
});

test("a missing score, rank or cohort renders unavailable rather than crashing", () => {
  const section = verdictSection();

  assert.ok(section.includes("const parsedRank = toNumber(rankValue);"));
  assert.ok(section.includes("const parsedCohortSize = toNumber(cohortSize);"));
  assert.ok(section.includes('parsedRank === null\n                ? "Rank unavailable"'));
  // formatRawScore is the shared null-safe formatter ("—" for missing).
  assert.ok(source.includes("return parsed === null ? \"—\" : parsed.toFixed(1);"));
});

// ---------------------------------------------------------------------------
// Values unchanged — the layout update touched presentation only.
// ---------------------------------------------------------------------------

const RIP_FIXTURE = {
  score: 68.4,
  relativeScore: 70.9,
  rank: 12,
  tier: "B",
  cohortSize: 140,
  interpretation: { label: "Good value, rough misses", summary: "This set has good value for the price." },
  financialRip: {
    components: {
      profit: { score: 74.2, rank: 9, tier: "A", cohortSize: 140, weight: 0.6, contribution: 44.52 },
      safety: { score: 51.8, rank: 61, tier: "C", cohortSize: 140, weight: 0.25, contribution: 12.95 },
      stability: { score: 63.1, rank: 30, tier: "B", cohortSize: 140, weight: 0.15, contribution: 9.465 },
    },
  },
};

const RIP_CORE_FIXTURE = {
  score: 66.1,
  relativeScore: 64.3,
  rank: 21,
  tier: "B",
  cohortSize: 140,
  interpretation: { label: "Solid financial floor", summary: "Financial profile only." },
};

test("the three pillar values the section displays are unchanged", () => {
  const { rows, sourceUsed, fallbackUsed } = selectRipScoreBreakdown(RIP_FIXTURE, {});

  assert.deepEqual(
    rows.map((row) => [row.title, row.score, row.rankValue, row.rankTier]),
    [
      ["Profit", 74.2, 9, "A"],
      ["Safety", 51.8, 61, "C"],
      ["Stability", 63.1, 30, "B"],
    ]
  );
  assert.equal(sourceUsed, "rip.financialRip.components");
  assert.equal(fallbackUsed, false);
});

test("both score modes still resolve the same values the section renders", () => {
  const payload = { rip: RIP_FIXTURE, ripCore: RIP_CORE_FIXTURE };

  const ripScore = selectRipHeroScoreMode({ mode: RIP_SCORE_MODE, payload });
  assert.equal(ripScore.mode, RIP_SCORE_MODE);
  assert.equal(ripScore.score, 70.9);
  assert.equal(ripScore.absoluteScore, 68.4);
  assert.equal(ripScore.rank, 12);
  assert.equal(ripScore.tier, "B");
  assert.equal(ripScore.interpretation.label, "Good value, rough misses");
  assert.equal(ripScore.coreAvailable, true);

  const ripCore = selectRipHeroScoreMode({ mode: RIP_CORE_MODE, payload });
  assert.equal(ripCore.mode, RIP_CORE_MODE);
  assert.equal(ripCore.score, 64.3);
  assert.equal(ripCore.absoluteScore, 66.1);
  assert.equal(ripCore.rank, 21);
  assert.equal(ripCore.tier, "B");
  assert.equal(ripCore.interpretation.label, "Solid financial floor");

  // Switching modes changes the values, never the pillar contract.
  assert.notEqual(ripScore.score, ripCore.score);
  assert.deepEqual(
    selectRipScoreBreakdown(RIP_FIXTURE, {}).rows.map((row) => row.score),
    [74.2, 51.8, 63.1]
  );
});
