import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs
  .readFileSync(path.resolve(here, "RipStatisticsPageClient.jsx"), "utf8")
  .replace(/\r\n/g, "\n");

const row = source.slice(
  source.indexOf("function DecisionSignalRow("),
  source.indexOf("function DecisionSignalsCard(")
);
const card = source.slice(
  source.indexOf("function DecisionSignalsCard("),
  source.indexOf("// A Profit / Safety / Stability card.")
);

test("each pillar is a divider-separated row, not its own card, below desktop", () => {
  assert.ok(row.includes("max-desk:rounded-none"));
  assert.ok(row.includes("max-desk:border-0"));
  assert.ok(row.includes("max-desk:border-b"));
  assert.ok(row.includes("max-desk:px-0"));
  assert.ok(row.includes("max-desk:last:border-b-0"), "the final row does not draw a trailing divider");
  // Desktop keeps the bordered inner card exactly as it is.
  assert.ok(row.includes("set-glass-inner"), "the desktop surface class is preserved");
  assert.ok(row.includes("rounded-xl border border-[var(--border-subtle)] px-3 py-3"), "the desktop border is preserved");
});

test("every score, tier, rank and interpretation survives", () => {
  for (const token of ["signal.label", "signal.scoreText", "signal.rankTier", "RankBadge", "summaryText", "parsedRank"]) {
    assert.ok(row.includes(token), `${token} must remain`);
  }
});

test("Also tracked and Opening Experience are preserved", () => {
  assert.ok(card.includes("Also tracked"));
  assert.ok(card.includes("openingRows.map"));
});

test("the compact stack removes the gap that made each row read as a card", () => {
  assert.equal(
    (card.match(/className="grid gap-2 max-desk:gap-0"/g) || []).length,
    2,
    "both the pillar stack and the Also-tracked stack sit flush below desktop"
  );
  assert.ok(!card.includes('className="grid gap-2"'), "no row container may keep the desktop-only gap below desktop");
});

test("the target is Decision Signals on Overview, not the deeper Insights module", () => {
  // Brief section 8's Profit / Safety / Stability / Opening Experience target.
  // RipScoreBreakdownModule on Insights is a separate surface and is untouched.
  assert.ok(source.includes("function DecisionSignalsCard("), "the Overview card is the one recomposed");
  const breakdownStart = source.indexOf("function RipScoreBreakdownModule(");
  if (breakdownStart >= 0) {
    const breakdown = source.slice(breakdownStart, breakdownStart + 4000);
    assert.ok(
      !breakdown.includes("max-desk:border-0"),
      "the Insights breakdown module must not be recomposed by this task"
    );
  }
});
