import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const rankings = fs.readFileSync(new URL("./ExploreTableClient.jsx", import.meta.url), "utf8");
const scoreBadgeSource = fs.readFileSync(new URL("./RipScoreBadge.jsx", import.meta.url), "utf8");
const setPage = fs.readFileSync(new URL("./RipDecisionPage.jsx", import.meta.url), "utf8");
const shared = fs.readFileSync(new URL("./SetRipFamilyBreakdown.jsx", import.meta.url), "utf8");
const cohortControl = fs.readFileSync(new URL("./ProductFamilyRankingsClient.jsx", import.meta.url), "utf8");
const rankingsPage = fs.readFileSync(new URL("../../app/Explore/page.js", import.meta.url), "utf8");
const familyStyles = fs.readFileSync(new URL("./explore.module.css", import.meta.url), "utf8");

test("Rankings desktop exposes the approved Set RIP hierarchy and no economics columns", () => {
  for (const heading of ["Set RIP Score", "Tier", "Format Strength"]) {
    assert.ok(rankings.includes(heading), heading);
  }
  const head = rankings.slice(rankings.indexOf("<thead"), rankings.indexOf("</thead>"));
  assert.ok(!head.includes("Product Family Snapshot"));
  assert.ok(!head.includes('scope="colgroup"'));
  for (const retired of ["Market Price", "Typical Opening", "Model Break-Even", "Chance to Beat Cost", "Top Chase"]) {
    assert.ok(!head.includes(retired), retired);
  }
});

test("Rankings mobile uses dense expandable rows with canonical Set RIP context", () => {
  assert.ok(rankings.includes("expandedMobileSet"));
  assert.ok(rankings.includes('aria-expanded={expanded}'));
  assert.ok(rankings.includes('<FamilySnapshot setRip={target?.setRipV1} layout="modules" compact />'));
  assert.ok(scoreBadgeSource.includes("data-rip-score-badge"));
});

test("Set RIP deep dive keeps opening value and composition content", () => {
  const deepDive = setPage.indexOf('data-rip-section="deep-dive"');
  assert.ok(deepDive >= 0);
  assert.ok(setPage.indexOf("<ProductOpeningValue", deepDive) > deepDive);
  assert.ok(setPage.indexOf("What Makes Up", deepDive) > deepDive);
  assert.ok(!setPage.includes("Booster Pack RIP Rank"));
});

test("one shared array contract and canonical tier function drive both surfaces", () => {
  assert.ok(shared.includes("Array.isArray(setRip?.familyScores)"));
  assert.ok(shared.includes('String(entry?.tier || "").toUpperCase()'));
  assert.ok(!shared.includes("topPercentToTier"));
  assert.ok(rankings.includes("FamilySnapshot"));
  assert.ok(setPage.includes("FamilyScoreRow"));
});

test("family presentation is text-first while the set-page header remains owned by the existing page", () => {
  assert.ok(!shared.includes("FamilyPlaceholder"));
  assert.ok(!shared.includes("data-family-media-slot"));
  assert.ok(rankings.includes('variant="compact"'));
  assert.ok(rankings.includes('variant="mobileRanking"'));
  assert.ok(!setPage.includes("PokemonSetMobileHero"), "RipDecisionPage must not replace the existing set identity header");
});

test("Rankings keeps the compact mobile snapshot and uses fixed desktop family columns", () => {
  assert.ok(shared.includes("data-family-snapshot"));
  assert.ok(shared.includes("Math.min(families.length, 7)"));
  assert.ok(familyStyles.includes("repeat(2, minmax(0, 1fr))"));
  assert.ok(familyStyles.includes("repeat(3, minmax(0, 1fr))"));
  assert.ok(familyStyles.includes("repeat(var(--family-columns), minmax(0, 1fr))"));
  assert.ok(scoreBadgeSource.includes("data-rip-score-badge"));
  assert.ok(rankings.includes("data-ranking-insight"));
  assert.ok(rankings.includes("RankingsFamilyCells"));
  assert.ok(!rankings.includes('scope="colgroup"'));
  assert.ok(cohortControl.includes("SegmentedControl"));
  assert.ok(cohortControl.includes('variant="primary"'));
});

test("Rankings data surface uses the wider desktop canvas and prioritizes family capacity", () => {
  assert.ok(rankingsPage.includes("data-rankings-wide-shell"));
  assert.ok(rankingsPage.includes("md:max-w-[100rem]"));
  assert.ok(!rankingsPage.includes("max-w-5xl"));
  assert.ok(rankings.includes("RANKINGS_FAMILY_COLUMNS.map"));
  assert.ok(rankings.includes('<col style={{ width: "14%" }} />'));
});

test("Set RIP score uses an accessible shared SVG outline and Tier remains separate", () => {
  assert.ok(scoreBadgeSource.includes("<svg"));
  assert.ok(scoreBadgeSource.includes("<polygon"));
  assert.ok(scoreBadgeSource.includes('aria-hidden="true"'));
  assert.ok(scoreBadgeSource.includes("formatModeScore"), "score remains real DOM text");
  assert.ok(!scoreBadgeSource.includes("clip-path"));
  assert.ok(scoreBadgeSource.includes("data-rip-tier-mark"));
  assert.ok(rankings.includes("<RipScoreBadge score={canonicalOverall.publicScore} tier={tier} compact"), "mobile reuses the shared score component");
});

test("family panel relies on spacing rather than spreadsheet cell borders", () => {
  const moduleMarkup = shared.slice(shared.indexOf("data-family-module"), shared.indexOf("</div>;", shared.indexOf("data-family-module")));
  assert.ok(!moduleMarkup.includes("border-r"));
  assert.ok(!moduleMarkup.includes("border-b"));
  assert.ok(!familyStyles.includes("border-right"));
  assert.ok(familyStyles.includes("height: 60%"));
  assert.ok(familyStyles.includes("background: var(--border-subtle)"));
  assert.ok(shared.includes("text-[10px] font-semibold"));
  assert.ok(shared.includes("text-[15px] font-bold"));
});
