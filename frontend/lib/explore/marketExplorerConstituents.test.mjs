import assert from "node:assert/strict";
import test from "node:test";

import {
  CONSTITUENTS_AVAILABLE,
  CONSTITUENTS_NOT_APPLICABLE,
  CONSTITUENT_MOVEMENT_WINDOWS,
  getConstituentChange,
  isEnumerableSeries,
  resolveSeriesAsset,
  resolveSeriesConstituents,
} from "./marketExplorerConstituents.mjs";

test("a parent market that publishes a roster can be inspected; one that does not cannot", () => {
  // "Parent" used to mean "never enumerated", which was right while no parent
  // published composition. Total Sealed now does, and it is the only place the
  // `otherSealed` residual products appear — so enumerability has to follow the
  // published roster rather than the isParent flag.
  const totalSealed = {
    key: "sealedMarket",
    label: "Sealed Market",
    isParent: true,
    currentConstituents: {
      asOf: "2026-08-25",
      totalCount: 139,
      isComplete: true,
      idField: "sealedProductId",
      topConstituents: [
        { sealedProductId: "p-1", productName: "ETB", marketPrice: 500 },
        { sealedProductId: "p-2", productName: "Half Booster Box", marketPrice: 250 },
      ],
    },
  };
  const rawParent = { key: "raw", label: "Raw Card Market", isParent: true };

  assert.equal(isEnumerableSeries(totalSealed), true);
  assert.equal(isEnumerableSeries(rawParent), false);

  const inspected = resolveSeriesConstituents(totalSealed);
  assert.equal(inspected.availability, CONSTITUENTS_AVAILABLE);
  assert.equal(inspected.totalCount, 139);
  assert.equal(inspected.source, "prepared");

  const summarised = resolveSeriesConstituents(rawParent);
  assert.equal(summarised.availability, CONSTITUENTS_NOT_APPLICABLE);
  assert.match(summarised.reason, /parent market/);
});

// --- Constituent movement ---------------------------------------------------

const movingCards = {
  key: "card:raw:specialIllustrationRare",
  label: "Special Illustration Rare",
  currentConstituents: {
    idField: "canonicalCardId",
    totalCount: 2,
    isComplete: true,
    topConstituents: [
      {
        canonicalCardId: "umbreon",
        cardName: "Umbreon ex",
        marketPrice: 1477.11,
        // A bare number per window; null where there is no comparable
        // observation. The boundary dates live on the market, not the row.
        changes: { "1D": 0.4, "7D": 4.8, "30D": -12.5, "3M": null },
      },
      {
        canonicalCardId: "mew",
        cardName: "Mew ex",
        marketPrice: 978,
        changes: { "1D": -0.1, "7D": -2.1, "30D": 3.3, "3M": 0 },
      },
    ],
  },
};

test("the movement column follows the selected window", () => {
  for (const window of ["1D", "7D", "30D", "3M"]) {
    const model = resolveSeriesConstituents(movingCards, { movementWindow: window });
    const column = model.columns.at(-1);
    assert.equal(column.change, true);
    assert.equal(column.window, window);
    assert.equal(column.label, `${window} Change`);
    assert.equal(column.align, "right");
  }
});

test("7D is the default and an unknown window falls back to it rather than throwing", () => {
  assert.equal(resolveSeriesConstituents(movingCards).movementWindow, "7D");
  assert.equal(
    resolveSeriesConstituents(movingCards, { movementWindow: "6M" }).movementWindow,
    "7D"
  );
});

test("each constituent moves on its own, never on the market's aggregate", () => {
  const model = resolveSeriesConstituents(movingCards, { movementWindow: "7D" });
  const percents = model.rows.map((row) => getConstituentChange(row, "7D"));
  assert.deepEqual(percents, [4.8, -2.1]);
});

test("an unavailable window is null so the table can print a dash, never 0.00%", () => {
  const model = resolveSeriesConstituents(movingCards, { movementWindow: "3M" });
  const [umbreon, mew] = model.rows;
  assert.equal(getConstituentChange(umbreon, "3M"), null, "no comparable history -> null");
  // A genuine zero is NOT null: the price really did not move.
  assert.equal(getConstituentChange(mew, "3M"), 0);
});

