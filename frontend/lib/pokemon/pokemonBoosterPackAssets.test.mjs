import assert from "node:assert/strict";
import test from "node:test";

import { resolvePokemonBoosterPackAsset } from "./pokemonBoosterPackAssets.mjs";

test("available canonical sets resolve their local camelCase WebP", () => {
  assert.equal(resolvePokemonBoosterPackAsset("paradoxRift")?.src, "/images/pokemon/booster-packs/paradoxRift.webp");
  assert.equal(resolvePokemonBoosterPackAsset("scarletAndViolet151")?.src, "/images/pokemon/booster-packs/scarletAndViolet151.webp");
});

test("missing sets return null without cross-set or external fallback", () => {
  assert.equal(resolvePokemonBoosterPackAsset("temporalForces"), null);
  assert.equal(resolvePokemonBoosterPackAsset("shroudedFable"), null);
  assert.equal(resolvePokemonBoosterPackAsset("obsidianFlames"), null);
});
