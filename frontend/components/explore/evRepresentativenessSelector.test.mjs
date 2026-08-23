import test from "node:test";
import assert from "node:assert/strict";
import { formatEvRepPacks, formatEvRepPercent, selectEvRepresentativenessPublicV1 } from "./evRepresentativenessSelector.mjs";

const payload = {
  contractVersion: "ev_representativeness_public_v1",
  methodVersion: "ev_representativeness_v1",
  calculationRunId: "run-A",
  typicalCapture: 0.209,
  top1OutcomeEvShare: 0.641,
  realizationHorizon: { packCount: 2812, status: "confirmed" },
  convergenceHorizon: { packCount: 5906, status: "confirmed" },
  realizationByPackCount: [
    { packCount: 6, probabilityAtLeast80PercentEv: 0.2 },
    { packCount: 1, probabilityAtLeast80PercentEv: 0.073 },
  ],
};

test("selects and formats the exact same-run public V1 contract", () => {
  const selected = selectEvRepresentativenessPublicV1(payload, "run-A");
  assert.equal(formatEvRepPercent(selected.typicalCapture), "20.9%");
  assert.equal(formatEvRepPercent(selected.top1OutcomeEvShare), "64.1%");
  assert.equal(formatEvRepPacks(selected.realizationHorizon.packCount), "2,812 packs");
  assert.deepEqual(selected.realizationByPackCount.map((row) => row.packCount), [1, 6]);
});

test("rejects stale runs and future method contracts", () => {
  assert.equal(selectEvRepresentativenessPublicV1(payload, "run-B"), null);
  assert.equal(selectEvRepresentativenessPublicV1({ ...payload, methodVersion: "ev_representativeness_v2" }, "run-A"), null);
});

test("does not promote an unconfirmed horizon", () => {
  const selected = selectEvRepresentativenessPublicV1({
    ...payload,
    convergenceHorizon: { packCount: 500, status: "confirmation_did_not_ratify" },
  }, "run-A");
  assert.equal(selected.convergenceHorizon, null);
});

test("missing values remain unavailable rather than fabricated", () => {
  assert.equal(formatEvRepPacks(null), "Unavailable");
  assert.equal(formatEvRepPercent(null), "—");
});
