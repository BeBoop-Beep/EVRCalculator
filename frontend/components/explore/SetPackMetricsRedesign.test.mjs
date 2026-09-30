import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { SET_PACK_COLUMNS, familyBestOpenPresentation, filterPackEconomicsSets, formatPackEconomicsValue, sortPackEconomicsSets } from "./setPackMetricsSelector.mjs";

const source = fs.readFileSync(new URL("./SetPackMetrics.jsx", import.meta.url), "utf8");
const hub = fs.readFileSync(new URL("./SetRankingsHub.jsx", import.meta.url), "utf8");

test("Pack Economics exposes the exact redesigned column contract", () => {
  assert.deepEqual(SET_PACK_COLUMNS.map((column) => column[1]), ["Families", "Products", "Avg Pack Cost", "EV / Pack", "Modeled Return", "Recover Cost", "Entertainment Cost", "Best-Open Price"]);
  assert.ok(source.includes('changeSort("setName")}>Set'));
  assert.doesNotMatch(source, /Typical Opening|Typical Retention|typicalOpening|typicalRetention/);
});

test("Family and Product detail uses sibling table rows in the parent colgroup", () => {
  assert.match(source, /data-pack-family-row/);
  assert.match(source, /data-pack-product-row/);
  assert.match(source, /<FamilyRow/);
  assert.match(source, /<ProductRow/);
  assert.doesNotMatch(source, /colSpan=|<table[^>]*data-family-economics/);
});

test("single-SKU and multi-SKU Best-Open semantics remain exact", () => {
  const single = { bestOpenDisplayMode: "single", productCount: 1, products: [{ bestOpenPrice: 79.41 }] };
  const multiple = { bestOpenDisplayMode: "multiple", productCount: 2, products: [{ bestOpenPrice: 54.31 }, { bestOpenPrice: 55.29 }] };
  assert.equal(familyBestOpenPresentation(single), "$79.41");
  assert.equal(familyBestOpenPresentation(multiple), "2 prices");
  assert.notEqual(familyBestOpenPresentation(multiple), "$54.80");
  assert.equal(formatPackEconomicsValue("bestOpenPrice", multiple.products[0].bestOpenPrice), "$54.31");
  assert.equal(formatPackEconomicsValue("bestOpenPrice", multiple.products[1].bestOpenPrice), "$55.29");
});

test("Set sorting and search are local and preserve Era filtering", () => {
  const sets = [{ setName: "Beta", modeledReturnOnSpend: .4, era: { eraName: "Two" } }, { setName: "Alpha", modeledReturnOnSpend: .6, era: { eraName: "One" } }];
  assert.deepEqual(sortPackEconomicsSets(sets).map((row) => row.setName), ["Alpha", "Beta"]);
  assert.deepEqual(filterPackEconomicsSets(sets, "alp", "One").map((row) => row.setName), ["Alpha"]);
});

test("Pack Economics selects public preview or paid detail on its tab and retains last-good state", () => {
  assert.match(hub, /view === "packEconomics" && packState\.status === "idle"/);
  assert.match(hub, /readPackEconomics\(\{ sessionCache, force \}\)/);
  assert.match(hub, /readPublicPackEconomicsPreview\(\{ sessionCache, force \}\)/);
  assert.match(hub, /beginLastGoodRefresh/);
  assert.match(hub, /failLastGoodRefresh/);
  const loaderStart = hub.indexOf("const loadPackEconomics");
  const loader = hub.slice(loaderStart, hub.indexOf("  useEffect(", loaderStart));
  assert.match(loader, /canViewRankingsIntelligence\s*\? await readPackEconomics/);
  assert.match(source, /key === "averagePackCostPerPack"/);
  assert.match(source, /<LockedMetric \/>/);
});

test("independent Best-Open freshness is visible and neutral", () => {
  assert.match(source, /Best-Open as of/);
  assert.match(source, /independently dated/);
  assert.doesNotMatch(source, /text-red|error.*best.?open/i);
});
