import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(new URL("./PokemonCardDetailClient.jsx", import.meta.url), "utf8");

test("Premium section is additive beneath existing Plus intelligence", () => {
  const card = source.indexOf("<CardIntelligence detail={detail}");
  const products = source.indexOf("<ProductEconomics chase={chase}");
  const premium = source.indexOf("<ChaseEfficiencySection state={chaseEfficiencyState}");
  assert.ok(products > -1 && card > -1 && premium > card);
  assert.match(source, /hasIndexPlusAccess\(user\?\.index_plan\)/);
  assert.match(source, /hasIndexFeatureAccess\(user\?\.index_plan, FEATURE_CARD_CHASE_EFFICIENCY\)/);
});

test("variant switching drives a distinct authenticated Premium request", () => {
  assert.match(source, /getPokemonCardChaseEfficiency\(detail\.set\.id, detail\.card\.id, detail\.selectedVariantId/);
  assert.match(source, /detail\.selectedVariantId\]\);/);
  assert.match(source, /if \(!premiumEntitled\).*return undefined/);
});

test("rank, economics and copy distinctions are explicit", () => {
  for (const label of ["Rank Context", "Overall", "Era", "Set", "Card Market Price", "Best Verified Opening Route", "Effective Pack Cost", "Loose Pack Price", "Chance at Buy Price", "50% Chase Spend", "50% Cost Multiple", "Chase Efficiency", "Product Chase Economics"]) assert.ok(source.includes(label), label);
  assert.match(source, /How rare is this exact printing/);
  assert.match(source, /How favorable is hunting it relative to buying and other cards/);
  assert.match(source, /How does the journey change depending on which sealed product you open/);
});

test("milestone dollars come directly from backend actual-route output", () => {
  assert.match(source, /dollars\[`\$\{threshold\}%`\] = milestones\[String\(threshold\)\]\?\.spend/);
  assert.match(source, /milestoneDollars=\{dollars\}/);
  assert.doesNotMatch(source, /milestoneDollars.*\*|packs.*\*.*price/);
});

test("Premium lock uses teal rather than amber", () => {
  const start = source.indexOf("function PremiumLock()");
  const end = source.indexOf("const rarityRankLabel", start);
  const lock = source.slice(start, end);
  assert.match(lock, /var\(--accent\)/);
  assert.doesNotMatch(lock, /amber|yellow/);
});
