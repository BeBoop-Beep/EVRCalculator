import assert from "node:assert/strict";
import test from "node:test";

import { resolveLooseBoosterPackArtwork, resolvePokemonBoosterPackAsset } from "./pokemonBoosterPackAssets.mjs";

test("available canonical sets resolve their local camelCase WebP", () => {
  assert.equal(resolvePokemonBoosterPackAsset("paradoxRift")?.src, "/images/pokemon/booster-packs/paradoxRift.webp");
  assert.equal(resolvePokemonBoosterPackAsset("scarletAndViolet151")?.src, "/images/pokemon/booster-packs/scarletAndViolet151.webp");
});

test("missing sets return null without cross-set or external fallback", () => {
  assert.equal(resolvePokemonBoosterPackAsset("temporalForces"), null);
  assert.equal(resolvePokemonBoosterPackAsset("shroudedFable"), null);
  assert.equal(resolvePokemonBoosterPackAsset("obsidianFlames"), null);
});

test("loose-pack artwork prefers the canonical product URL", () => {
  assert.deepEqual(
    resolveLooseBoosterPackArtwork({ productImageUrl: "https://cdn.example/pack.webp", setCanonicalKey: "ascendedHeroes" }),
    { src: "https://cdn.example/pack.webp", source: "product" },
  );
});

test("loose-pack artwork falls back to exact curated local assets", () => {
  assert.equal(resolveLooseBoosterPackArtwork({ setCanonicalKey: "ascendedHeroes" })?.src, "/images/pokemon/booster-packs/ascendedHeroes.webp");
  assert.equal(resolveLooseBoosterPackArtwork({ setCanonicalKey: "blackBolt" })?.src, "/images/pokemon/booster-packs/blackBolt.webp");
  assert.equal(resolveLooseBoosterPackArtwork({ setCanonicalKey: "journeyTogether" })?.src, "/images/pokemon/booster-packs/journeyTogether.webp");
  assert.equal(resolveLooseBoosterPackArtwork({ setCanonicalKey: "notInManifest" }), null);
});
