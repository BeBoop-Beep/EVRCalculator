import assert from "node:assert/strict";
import test from "node:test";

import {
  CONSTITUENTS_AVAILABLE,
  CONSTITUENTS_NOT_APPLICABLE,
  isEnumerableSeries,
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
