import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const read = (file) => fs.readFileSync(path.resolve(file), "utf8");
const shared = read("lib/membership/upgradeFunnel.mjs");
const planLock = read("components/membership/PlanLock.jsx");

test("shared lock primitives consume centralized panel, badge, CTA, compact, and focus styles", () => {
  for (const key of ["panelClassName", "badgeClassName", "ctaClassName", "compactClassName"])
    assert.ok(shared.includes(key), key);
  for (const key of ["panelClassName", "ctaClassName", "compactClassName"])
    assert.ok(planLock.includes(`lock.${key}`), key);
  assert.match(shared, /Index Plus[\s\S]*?tone: "gold"[\s\S]*?border-amber/);
  assert.match(shared, /Index Premium[\s\S]*?tone: "purple"[\s\S]*?border-violet/);
});

test("representative manifest locks resolve their required plan through the shared presentation", () => {
  const files = [
    "components/explore/RankedProductTablePrimitives.jsx",
    "components/explore/SetRipFamilyBreakdown.jsx",
    "components/explore/SetPackMetrics.jsx",
    "components/explore/OpeningEconomicsEras.jsx",
    "components/explore/MarketExplorerQueryBuilder.jsx",
    "components/pokemon/set-page/Market/SetMarketSignals.jsx",
    "components/pokemon/card-detail/PokemonCardDetailClient.jsx",
    "components/pokemon/sealed-product-detail/ProductRipSection.jsx",
    "components/explore/CardChaseEfficiencyRankings.jsx",
  ].map(read);
  for (const source of files) assert.match(source, /planPresentation|PlanLock|PlanBadge|PlanUpgradeLink/);
  assert.doesNotMatch(files.join("\n"), /border-\[rgba\(45,212,191[^\n]*(?:lock|RIP)/i);
});

test("locked plan text remains explicit and entitled branches render normal content", () => {
  const card = read("components/pokemon/card-detail/PokemonCardDetailClient.jsx");
  assert.match(card, /PlanBadge plan=\{INDEX_PLAN_PLUS\}/);
  assert.match(card, /PlanBadge plan=\{INDEX_PLAN_PREMIUM\}/);
  assert.match(card, /premiumEntitled \? \([\s\S]*?<ChaseEfficiencySection/);
  assert.match(card, /entitled \? \([\s\S]*?<OpeningProductsSection/);
  const explorer = read("components/explore/MarketExplorerQueryBuilder.jsx");
  assert.match(explorer, /unlocked \? "border-\[var\(--border-subtle\)\]" : lockTone\.compactClassName/);
});
