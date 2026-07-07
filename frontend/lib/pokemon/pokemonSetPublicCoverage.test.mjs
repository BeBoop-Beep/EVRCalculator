import test from "node:test";
import assert from "node:assert/strict";
import {
  POKEMON_SET_COVERAGE_STATUS,
  getPokemonSetPublicCoverageStatus,
  isPublicAnalyticsEligiblePokemonSet,
  isHiddenFromPublicPokemonSetsCatalog,
} from "./pokemonSetPublicCoverage.js";

test("SWSH set (by era name) returns hidden_pending_validation and is not eligible", () => {
  const set = { name: "Silver Tempest", era: "Sword and Shield" };
  assert.equal(getPokemonSetPublicCoverageStatus(set), POKEMON_SET_COVERAGE_STATUS.HIDDEN_PENDING_VALIDATION);
  assert.equal(isPublicAnalyticsEligiblePokemonSet(set), false);
});

test("SWSH set (by era_id) returns hidden_pending_validation even without an era name", () => {
  const set = { name: "Rebel Clash", eraId: "cdae9eb9-0f9e-4d93-9fdf-4221cfbdb90d" };
  assert.equal(getPokemonSetPublicCoverageStatus(set), POKEMON_SET_COVERAGE_STATUS.HIDDEN_PENDING_VALIDATION);
  assert.equal(isPublicAnalyticsEligiblePokemonSet(set), false);
});

test("SWSH era match is case/whitespace-insensitive and works with snake_case era_id/era_name fields", () => {
  const set = { name: "Fusion Strike", era_name: "  SWORD AND SHIELD  " };
  assert.equal(getPokemonSetPublicCoverageStatus(set), POKEMON_SET_COVERAGE_STATUS.HIDDEN_PENDING_VALIDATION);
});

test("supported modern (Scarlet and Violet) set remains analytics_ready and eligible", () => {
  const set = { name: "Prismatic Evolutions", era: "Scarlet and Violet", eraId: "dfb0dfa1-6a8e-4335-850f-e003867e19ee" };
  assert.equal(getPokemonSetPublicCoverageStatus(set), POKEMON_SET_COVERAGE_STATUS.ANALYTICS_READY);
  assert.equal(isPublicAnalyticsEligiblePokemonSet(set), true);
});

test("supported modern (Mega Evolution) set remains analytics_ready and eligible", () => {
  const set = { name: "Perfect Order", era: "Mega Evolution" };
  assert.equal(getPokemonSetPublicCoverageStatus(set), POKEMON_SET_COVERAGE_STATUS.ANALYTICS_READY);
  assert.equal(isPublicAnalyticsEligiblePokemonSet(set), true);
});

test("Trainer Gallery / Galarian Gallery subsets are marked subset_needs_parent_blend, distinct from blanket SWSH hiding", () => {
  const trainerGallery = { name: "Silver Tempest Trainer Gallery", era: "Sword and Shield" };
  const galarianGallery = { name: "Crown Zenith Galarian Gallery", era: "Sword and Shield" };
  assert.equal(
    getPokemonSetPublicCoverageStatus(trainerGallery),
    POKEMON_SET_COVERAGE_STATUS.SUBSET_NEEDS_PARENT_BLEND
  );
  assert.equal(
    getPokemonSetPublicCoverageStatus(galarianGallery),
    POKEMON_SET_COVERAGE_STATUS.SUBSET_NEEDS_PARENT_BLEND
  );
  // Both statuses are non-ready, so both are still excluded from analytics —
  // the point is the *reason* is distinguishable, not that either is shown.
  assert.equal(isPublicAnalyticsEligiblePokemonSet(trainerGallery), false);
  assert.equal(isPublicAnalyticsEligiblePokemonSet(galarianGallery), false);
  assert.notEqual(
    getPokemonSetPublicCoverageStatus(trainerGallery),
    POKEMON_SET_COVERAGE_STATUS.HIDDEN_PENDING_VALIDATION
  );
});

