import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const highlights = read("./RankingsOverviewHighlights.jsx");
const lazy = read("./RankingsLazyClient.jsx");
const distribution = read("./OpeningEconomicsDistribution.jsx");
const landscape = read("./setRipLandscapeSelector.mjs");
const primitives = read("./RankingsScorePrimitives.jsx");

test("Overview exposes exactly four Basic-safe highlights", () => {
  for (const label of ["Top Set", "Top Era", "Lowest Avg Cost / Pack", "Modeled Coverage"]) assert.ok(highlights.includes(label));
  assert.ok(highlights.includes("overview?.topSet"));
  assert.ok(!highlights.includes("readBenchmarkOverviewHeadlines"));
  assert.ok(highlights.includes("averagePackCost"));
  for (const field of ["coverage.setCount", "coverage.productCount", "coverage.productFamilyCount"]) assert.ok(highlights.includes(field));
  for (const paid of ["Collector Appeal", "Chase Accessibility", "familyScores", "overallRipV12", "Card Chase"]) assert.ok(!highlights.includes(paid));
});

test("Overview handoffs switch existing state and reuse cached Set/Era loaders", () => {
  assert.ok(lazy.includes('onOpenTopSet={() => { setSetEntryView("ripScore"); setActiveLens("sets"); }}'));
  assert.ok(lazy.includes('onOpenTopEra={() => { setEraLens("rankings"); setActiveLens("eras"); }}'));
  assert.ok(lazy.includes('onOpenLowestCost={() => { setSetEntryView("packEconomics"); setActiveLens("sets"); }}'));
  assert.ok(lazy.includes("loadSets({ foreground: true })"));
  assert.ok(lazy.includes("loadEra({ foreground: true })"));
});

test("Overview replaces the legacy Set RIP landscape with absolute Financial RIP history", () => {
  assert.ok(distribution.includes("FinancialRipHistoryChart"));
  for (const removed of ["Opening outcome range", "normalizedReturnBuckets", "normalizedReturnPercentiles", "Sets represented"]) assert.ok(!distribution.includes(removed));
  for (const paid of ["Collector Appeal", "chaseAccessibility"]) assert.ok(!`${distribution}\n${landscape}`.includes(paid));
  assert.ok(lazy.includes("targets={targets}"));
  const overviewInvocation = lazy.slice(lazy.indexOf("<OpeningEconomicsOverall"), lazy.indexOf("</>", lazy.indexOf("<OpeningEconomicsOverall")));
  assert.ok(!overviewInvocation.includes("benchmark="));
  assert.ok(lazy.includes('readPublicRankingsHeadlines("set"'));
});

test("Top Set and Top Era use bespoke concise hierarchy without a redundant Era rank", () => {
  assert.ok(highlights.includes("#1 Set to Open"));
  assert.ok(highlights.includes("#1 Era to Open"));
  assert.equal((highlights.match(/#1 Era to Open/g) || []).length, 1);
  assert.equal((highlights.match(/RankingsRipScoreBadge/g) || []).length, 3);
  assert.ok(primitives.includes("RipScoreBadge"));
});

test("Overall Financial RIP is absolute, defined, and never presented as a /10 score", () => {
  assert.ok(highlights.includes("financial.absoluteScore"));
  assert.ok(highlights.includes("absolute Financial RIP value"));
  const summary = highlights.slice(highlights.indexOf("data-overall-financial-rip"));
  assert.ok(!summary.includes("<RipScoreBadge"));
  assert.ok(summary.includes("not a /10 score"));
});

test("lowest cost explanation is in an InfoPopover instead of visible body copy", () => {
  assert.ok(highlights.includes('info="Lowest modeled average cost per pack; this is not a quality ranking."'));
  assert.equal((highlights.match(/Lowest modeled average cost per pack/g) || []).length, 1);
});
