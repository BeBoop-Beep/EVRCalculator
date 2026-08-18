import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const rankings = fs.readFileSync(new URL("./ExploreTableClient.jsx", import.meta.url), "utf8");
const setPage = fs.readFileSync(new URL("./RipDecisionPage.jsx", import.meta.url), "utf8");
const shared = fs.readFileSync(new URL("./SetRipFamilyBreakdown.jsx", import.meta.url), "utf8");

test("Rankings desktop exposes the approved Set RIP hierarchy and no economics columns", () => {
  for (const heading of ["Set RIP Score", "Tier", "Product Family Snapshot", "Why It Ranks"]) {
    assert.ok(rankings.includes(heading), heading);
  }
  const head = rankings.slice(rankings.indexOf("<thead"), rankings.indexOf("</thead>"));
  for (const retired of ["Market Price", "Typical Opening", "Model Break-Even", "Chance to Beat Cost", "Top Chase"]) {
    assert.ok(!head.includes(retired), retired);
  }
});

test("Rankings mobile uses dense expandable rows with canonical Set RIP context", () => {
  assert.ok(rankings.includes("expandedMobileSet"));
  assert.ok(rankings.includes('aria-expanded={expanded}'));
  assert.ok(rankings.includes('<FamilySnapshot setRip={target?.setRipV1} compact />'));
  assert.ok(rankings.includes('columnId="setRip"'));
});

test("Set RIP page leads with composition and keeps downstream opening content", () => {
  const breakdown = setPage.indexOf('data-rip-section="set-rip-breakdown"');
  assert.ok(breakdown >= 0);
  assert.ok(setPage.indexOf("What Makes Up", breakdown) > breakdown);
  assert.ok(setPage.indexOf("<ProductOpeningValue", breakdown) > breakdown);
  assert.ok(!setPage.includes("Booster Pack RIP Rank"));
});

test("one shared array contract and canonical tier function drive both surfaces", () => {
  assert.ok(shared.includes("Array.isArray(setRip?.familyScores)"));
  assert.ok(shared.includes("topPercentToTier((rank / cohortSize) * 100)"));
  assert.ok(rankings.includes("FamilySnapshot"));
  assert.ok(setPage.includes("FamilyScoreRow"));
});

