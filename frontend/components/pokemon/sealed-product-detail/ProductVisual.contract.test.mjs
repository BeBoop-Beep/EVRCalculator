import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { resolveLooseBoosterPackArtwork } from "../../../lib/pokemon/pokemonBoosterPackAssets.mjs";

const source = fs.readFileSync(new URL("./SealedProductDetailClient.jsx", import.meta.url), "utf8");

test("Ascended Heroes loose pack falls back to its registered local artwork", () => {
  assert.equal(resolveLooseBoosterPackArtwork({ productImageUrl: null, setCanonicalKey: "ascendedHeroes" })?.src, "/images/pokemon/booster-packs/ascendedHeroes.webp");
});

test("database product artwork retains precedence", () => {
  assert.deepEqual(resolveLooseBoosterPackArtwork({ productImageUrl: "https://images.example/pack.webp", setCanonicalKey: "ascendedHeroes" }), { src: "https://images.example/pack.webp", source: "product" });
});

test("the mounted visual limits registry fallback to loose-pack families", () => {
  assert.match(source, /product\.productFamily === "loose_booster_pack"/);
  assert.match(source, /loosePack\s*\?\s*resolveLooseBoosterPackArtwork/);
  assert.doesNotMatch(source, /productFamily.*elite_trainer_box.*resolveLooseBoosterPackArtwork/);
});

test("unknown registry entry stays unavailable and image failure resets per product and asset", () => {
  assert.equal(resolveLooseBoosterPackArtwork({ productImageUrl: null, setCanonicalKey: "unknownSet" }), null);
  assert.match(source, /\[product\.id, artwork\?\.src\]/);
  assert.match(source, /data-product-image-placeholder/);
});
