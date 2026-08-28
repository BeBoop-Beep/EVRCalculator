import assert from "node:assert/strict";
import test from "node:test";
import { normaliseRipStatisticsPayload as normalisePayload } from "./ripStatisticsNormalizer.mjs";

test("productFamilyRankings survives RIP statistics normalization unchanged", () => {
  const rankings = { calculationRunId: "run-current", families: { booster_box: { products: [{ sealedProductId: "sku-1" }] } } };
  const normalized = normalisePayload({ targets: [], productFamilyRankings: rankings });
  assert.equal(normalized.productFamilyRankings, rankings);
  assert.equal(normalized.productFamilyRankings.families.booster_box.products.length, 1);
});

test("Overall rankings do not travel through RIP statistics normalization", () => {
  const normalized = normalisePayload({ targets: [], overallProductRankings: { cohorts: {} } });
  assert.equal(normalized.overallProductRankings, undefined);
});

test("authoritative Era Set Strength survives RIP statistics normalization unchanged", () => {
  const eraSetStrengthV1 = {
    methodologyVersion: "era_set_strength_v1_equal_set_mean_of_set_rip_v1",
    cohortSize: 2,
    eras: [
      { eraName: "Mega Evolution", score: 61.749256, rank: 1, modeledSetCount: 6 },
      { eraName: "Scarlet & Violet", score: 45.673312, rank: 2, modeledSetCount: 16 },
    ],
  };
  const normalized = normalisePayload({ targets: [], eraSetStrengthV1 });
  assert.equal(normalized.eraSetStrengthV1, eraSetStrengthV1);
  assert.deepEqual(normalized.eraSetStrengthV1.eras, eraSetStrengthV1.eras);
});

test("relational era records are normalized to renderable target fields", () => {
  const era = {
    id: "era-1",
    name: "Scarlet & Violet",
    canonical_key: "scarlet-and-violet",
    sort_order: 1,
  };
  const normalized = normalisePayload({
    targets: [{ target_id: "set-1", name: "Test Set", era }],
    default_target: { target_id: "set-1", name: "Test Set", era },
  });

  assert.equal(normalized.targets[0].era, "Scarlet & Violet");
  assert.equal(normalized.targets[0].era_id, "era-1");
  assert.equal(normalized.default_target.era, "Scarlet & Violet");
  assert.equal(normalized.default_target.era_id, "era-1");
});

test("string era fields retain their existing target shape", () => {
  const target = { target_id: "set-1", era: "Sword & Shield" };
  const normalized = normalisePayload({ targets: [target] });

  assert.equal(normalized.targets[0], target);
  assert.equal(normalized.targets[0].era, "Sword & Shield");
});
