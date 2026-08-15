import assert from "node:assert/strict";
import test from "node:test";
import { RANK_CONFIG } from "../../constants/rankConfig.mjs";
import { getRipTierPresentation } from "./ripTierPresentation.mjs";

test("every canonical tier uses the existing rank palette", () => {
  for (const [tier, config] of Object.entries(RANK_CONFIG)) {
    const presentation = getRipTierPresentation(tier);
    assert.equal(presentation.tier, tier);
    assert.equal(presentation.color, config.color);
    assert.equal(presentation.label, `${tier} Tier`);
  }
});

test("tier treatment is independent of score category", () => {
  const financialA = getRipTierPresentation("A", { strength: "supporting" });
  const collectorA = getRipTierPresentation("A", { strength: "supporting" });
  assert.deepEqual(financialA, collectorA);
  assert.notEqual(financialA.color, RANK_CONFIG.S.color);
  assert.equal(getRipTierPresentation(null).tier, null);
});
