import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const highlights = read("./RankingsOverviewHighlights.jsx");
const lazy = read("./RankingsLazyClient.jsx");
const distribution = read("./OpeningEconomicsDistribution.jsx");
const landscape = read("./setRipLandscapeSelector.mjs");

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

test("Overview replaces outcome distributions with the public Set RIP landscape", () => {
  assert.ok(distribution.includes("How Sets Rank to Open"));
  assert.ok(landscape.includes("readPublicSetRip"));
  assert.ok(distribution.includes("data-set-rip-landscape"));
  for (const removed of ["Opening outcome range", "normalizedReturnBuckets", "normalizedReturnPercentiles", "Sets represented"]) assert.ok(!distribution.includes(removed));
  for (const paid of ["financialRipV4", "Collector Appeal", "chaseAccessibility"]) assert.ok(!`${distribution}\n${landscape}`.includes(paid));
  assert.ok(lazy.includes("<OpeningEconomicsOverall economics={openingEconomics} targets={setTargets} />"));
  assert.equal((lazy.match(/lens\?lens=sets/g) || []).length, 1);
});

test("Top Set and Top Era use bespoke concise hierarchy without a redundant Era rank", () => {
  assert.ok(highlights.includes("function TopSetHighlight"));
  assert.ok(highlights.includes("function TopEraHighlight"));
  assert.ok(highlights.includes("#1 Set to Open"));
  assert.ok(highlights.includes("#1 Era to Open"));
  const era = highlights.slice(highlights.indexOf("function TopEraHighlight"), highlights.indexOf("export default"));
  assert.equal((era.match(/#1/g) || []).length, 1);
});
