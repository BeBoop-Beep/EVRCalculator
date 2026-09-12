import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const highlights = read("./RankingsOverviewHighlights.jsx");
const lazy = read("./RankingsLazyClient.jsx");
const distribution = read("./OpeningEconomicsDistribution.jsx");

test("Overview exposes exactly four Basic-safe highlights", () => {
  for (const label of ["Top Set", "Top Era", "Lowest Avg Cost / Pack", "Modeled Coverage"]) assert.ok(highlights.includes(label));
  assert.ok(highlights.includes("readPublicSetRip(target).rank === 1"));
  assert.ok(highlights.includes("era.rank === 1"));
  assert.ok(highlights.includes("averageCostPerPack"));
  for (const field of ["global.setCount", "global.productSkuCount", "global.productFamilyCount"]) assert.ok(highlights.includes(field));
  for (const paid of ["Financial RIP", "Collector Appeal", "Chase Accessibility", "familyScores", "overallRipV12", "Card Chase"]) assert.ok(!highlights.includes(paid));
});

test("Overview handoffs switch existing state and reuse cached Set/Era loaders", () => {
  assert.ok(lazy.includes('onOpenTopSet={() => { setSetEntryView("ripScore"); setActiveLens("sets"); }}'));
  assert.ok(lazy.includes('onOpenTopEra={() => { setEraLens("rankings"); setActiveLens("eras"); }}'));
  assert.ok(lazy.includes('onOpenLowestCost={() => { setSetEntryView("packEconomics"); setActiveLens("sets"); }}'));
  assert.equal((lazy.match(/fetch\("\/api\/explore\/rankings\/lens\?lens=sets"/g) || []).length, 1);
  assert.equal((lazy.match(/fetch\("\/api\/explore\/rankings\/lens\?lens=eras"/g) || []).length, 1);
});

test("exact buckets take priority over a truthful percentile compatibility curve", () => {
  assert.ok(distribution.includes("const percentilePoints = buckets.length ? [] : readLegacyReturnPercentiles(scope)"));
  assert.ok(distribution.includes('data-recovery-buckets="6"'));
  assert.ok(distribution.includes('data-legacy-percentile-points="99"'));
  assert.ok(distribution.includes("Each point is a published percentile position; it is not a frequency bucket."));
  assert.ok(!distribution.includes("interpolat"));
  assert.ok(distribution.includes("The modeled recovery distribution is unavailable."));
});
