import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const rankings = fs.readFileSync(new URL("./ExploreTableClient.jsx", import.meta.url), "utf8");
const setPage = fs.readFileSync(new URL("./RipDecisionPage.jsx", import.meta.url), "utf8");
const shared = fs.readFileSync(new URL("./SetRipFamilyBreakdown.jsx", import.meta.url), "utf8");
const cohortControl = fs.readFileSync(new URL("./ProductFamilyRankingsClient.jsx", import.meta.url), "utf8");
const rankingsPage = fs.readFileSync(new URL("../../app/Explore/page.js", import.meta.url), "utf8");
const familyStyles = fs.readFileSync(new URL("./explore.module.css", import.meta.url), "utf8");

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
  assert.ok(rankings.includes('<FamilySnapshot setRip={target?.setRipV1} layout="modules" compact />'));
  assert.ok(rankings.includes("data-set-rip-score-badge"));
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

test("family presentation is text-first while the set-page header remains owned by the existing page", () => {
  assert.ok(!shared.includes("FamilyPlaceholder"));
  assert.ok(!shared.includes("data-family-media-slot"));
  assert.ok(rankings.includes('variant="compact"'));
  assert.ok(rankings.includes('variant="mobileRanking"'));
  assert.ok(!setPage.includes("PokemonSetMobileHero"), "RipDecisionPage must not replace the existing set identity header");
});

test("Rankings uses one compact shared snapshot panel and the approved view control", () => {
  assert.ok(shared.includes("data-family-snapshot"));
  assert.ok(shared.includes("Math.min(families.length, 7)"));
  assert.ok(familyStyles.includes("repeat(2, minmax(0, 1fr))"));
  assert.ok(familyStyles.includes("repeat(3, minmax(0, 1fr))"));
  assert.ok(familyStyles.includes("repeat(var(--family-columns), minmax(0, 1fr))"));
  assert.ok(rankings.includes("data-set-rip-score-badge"));
  assert.ok(rankings.includes("data-ranking-insight"));
  assert.ok(cohortControl.includes(">Sets</button>"));
  assert.ok(cohortControl.includes(">Individual Products</button>"));
});

test("Rankings data surface uses the wider desktop canvas and prioritizes family capacity", () => {
  assert.ok(rankingsPage.includes("md:max-w-[84rem]"));
  assert.ok(rankings.includes('<col style={{ width: "51%" }} />'));
  assert.ok(rankings.includes('<col style={{ width: "14%" }} />'));
});

test("Set RIP score uses an accessible shared SVG outline and Tier remains separate", () => {
  const scoreBadge = rankings.slice(rankings.indexOf("function SetRipScoreBadge"), rankings.indexOf("function SetTierMark"));
  assert.ok(scoreBadge.includes("<svg"));
  assert.ok(scoreBadge.includes("<polygon"));
  assert.ok(scoreBadge.includes('aria-hidden="true"'));
  assert.ok(scoreBadge.includes("formatModeScore"), "score remains real DOM text");
  assert.ok(!scoreBadge.includes("clip-path"));
  assert.ok(rankings.includes("data-set-tier-mark"));
  assert.ok(rankings.includes("<SetRipScoreBadge setRip={target?.setRipV1} tier={tier} compact />"), "mobile reuses the score component");
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
