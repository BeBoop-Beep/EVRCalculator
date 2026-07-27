import test from "node:test";
import assert from "node:assert/strict";

import { getAllCardsDirectionLabel, getEffectiveRarityFilter, resolveCardsRequest } from "./cardsControls.mjs";

test("ordinary sorts do not depend on the selected movement timeframe", () => {
  for (const activeSortMode of ["set-number", "name", "current-price"]) {
    const sevenDay = resolveCardsRequest({ selectedTimeframe: "7D", activeSortMode, activeSortDirection: "asc" });
    const thirtyDay = resolveCardsRequest({ selectedTimeframe: "30D", activeSortMode, activeSortDirection: "asc" });
    assert.deepEqual(sevenDay, thirtyDay);
    assert.equal(sevenDay.movementSort, null);
  }
});

test("price direction maps to the existing null-safe server sorts", () => {
  assert.equal(resolveCardsRequest({ activeSortMode: "current-price", activeSortDirection: "asc" }).sort, "market-price-asc");
  assert.equal(resolveCardsRequest({ activeSortMode: "current-price", activeSortDirection: "desc" }).sort, "market-price-desc");
});

test("gainers and losers use the selected timeframe", () => {
  assert.deepEqual(
    resolveCardsRequest({ selectedSubTab: "market-movers", selectedTimeframe: "7D", activeSortDirection: "gainers" }),
    { sort: "set-number", movementSort: "7d-movers", movementFilter: "all", sortDirection: "desc" }
  );
  assert.deepEqual(
    resolveCardsRequest({ selectedSubTab: "market-movers", selectedTimeframe: "7D", activeSortDirection: "losers" }),
    { sort: "set-number", movementSort: "7d-movers", movementFilter: "all", sortDirection: "asc" }
  );
  assert.deepEqual(
    resolveCardsRequest({ selectedSubTab: "market-movers", selectedTimeframe: "30D", activeSortDirection: "gainers" }),
    { sort: "set-number", movementSort: "30d-gainers", movementFilter: "all", sortDirection: "desc" }
  );
  assert.deepEqual(
    resolveCardsRequest({ selectedSubTab: "market-movers", selectedTimeframe: "30D", activeSortDirection: "losers" }),
    { sort: "set-number", movementSort: "30d-decliners", movementFilter: "all", sortDirection: "asc" }
  );
});

test("All Cards direction labels describe the active comparator", () => {
  assert.equal(getAllCardsDirectionLabel("set-number", "asc"), "1 → 193");
  assert.equal(getAllCardsDirectionLabel("set-number", "desc"), "193 → 1");
  assert.equal(getAllCardsDirectionLabel("name", "asc"), "A → Z");
  assert.equal(getAllCardsDirectionLabel("name", "desc"), "Z → A");
  assert.equal(getAllCardsDirectionLabel("current-price", "asc"), "Low → High");
  assert.equal(getAllCardsDirectionLabel("current-price", "desc"), "High → Low");
});

test("All Cards rarity remains stored but is not applied to Market Movers", () => {
  const selectedRarity = "Special Illustration Rare";
  assert.equal(getEffectiveRarityFilter("all-cards", selectedRarity), selectedRarity);
  assert.equal(getEffectiveRarityFilter("market-movers", selectedRarity), null);
  assert.equal(getEffectiveRarityFilter("all-cards", selectedRarity), selectedRarity);
});
