import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const source = fs.readFileSync(path.join(process.cwd(), "components/pokemon/card-detail/PokemonCardDetailClient.jsx"), "utf8");
const grid = fs.readFileSync(path.join(process.cwd(), "components/explore/RipStatisticsPageClient.jsx"), "utf8");
const page = fs.readFileSync(path.join(process.cwd(), "app/TCGs/Pokemon/Sets/[setSlug]/Cards/[cardId]/page.js"), "utf8");

test("Cards tab uses an accessible Next Link and carries active set slug", () => {
  assert.match(grid, /<Link href=\{detailHref/);
  assert.match(grid, /aria-label=\{`View \$\{name\} card details`\}/);
  assert.match(grid, /detailSetSlug: activeSetSlug/);
  assert.match(grid, /prefetch=\{false\}/);
});

test("variant selection updates query state without changing canonical card", () => {
  assert.match(source, /getPokemonCardDetail\(detail\.set\.id, detail\.card\.id, variantId\)/);
  assert.match(source, /router\.replace\(`/);
  assert.match(source, /\?variant=\$\{encodeURIComponent\(variantId\)\}/);
  assert.match(source, /role="radiogroup"/);
  assert.match(source, /aria-checked=/);
});

test("selection-required and unavailable cards retain identity without fake Chase values", () => {
  assert.match(source, /variantSelection\.state === "selection_required"/);
  assert.match(source, /Choose a printing to see Chase economics/);
  assert.match(source, /Modeled Chase data is unavailable for this card/);
  assert.match(source, /\{chase\.available \? <>/);
});

test("journey, product economics, missing-price guard, and disclosure are present", () => {
  for (const label of ["50%", "75%", "90%", "95%", "Choose how youâ€™d open it", "What would you spend?", "Opening vs buying", "gross_market_value"]) {
    assert.ok(source.includes(label), `missing ${label}`);
  }
  assert.match(source, /Number\(chase\.currentTargetMarketPrice\) > 0/);
  assert.match(source, /role="img"/);
  assert.doesNotMatch(source, /Overall RIP|Financial RIP|Collector Appeal|RIP Tier/);
});

test("canonical metadata excludes the variant query", () => {
  assert.match(page, /const path = `\/TCGs\/Pokemon\/Sets\/\$\{encodeURIComponent\(detail\.set\.slug\)\}\/Cards\/\$\{encodeURIComponent\(detail\.card\.id\)\}`/);
  assert.doesNotMatch(page, /path.*variant/);
  assert.match(page, /notFound\(\)/);
});
