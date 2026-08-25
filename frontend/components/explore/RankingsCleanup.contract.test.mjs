import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const source = fs.readFileSync(path.resolve("components/explore/ExploreTableClient.jsx"), "utf8");

test("main Set RIP badge keeps its canonical score and uses the larger /10 suffix", () => {
  const badge = source.slice(source.indexOf("function SetRipScoreBadge"), source.indexOf("function SetTierMark"));
  assert.ok(badge.includes("formatModeScore(score, SCORE_KIND_PUBLIC)"));
  assert.ok(badge.includes('text-[9px] text-[var(--text-secondary)]">/ 10'));
  assert.equal(badge.includes('text-[8px] text-[var(--text-secondary)]">/ 10'), false);
});

test("Format Strength remains qualitative and renders no aggregate score", () => {
  const insight = source.slice(source.indexOf("function RankingInsight"), source.indexOf("function SortableHeader"));
  assert.ok(insight.includes("whySetRanks(setRip)"));
  assert.ok(insight.includes("{heading}"));
  assert.ok(insight.includes("{explanation}"));
  assert.equal(insight.includes("formatModeScore"), false);
  assert.equal(insight.includes("/ 10"), false);
});
