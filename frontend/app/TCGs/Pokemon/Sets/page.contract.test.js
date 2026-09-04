const fs = require("fs");
const path = require("path");
const test = require("node:test");
const assert = require("node:assert/strict");

const pagePath = path.resolve(__dirname, "page.js");

// Catalog membership is broader than public analytics eligibility. Sword &
// Shield sets have real catalog/card/market identities even while their RIP
// opening models remain behind the stricter analytics gate.

test("Sets catalog does not apply the public-analytics eligibility gate", () => {
  const source = fs.readFileSync(pagePath, "utf8");

  assert.ok(
    !source.includes("isHiddenFromPublicPokemonSetsCatalog"),
    "catalog visibility must not be coupled to the SWSH analytics hide"
  );
  assert.ok(
    !source.includes("isPublicAnalyticsEligiblePokemonSet"),
    "catalog visibility must not be coupled to RIP/public-analytics eligibility"
  );
  assert.ok(
    source.includes("sets = summaries.filter((setSummary) => setSummary?.id && setSummary?.name);"),
    "catalog should keep every valid set summary returned by the catalog source"
  );
  assert.ok(
    !/era\s*===\s*["'`]Sword/i.test(source),
    "must not replace the removed shared gate with a one-off Sword & Shield era check"
  );
});

test("Sets catalog keeps its genuine-empty state after removing the analytics filter", () => {
  const source = fs.readFileSync(pagePath, "utf8");

  assert.ok(source.includes("groupedEras.length === 0"));
  assert.ok(source.includes("No Pokémon sets available yet."));
  assert.ok(source.includes("const groupedEras = groupSetsByEra(sets);"));
});