test("promo/side-collection sets are marked unsupported_special regardless of era", () => {
  const promo = { name: "SWSH Black Star Promos", era: "Sword and Shield" };
  const mcdonalds = { name: "McDonald's Collection 2022", era: "Scarlet and Violet" };
  assert.equal(getPokemonSetPublicCoverageStatus(promo), POKEMON_SET_COVERAGE_STATUS.UNSUPPORTED_SPECIAL);
  assert.equal(getPokemonSetPublicCoverageStatus(mcdonalds), POKEMON_SET_COVERAGE_STATUS.UNSUPPORTED_SPECIAL);
  assert.equal(isPublicAnalyticsEligiblePokemonSet(promo), false);
  assert.equal(isPublicAnalyticsEligiblePokemonSet(mcdonalds), false);
});

test("catalog visibility: SWSH sets are hidden from the public Sets catalog", () => {
  const set = { name: "Rebel Clash", era: "Sword and Shield" };
  assert.equal(isHiddenFromPublicPokemonSetsCatalog(set), true);
});

test("catalog visibility: SWSH Trainer Gallery/Galarian Gallery subsets are also hidden from the catalog", () => {
  const trainerGallery = { name: "Silver Tempest Trainer Gallery", era: "Sword and Shield" };
  assert.equal(isHiddenFromPublicPokemonSetsCatalog(trainerGallery), true);
});

test("catalog visibility: SWSH-era sets that also match an unsupported_special name pattern (Pokemon GO, SWSH Black Star Promos) are still hidden from the catalog", () => {
  // These get classified as unsupported_special (name pattern wins over era
  // for the status enum), but the catalog hide must key on era directly so
  // it doesn't accidentally let SWSH content back in through that gap.
  const pokemonGo = { name: "Pokémon GO", era: "Sword and Shield" };
  const swshPromos = { name: "SWSH Black Star Promos", era: "Sword and Shield" };
  assert.equal(getPokemonSetPublicCoverageStatus(pokemonGo), POKEMON_SET_COVERAGE_STATUS.UNSUPPORTED_SPECIAL);
  assert.equal(isHiddenFromPublicPokemonSetsCatalog(pokemonGo), true);
  assert.equal(getPokemonSetPublicCoverageStatus(swshPromos), POKEMON_SET_COVERAGE_STATUS.UNSUPPORTED_SPECIAL);
  assert.equal(isHiddenFromPublicPokemonSetsCatalog(swshPromos), true);
});

test("catalog visibility: non-SWSH unsupported_special products (POP Series, promos) stay visible in the catalog — only SWSH is in scope for this task", () => {
  const popSeries = { name: "POP Series 9", era: "POP" };
  const nintendoPromos = { name: "Nintendo Black Star Promos", era: "NP" };
  assert.equal(getPokemonSetPublicCoverageStatus(popSeries), POKEMON_SET_COVERAGE_STATUS.UNSUPPORTED_SPECIAL);
  assert.equal(getPokemonSetPublicCoverageStatus(nintendoPromos), POKEMON_SET_COVERAGE_STATUS.UNSUPPORTED_SPECIAL);
  // Not eligible for analytics/rankings surfaces...
  assert.equal(isPublicAnalyticsEligiblePokemonSet(popSeries), false);
  assert.equal(isPublicAnalyticsEligiblePokemonSet(nintendoPromos), false);
  // ...but the catalog page must not newly hide these; that was never SWSH-scoped.
  assert.equal(isHiddenFromPublicPokemonSetsCatalog(popSeries), false);
  assert.equal(isHiddenFromPublicPokemonSetsCatalog(nintendoPromos), false);
});

test("catalog visibility: supported modern sets stay visible", () => {
  const set = { name: "Prismatic Evolutions", era: "Scarlet and Violet" };
  assert.equal(isHiddenFromPublicPokemonSetsCatalog(set), false);
});

test("is defensive against missing/malformed input", () => {
  assert.equal(getPokemonSetPublicCoverageStatus(null), POKEMON_SET_COVERAGE_STATUS.ANALYTICS_READY);
  assert.equal(getPokemonSetPublicCoverageStatus(undefined), POKEMON_SET_COVERAGE_STATUS.ANALYTICS_READY);
  assert.equal(getPokemonSetPublicCoverageStatus({}), POKEMON_SET_COVERAGE_STATUS.ANALYTICS_READY);
  assert.equal(isPublicAnalyticsEligiblePokemonSet({}), true);
});
