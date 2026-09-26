// ---------------------------------------------------------------------------
// Market Explorer — truthful availability of rarity / sealed-type options.
//
// The DB publishes an eligibility STATE for every option
// (get_pokemon_market_explorer_asset_options_v2). This module turns a state
// into exactly one ACTION so no option can be "click -> nothing" or "Adding…"
// forever:
//
//   prepared -> activate the published prepared market (marketKey)
//   build    -> no prepared market yet, but the generic custom-build pathway
//               can construct it
//   none     -> not executable; `reason` is always a concise explanation
//
// Nothing here special-cases a rarity or a product family. Keys, labels and
// counts are read from the option; the option list itself is never hard-coded.
// ---------------------------------------------------------------------------

export const ASSET_OPTION_ACTION = Object.freeze({ prepared: "prepared", build: "build", none: "none" });

const RARITY_STATES = Object.freeze({
  PREPARED: "PREPARED",
  CUSTOM_BUILD_AVAILABLE: "CUSTOM_BUILD_AVAILABLE",
  INSUFFICIENT_COHORT: "INSUFFICIENT_COHORT",
  INSUFFICIENT_HISTORY: "INSUFFICIENT_HISTORY",
  UNAVAILABLE: "UNAVAILABLE",
});
const SEALED_STATES = Object.freeze({
  PREPARED: "PREPARED",
  PREPARED_CANDIDATE: "PREPARED_CANDIDATE",
  SEARCHABLE_BUILDABLE: "SEARCHABLE_BUILDABLE",
  INSUFFICIENT_HISTORY: "INSUFFICIENT_HISTORY",
  UNAVAILABLE: "UNAVAILABLE",
});

const DEFAULT_REASON = Object.freeze({
  INSUFFICIENT_COHORT: "Not enough currently priced cards across enough Sets to form a market yet.",
  INSUFFICIENT_HISTORY: "Not enough price history to form a market yet.",
  UNAVAILABLE: "No current priced inventory is available for this option.",
  UNKNOWN: "This option is not available as a market right now.",
});

const usable = (value) => (typeof value === "string" && value.trim() ? value.trim() : null);

function blocked(state, option) {
  const known = DEFAULT_REASON[state] ? state : "UNKNOWN";
  return { action: ASSET_OPTION_ACTION.none, marketKey: null, reason: usable(option?.reason) || DEFAULT_REASON[known], state: state || "UNKNOWN" };
}

/**
 * Map one asset option (rarity or sealed type) to its single action.
 * A published prepared market key is DB-owned truth and always wins, so a
 * temporarily empty audit can never downgrade a maintained identity.
 */
export function resolveAssetOptionAction(option) {
  const state = String(option?.eligibilityState || "").toUpperCase();
  const key = usable(option?.preparedMarketKey);
  if (option?.preparedMarketAvailable === true && key) {
    return { action: ASSET_OPTION_ACTION.prepared, marketKey: key, reason: null, state: state || "PREPARED" };
  }
  if (state === RARITY_STATES.PREPARED || state === SEALED_STATES.PREPARED_CANDIDATE) {
    // A candidate/prepared state with a candidate key is executable through the
    // prepared loader; without any key the honest answer is the build path.
    if (key) return { action: ASSET_OPTION_ACTION.prepared, marketKey: key, reason: null, state };
    if (state === SEALED_STATES.PREPARED_CANDIDATE) return { action: ASSET_OPTION_ACTION.build, marketKey: null, reason: null, state };
    return blocked(state, { ...option, reason: option?.reason || "This market is not published yet." });
  }
  if (state === RARITY_STATES.CUSTOM_BUILD_AVAILABLE || state === SEALED_STATES.SEARCHABLE_BUILDABLE) {
    return key
      ? { action: ASSET_OPTION_ACTION.prepared, marketKey: key, reason: null, state }
      : { action: ASSET_OPTION_ACTION.build, marketKey: null, reason: null, state };
  }
  return blocked(state, option);
}

export const resolveRarityOptionAction = resolveAssetOptionAction;
export const resolveSealedTypeAction = resolveAssetOptionAction;

/** Normalize a V2 `rarities[]` payload to a stable option list (order preserved). */
export function normalizeRarityOptions(payload) {
  const rows = Array.isArray(payload?.rarities) ? payload.rarities : [];
  return rows.filter((row) => usable(row?.key) && usable(row?.label)).map((row) => ({
    id: String(row.key), label: String(row.label), raw: row, ...resolveAssetOptionAction(row),
    counts: { cards: row.currentPricedCardCount ?? null, sets: row.representedSetCount ?? null, history: row.historyPointCount ?? null, images: row.imageCount ?? null },
  }));
}

export const BULK_CONTAINER_NOTE = "Bulk container — tracked separately from Total Sealed";

/** Normalize a V2 sealed `types[]` payload. Bulk containers are informational, never "invalid". */
export function normalizeSealedTypeOptions(payload) {
  const rows = Array.isArray(payload?.types) ? payload.types : [];
  return rows.filter((row) => usable(row?.key) && usable(row?.label)).map((row) => ({
    id: String(row.key), label: String(row.label), raw: row, ...resolveAssetOptionAction(row),
    bulkContainer: row.bulkContainer === true,
    parentMembership: row.parentMembership === true,
    note: row.bulkContainer === true ? BULK_CONTAINER_NOTE : null,
    counts: { products: row.currentProductCount ?? null, priced: row.currentPricedCount ?? null, sets: row.representedSetCount ?? null, eras: row.representedEraCount ?? null, history: row.historyPointCount ?? null },
  }));
}

/** Sealed Quick Markets: only APPROVED registry entries are selectable. */
export function approvedSealedQuickMarkets(payload) {
  const rows = Array.isArray(payload?.quickMarkets) ? payload.quickMarkets : [];
  return rows.filter((row) => String(row?.status || "").toUpperCase() === "APPROVED" && usable(row?.key));
}
export const NO_APPROVED_SEALED_QUICK_COPY = "No approved Sealed Quick Markets yet.";

export const ASSET_OPTIONS_ENDPOINT = "/api/market/explorer/asset-options";

export async function fetchAssetOptions(asset, { signal } = {}) {
  const response = await fetch(`${ASSET_OPTIONS_ENDPOINT}?asset=${encodeURIComponent(asset)}`, { credentials: "include", cache: "no-store", signal });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error("Options are temporarily unavailable");
    error.status = response.status;
    error.code = payload?.code || "ASSET_OPTIONS_FAILED";
    throw error;
  }
  return payload || {};
}