test("a missing changes map degrades to null rather than to a fabricated zero", () => {
  const noMovement = {
    key: "sealed:eliteTrainerBox",
    label: "ETBs",
    currentConstituents: {
      idField: "sealedProductId",
      totalCount: 1,
      isComplete: true,
      topConstituents: [{ sealedProductId: "p1", productName: "ETB", marketPrice: 50 }],
    },
  };
  const model = resolveSeriesConstituents(noMovement, { movementWindow: "7D" });
  assert.equal(model.availability, CONSTITUENTS_AVAILABLE);
  assert.equal(getConstituentChange(model.rows[0], "7D"), null);
  // Stated, so the panel can say WHY the column is empty.
  assert.equal(model.hasMovement, false);
});

test("prepared and dynamic markets expose one identical movement contract", () => {
  const dynamic = {
    key: "query:abc",
    label: "Custom",
    spec: { asset: "cards", mode: "chase" },
    currentConstituents: [
      {
        canonicalCardId: "umbreon",
        rank: 1,
        marketPrice: 1477.11,
        changes: { "7D": 4.8 },
      },
    ],
  };
  const dynamicModel = resolveSeriesConstituents(dynamic, { movementWindow: "7D" });
  const preparedModel = resolveSeriesConstituents(movingCards, { movementWindow: "7D" });
  // Same column contract, same accessor, same shape — the table does not care
  // which lane its target came from.
  assert.equal(dynamicModel.columns.at(-1).label, preparedModel.columns.at(-1).label);
  assert.equal(dynamicModel.hasMovement, true);
  assert.equal(getConstituentChange(dynamicModel.rows[0], "7D"), 4.8);
});

test("the frontend windows mirror the backend contract exactly", () => {
  assert.deepEqual([...CONSTITUENT_MOVEMENT_WINDOWS], ["1D", "7D", "30D", "3M"]);
});

test("the sealed PARENT's roster resolves as sealed, not as cards", () => {
  // `sealedMarket` does not match the `sealed:` child prefix, so convention
  // alone resolved the Sealed Market parent to cards and would have rendered
  // its products under Card / Rarity headings. The published roster states
  // its own id field, and that fact wins over the naming convention.
  const totalSealed = {
    key: "sealedMarket",
    label: "Sealed Market",
    isParent: true,
    currentConstituents: {
      idField: "sealedProductId",
      totalCount: 1,
      isComplete: true,
      topConstituents: [{ sealedProductId: "p1", productName: "ETB", marketPrice: 50 }],
    },
  };
  assert.equal(resolveSeriesAsset(totalSealed), "sealed");
  const model = resolveSeriesConstituents(totalSealed);
  assert.equal(model.idField, "sealedProductId");
  assert.deepEqual(
    model.columns.map((column) => column.label),
    ["Rank", "Product", "Set", "Family", "Price", "7D Change"]
  );
});

test("a null percentage is never coerced into a confident zero", () => {
  // `Number(null)` is 0 and `Number("")` is 0, so a coerce-first accessor
  // turns "no comparable observation" into "the price did not move" — the
  // single most misleading thing this column could print.
  for (const raw of [null, undefined, "", "abc", NaN, Infinity, {}, []]) {
    assert.equal(getConstituentChange({ changes: { "7D": raw } }, "7D"), null, String(raw));
  }
  // ...while a real zero survives as a real zero.
  assert.equal(getConstituentChange({ changes: { "7D": 0 } }, "7D"), 0);
  // -0 is a real observed zero too; the accessor must not reject it.
  assert.equal(Object.is(getConstituentChange({ changes: { "7D": -0.0 } }, "7D"), -0), true);
});

test("window boundary dates are read from the market, not from a row", () => {
  const series = {
    key: "card:raw:specialIllustrationRare",
    currentConstituents: {
      idField: "canonicalCardId",
      totalCount: 1,
      isComplete: true,
      movementWindows: {
        "7D": { available: true, startDate: "2026-08-18", endDate: "2026-08-25" },
        "30D": { available: false, startDate: null, endDate: "2026-08-25" },
      },
      topConstituents: [{ canonicalCardId: "c1", marketPrice: 10, changes: { "7D": 1.5 } }],
    },
  };
  assert.equal(resolveSeriesConstituents(series, { movementWindow: "7D" }).movementWindowMeta.startDate, "2026-08-18");
  assert.equal(resolveSeriesConstituents(series, { movementWindow: "30D" }).movementWindowMeta.available, false);
});
