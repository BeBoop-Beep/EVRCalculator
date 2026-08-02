import test from "node:test";
import assert from "node:assert/strict";
import { compactSealedProductLabel, selectSealedProduct, selectSealedWindow } from "./sealedMarketTrendSelector.mjs";

test("variants stay separate and default selection is deterministic", () => {
  const products = [
    { sealedProductId: "a", productFamily: "elite_trainer_box", variantLabel: "Koraidon" },
    { sealedProductId: "b", productFamily: "pokemon_center_elite_trainer_box", variantLabel: "Koraidon" },
  ];
  assert.equal(selectSealedProduct({ products, defaultProductId: "b" }, null).sealedProductId, "b");
  assert.equal(compactSealedProductLabel(products[0]), "ETB — Koraidon");
  assert.equal(compactSealedProductLabel(products[1]), "PC ETB — Koraidon");
});

test("window filtering defaults cleanly to prepared 30D movement", () => {
  const product = {
    priceAsOf: "2026-02-01",
    movements: { "30D": { status: "available", requestedStartDate: "2026-01-02" } },
    history: [{ date: "2026-01-01" }, { date: "2026-01-02" }, { date: "2026-02-01" }],
  };
  assert.deepEqual(selectSealedWindow(product, "30D").history.map((point) => point.date), ["2026-01-02", "2026-02-01"]);
});
