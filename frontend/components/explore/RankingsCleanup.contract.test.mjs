import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const source = fs.readFileSync(path.resolve("components/explore/ExploreTableClient.jsx"), "utf8");
const badgeSource = fs.readFileSync(path.resolve("components/explore/RipScoreBadge.jsx"), "utf8");
const familySource = fs.readFileSync(path.resolve("components/explore/SetRipFamilyBreakdown.jsx"), "utf8");

test("main Set RIP badge keeps its canonical score and uses the larger /10 suffix", () => {
  assert.ok(source.includes("<RipScoreBadge score={canonicalOverall.publicScore} tier={tier}"));
  assert.ok(badgeSource.includes("formatModeScore(score, SCORE_KIND_PUBLIC)"));
  assert.ok(badgeSource.includes('text-[9px] text-[var(--text-secondary)]">/ 10'));
  assert.equal(badgeSource.includes('text-[8px] text-[var(--text-secondary)]">/ 10'), false);
});

test("Sets search uses Market styling and filters names without deriving rank", () => {
  assert.ok(source.includes('placeholder="Search sets..."'));
  assert.ok(source.includes("<TableSearchInput"));
  assert.ok(source.includes("target?.name"));
  assert.ok(source.includes("const modeRank = canonicalOverall.rank"));
});

test("Format Strength remains qualitative and renders no aggregate score", () => {
  const insight = source.slice(source.indexOf("function RankingInsight"), source.indexOf("function SortableHeader"));
  assert.ok(insight.includes("whySetRanks(setRip)"));
  assert.ok(insight.includes("{heading}"));
  assert.ok(insight.includes("{explanation}"));
  assert.equal(insight.includes("formatModeScore"), false);
  assert.equal(insight.includes("/ 10"), false);
});

test("Sets uses one dense header row with only the requested family help", () => {
  assert.equal(source.includes("Product Family Snapshot"), false);
  assert.equal(source.includes('scope="colgroup"'), false);
  assert.equal(source.includes("rowSpan={2}"), false);
  assert.ok(source.includes("column.info ? <InfoPopover"));
  assert.ok(familySource.includes('key: "pc-etb"') && familySource.includes('key: "half-box"'));
  assert.equal((familySource.match(/info: /g) || []).length, 2);
});
