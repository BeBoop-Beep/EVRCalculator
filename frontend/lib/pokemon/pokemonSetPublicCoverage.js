/**
 * Centralized public-analytics eligibility gate for Pokemon sets.
 *
 * Sword & Shield's simulator-era data was run once during earlier work, but
 * the SWSH pull/hit-rate model is incomplete and some SWSH subsets (Trainer
 * Gallery / Galarian Gallery) still need to be blended with their parent
 * set's checklist before their numbers mean anything. SWSH also predates the
 * current set-page/performance architecture. None of that is a reason to
 * delete or rebuild anything — it just means SWSH analytics should not be
 * presented as validated public data yet.
 *
 * This module is the ONE place that decides "is this set's analytics ready
 * to show publicly" — every ranking/catalog surface should call
 * getPokemonSetPublicCoverageStatus / isPublicAnalyticsEligiblePokemonSet
 * instead of adding its own `era === "Sword & Shield"` check.
 */

export const POKEMON_SET_COVERAGE_STATUS = {
  ANALYTICS_READY: "analytics_ready",
  HIDDEN_PENDING_VALIDATION: "hidden_pending_validation",
  COMING_SOON: "coming_soon",
  SUBSET_NEEDS_PARENT_BLEND: "subset_needs_parent_blend",
  UNSUPPORTED_SPECIAL: "unsupported_special",
};

// era_id is the reliable, table-backed key (public.eras.id) and is preferred
// whenever a payload carries it (e.g. the Pokemon sets catalog). Some
// payloads only carry the era display name (e.g. the persisted Explore
// rankings snapshot's per-target rows never had era_id threaded through) —
// era name is still matched against here as a fallback, not because display
// names are otherwise preferred, but because that name is itself sourced
// from the same normalized `eras` table join, not free text.
const SWORD_AND_SHIELD_ERA_ID = "cdae9eb9-0f9e-4d93-9fdf-4221cfbdb90d";
const HIDDEN_PENDING_VALIDATION_ERA_NAMES = new Set(["sword and shield"]);

// Side-collection subsets that are structurally part of a parent set's
// checklist (Trainer Gallery / Galarian Gallery insert sheets) and cannot be
// meaningfully analyzed on their own — this status is intentionally
// independent of SWSH era membership, even though every current instance of
// it happens to be a SWSH-era subset, so a future non-SWSH subset can be
// tagged the same way without being confused for "SWSH, blanket hidden."
const SUBSET_NEEDS_PARENT_BLEND_NAME_PATTERNS = ["trainer gallery", "galarian gallery"];

// Promo-only / side products that are not real standalone analytics
// candidates regardless of era (McDonald's tie-ins, black star promos,
// starter/trainer kits, etc.).
const UNSUPPORTED_SPECIAL_NAME_PATTERNS = [
  "black star promo",
  "mcdonald",
  "pop series",
  "best of game",
  "futsal collection",
  "classic collection",
  "trainer kit",
  "starter set",
  "dragon vault",
  "southern islands",
  "pokemon go",
  "pokémon go",
];

function normalizeText(value) {
  return String(value ?? "").trim().toLowerCase();
}

function matchesAnyPattern(text, patterns) {
  return patterns.some((pattern) => text.includes(pattern));
}

function resolveEraId(pokemonSet) {
  const value = pokemonSet?.eraId ?? pokemonSet?.era_id ?? null;
  const text = String(value ?? "").trim();
  return text || null;
}

function resolveEraName(pokemonSet) {
  const value = pokemonSet?.era ?? pokemonSet?.era_name ?? pokemonSet?.eraName ?? null;
  return normalizeText(value) || null;
}

function isSwordAndShieldEra(pokemonSet) {
  const eraId = resolveEraId(pokemonSet);
  if (eraId && eraId === SWORD_AND_SHIELD_ERA_ID) {
    return true;
  }
  const eraName = resolveEraName(pokemonSet);
  return Boolean(eraName && HIDDEN_PENDING_VALIDATION_ERA_NAMES.has(eraName));
}

function resolveName(pokemonSet) {
  return normalizeText(pokemonSet?.name);
}

/**
 * Classify one Pokemon set's public-analytics coverage status. Pure
 * function — never reads the network/DB, never mutates the input, never
 * touches scoring/ranking math. Accepts either the sets-catalog shape
 * (name/era/eraId) or the Explore ranking-target shape (name/era) since both
 * carry enough era information to classify.
 */
export function getPokemonSetPublicCoverageStatus(pokemonSet) {
  if (!pokemonSet || typeof pokemonSet !== "object") {
    return POKEMON_SET_COVERAGE_STATUS.ANALYTICS_READY;
  }

  const name = resolveName(pokemonSet);

  if (matchesAnyPattern(name, UNSUPPORTED_SPECIAL_NAME_PATTERNS)) {
    return POKEMON_SET_COVERAGE_STATUS.UNSUPPORTED_SPECIAL;
  }

  if (matchesAnyPattern(name, SUBSET_NEEDS_PARENT_BLEND_NAME_PATTERNS)) {
    return POKEMON_SET_COVERAGE_STATUS.SUBSET_NEEDS_PARENT_BLEND;
  }

  if (isSwordAndShieldEra(pokemonSet)) {
    return POKEMON_SET_COVERAGE_STATUS.HIDDEN_PENDING_VALIDATION;
  }

  return POKEMON_SET_COVERAGE_STATUS.ANALYTICS_READY;
}

/**
 * True only for analytics_ready sets — every other status (hidden pending
 * validation, subset needing a parent blend, unsupported special, coming
 * soon) is excluded from public rankings/analytics surfaces.
 */
export function isPublicAnalyticsEligiblePokemonSet(pokemonSet) {
  return getPokemonSetPublicCoverageStatus(pokemonSet) === POKEMON_SET_COVERAGE_STATUS.ANALYTICS_READY;
}

/**
 * Narrower than isPublicAnalyticsEligiblePokemonSet: true only for the
 * SWSH-specific hide (this task's actual scope), checked directly against
 * era rather than derived from getPokemonSetPublicCoverageStatus. That
 * matters for sets like "Pokémon GO" or "SWSH Black Star Promos" — they are
 * SWSH era *and* happen to match the unsupported_special name patterns, so
 * status-based derivation would silently let them slip back into the
 * catalog because unsupported_special is checked ahead of the SWSH check
 * for status-classification purposes. The public Sets catalog already
 * showed genuinely non-SWSH unsupported_special products (POP Series,
 * Nintendo promos, etc.) before this change, and nothing in this task asked
 * for that to change — only SWSH's catalog visibility was in scope.
 */
export function isHiddenFromPublicPokemonSetsCatalog(pokemonSet) {
  return isSwordAndShieldEra(pokemonSet);
}
