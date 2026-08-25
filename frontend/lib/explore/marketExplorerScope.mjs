// ---------------------------------------------------------------------------
// Market Explorer — Era & Sets scope model.
//
// WHAT A SCOPE IS, AND IS NOT.
//
// A scope is a NARROWING: "Scarlet & Violet", or "Evolving Skies + Lost
// Origin". It is NOT a market. No backend publishes an era index, so selecting
// an era cannot and does not put a line on the chart — doing that would mean
// filtering an already-aggregated global index in React, which is a different
// (and wrong) number from an index built over the era's own constituents.
//
// What a scope IS good for is handing to the query engine, which can build a
// real era- or set-scoped market from its own constituents. So Era & Sets is
// navigation that FEEDS Build a Market, by an explicit user action, and says
// so in the UI rather than silently rewriting the builder underneath the user.
//
// ERA AND SET ARE ANDed by the backend (see resolve_scope_set_ids). "Scarlet &
// Violet" plus "Evolving Skies" therefore resolves to nothing at all. Rather
// than letting a user compose that and receive an empty market, set selections
// are reconciled against the selected eras here — the same rule the builder's
// Set control already applies.
// ---------------------------------------------------------------------------

import { sortEraOptions, sortSetOptions } from "./marketExplorerQuery.mjs";

/**
 * The era -> sets tree, in canonical order.
 *
 * `asset` narrows to the sets that asset can actually offer: a set with no
 * prepared sealed snapshot has no sealed market, and offering it would produce
 * a choice that resolves to nothing. A set that predates the flag is assumed
 * to support cards, which is the historical contract.
 */
export function buildEraSetTree(options, { asset = "cards", eraIds = [], setIds = [] } = {}) {
  const selectedEras = new Set(eraIds || []);
  const selectedSets = new Set(setIds || []);
  const sets = sortSetOptions(options?.sets).filter(
    (entry) => (Array.isArray(entry.assets) ? entry.assets.includes(asset) : asset === "cards")
  );
  const byEra = new Map();
  for (const entry of sets) {
    const key = String(entry.eraId || "");
    if (!byEra.has(key)) byEra.set(key, []);
    byEra.get(key).push({
      id: entry.id,
      label: entry.label,
      eraId: key,
      releaseDate: entry.releaseDate || null,
      selected: selectedSets.has(entry.id),
    });
  }
  return sortEraOptions(options?.eras)
    .map((era) => ({
      id: era.id,
      // The era's CANONICAL name, exactly as the `eras` table stores it —
      // "Sword & Shield", never a bucket label invented by the frontend.
      label: era.label,
      sortOrder: era.sortOrder ?? null,
      selected: selectedEras.has(era.id),
      sets: byEra.get(String(era.id)) || [],
    }))
    .filter((era) => era.sets.length > 0);
}

const toggleIn = (values, id) => {
  const next = new Set(values || []);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return [...next];
};

/**
 * Toggle one era's SELECTION. Expansion is separate component state and is
 * deliberately untouched: a user opening Sword & Shield to look at its sets has
 * not asked to select the whole era, and a user selecting the era has not asked
 * for a list of forty sets to unfold.
 */
export function toggleScopeEra(scope, eraId, tree) {
  const eraIds = toggleIn(scope?.eraIds, eraId);
  return reconcileScope({ ...scope, eraIds }, tree);
}

export function toggleScopeSet(scope, setId, tree) {
  return reconcileScope({ ...scope, setIds: toggleIn(scope?.setIds, setId) }, tree);
}

export function clearScope() {
  return { eraIds: [], setIds: [] };
}

/**
 * Drop selections the tree can no longer honour, and any set stranded outside
 * the selected eras — which the backend's era AND set rule would resolve to an
 * empty market.
 */
export function reconcileScope(scope, tree) {
  const eras = Array.isArray(tree) ? tree : [];
  const knownEras = new Set(eras.map((era) => era.id));
  const eraIds = (scope?.eraIds || []).filter((id) => knownEras.has(id));
  const allowedSets = new Set(
    eras
      .filter((era) => eraIds.length === 0 || eraIds.includes(era.id))
      .flatMap((era) => era.sets.map((entry) => entry.id))
  );
  return { eraIds, setIds: (scope?.setIds || []).filter((id) => allowedSets.has(id)) };
}

export const isScopeEmpty = (scope) =>
  !(scope?.eraIds || []).length && !(scope?.setIds || []).length;

/** A short, human summary of the active scope, for the group header. */
export function describeScope(scope, tree) {
  if (isScopeEmpty(scope)) return "";
  const eras = Array.isArray(tree) ? tree : [];
  const setNames = new Map(eras.flatMap((era) => era.sets.map((entry) => [entry.id, entry.label])));
  // An explicit set selection is the most specific statement the user made, so
  // it names the scope — the same precedence Build a Market's chip label uses.
  if (scope.setIds.length) {
    return scope.setIds.length === 1
      ? setNames.get(scope.setIds[0]) || "1 Set"
      : `${scope.setIds.length} Sets`;
  }
  const eraNames = new Map(eras.map((era) => [era.id, era.label]));
  return scope.eraIds.length === 1
    ? eraNames.get(scope.eraIds[0]) || "1 Era"
    : `${scope.eraIds.length} Eras`;
}

/** Case-insensitive match over era AND set names, for the group's search. */
export function filterEraSetTree(tree, term) {
  const needle = String(term || "").trim().toLowerCase();
  if (!needle) return Array.isArray(tree) ? tree : [];
  return (Array.isArray(tree) ? tree : [])
    .map((era) => {
      // Matching the ERA keeps all of its sets: the user searched for the era.
      if (String(era.label || "").toLowerCase().includes(needle)) return era;
      const sets = era.sets.filter((entry) => String(entry.label || "").toLowerCase().includes(needle));
      return sets.length ? { ...era, sets } : null;
    })
    .filter(Boolean);
}
