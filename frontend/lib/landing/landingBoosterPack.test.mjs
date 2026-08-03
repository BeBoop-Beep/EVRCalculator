import test from "node:test";
import assert from "node:assert/strict";

import {
  HERO_BOOSTER_PACK_FALLBACK,
  selectHeroBoosterPackImage,
} from "./landingBoosterPack.mjs";

/**
 * The hero backdrop's asset ladder. These lock the ORDER, not a particular
 * image: the backdrop must follow whichever set is spotlighted, and must
 * disappear rather than invent something when that set has no product art.
 */

test("no payload resolves to nothing, so the hero renders unchanged", () => {
  assert.equal(selectHeroBoosterPackImage(null), null);
  assert.equal(selectHeroBoosterPackImage(undefined), null);
  assert.equal(selectHeroBoosterPackImage({}), null);
  assert.equal(selectHeroBoosterPackImage({ products: [] }), null);
});

test("products without artwork resolve to nothing rather than a placeholder", () => {
  const payload = {
    products: [
      { product_family: "booster_box", name: "Booster Box", current_price: 314 },
      { product_family: "booster_pack", name: "Booster Pack", current_price: 11 },
    ],
  };
  assert.equal(selectHeroBoosterPackImage(payload), null);
});

test("step 1 — a booster pack from the spotlight set wins over any other family", () => {
  const resolved = selectHeroBoosterPackImage({
    products: [
      { product_family: "elite_trainer_box", image_large_url: "https://img/etb.png" },
      { product_family: "booster_box", image_large_url: "https://img/box.png" },
      { product_family: "booster_pack", image_large_url: "https://img/pack.png" },
    ],
  });
  assert.equal(resolved.src, "https://img/pack.png");
  assert.equal(resolved.source, "booster_pack");
});

test("step 2 — another sealed product from the SAME set when no pack has art", () => {
  const resolved = selectHeroBoosterPackImage({
    products: [
      { product_family: "booster_pack", name: "Pack with no image" },
      { product_family: "elite_trainer_box", image_small_url: "https://img/etb.png" },
    ],
  });
  assert.equal(resolved.src, "https://img/etb.png");
  assert.equal(resolved.source, "sealed_product");
});

test("camelCase and snake_case payload shapes are both read", () => {
  assert.equal(
    selectHeroBoosterPackImage({
      products: [{ productFamily: "booster_pack", imageLargeUrl: "https://img/a.png" }],
    }).src,
    "https://img/a.png"
  );
});

test("only http(s) and root-relative sources are accepted", () => {
  const reject = (src) =>
    selectHeroBoosterPackImage({ products: [{ product_family: "booster_pack", image_url: src }] });
  assert.equal(reject("data:image/png;base64,AAAA"), null);
  assert.equal(reject("pack.png"), null);
  assert.equal(reject("   "), null);
  assert.equal(reject("/images/pack.webp").src, "/images/pack.webp");
});

test("the set name travels with the resolved image for provenance", () => {
  const resolved = selectHeroBoosterPackImage(
    { products: [{ product_family: "booster_pack", image_large_url: "https://img/p.png" }] },
    { setName: "Temporal Forces" }
  );
  assert.equal(resolved.setName, "Temporal Forces");
});

test("the static fallback is documented as absent, so step 4 applies today", () => {
  // Guards the documented state: no booster-pack asset is stored in this repo,
  // so the ladder falls through to "leave the hero as it is" rather than to a
  // permanently hardcoded Pokemon 151 image. Changing this constant is the ONLY
  // step needed to activate the fallback.
  assert.equal(HERO_BOOSTER_PACK_FALLBACK, null);
  assert.equal(selectHeroBoosterPackImage({ products: [] }), null);
});
