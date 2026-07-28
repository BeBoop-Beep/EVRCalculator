import test from "node:test";
import assert from "node:assert/strict";

import {
  DEFAULT_MARKET_MOVER_METRIC,
  MARKET_MOVER_METRIC_OPTIONS,
  getAllCardsDirectionLabel,
  getEffectiveRarityFilter,
  normalizeMarketMoverMetric,
  resolveCardsRequest,
} from "./cardsControls.mjs";

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
    { sort: "set-number", movementSort: "7d-movers", movementMetric: "percent", movementFilter: "all", sortDirection: "desc" }
  );
  assert.deepEqual(
    resolveCardsRequest({ selectedSubTab: "market-movers", selectedTimeframe: "7D", activeSortDirection: "losers" }),
    { sort: "set-number", movementSort: "7d-movers", movementMetric: "percent", movementFilter: "all", sortDirection: "asc" }
  );
  assert.deepEqual(
    resolveCardsRequest({ selectedSubTab: "market-movers", selectedTimeframe: "30D", activeSortDirection: "gainers" }),
    { sort: "set-number", movementSort: "30d-gainers", movementMetric: "percent", movementFilter: "all", sortDirection: "desc" }
  );
  assert.deepEqual(
    resolveCardsRequest({ selectedSubTab: "market-movers", selectedTimeframe: "30D", activeSortDirection: "losers" }),
    { sort: "set-number", movementSort: "30d-decliners", movementMetric: "percent", movementFilter: "all", sortDirection: "asc" }
  );
});

test("Market Movers defaults to percentage ranking", () => {
  assert.equal(DEFAULT_MARKET_MOVER_METRIC, "percent");
  assert.equal(
    resolveCardsRequest({ selectedSubTab: "market-movers", activeSortDirection: "gainers" }).movementMetric,
    "percent"
  );
  for (const value of [undefined, null, "", "nonsense", "PERCENT"]) {
    assert.equal(normalizeMarketMoverMetric(value), "percent");
  }
  assert.equal(normalizeMarketMoverMetric("dollar"), "dollar");
});

test("metric is independent of direction and timeframe", () => {
  for (const selectedTimeframe of ["7D", "30D"]) {
    for (const activeSortDirection of ["gainers", "losers"]) {
      const percent = resolveCardsRequest({
        selectedSubTab: "market-movers",
        selectedTimeframe,
        activeSortDirection,
        activeMovementMetric: "percent",
      });
      const dollar = resolveCardsRequest({
        selectedSubTab: "market-movers",
        selectedTimeframe,
        activeSortDirection,
        activeMovementMetric: "dollar",
      });

      // Only the metric may differ — switching it must not move the request
      // onto a different timeframe or flip gainers/losers.
      assert.equal(percent.movementMetric, "percent");
      assert.equal(dollar.movementMetric, "dollar");
      assert.deepEqual({ ...percent, movementMetric: null }, { ...dollar, movementMetric: null });
    }
  }
});

test("metric options spell out percentage and dollar for assistive tech", () => {
  assert.deepEqual(
    MARKET_MOVER_METRIC_OPTIONS.map((option) => option.value),
    ["percent", "dollar"]
  );
  assert.deepEqual(
    MARKET_MOVER_METRIC_OPTIONS.map((option) => option.label),
    ["%", "$"]
  );
  assert.deepEqual(
    MARKET_MOVER_METRIC_OPTIONS.map((option) => option.accessibleLabel),
    ["Percentage Change", "Dollar Change"]
  );
});

test("All Cards requests carry no movement metric", () => {
  for (const activeSortMode of ["set-number", "name", "current-price"]) {
    assert.equal(
      resolveCardsRequest({ activeSortMode, activeMovementMetric: "dollar" }).movementMetric,
      null
    );
  }
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
