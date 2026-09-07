import {
  QUERY_ASSET_SEALED,
  QUERY_MODE_ALL,
  normalizeQuerySpec,
} from "./marketExplorerQuery.mjs";

/** Resolve exact semantic equivalence to an already-published prepared series.
 *
 * Card query markets intentionally do not resolve to the legacy overview
 * parents/submarkets. The overview snapshot covers its own published cohort,
 * while the query engine's Global scope uses the complete current Market
 * Explorer authority. Treating those as interchangeable made a 22-set Raw
 * parent suppress the 165-set Global All Raw query in production.
 */
export function resolvePreparedSeriesForSpec(spec, preparedSeries = []) {
  const normalized = normalizeQuerySpec(spec);
  if (normalized.mode !== QUERY_MODE_ALL || normalized.eraIds.length || normalized.setIds.length ||
      normalized.pokemonIds.length || normalized.priceSegmentIds.length || normalized.releaseAgeCohortIds.length) return null;
  const list = Array.isArray(preparedSeries) ? preparedSeries : [];
  if (!normalized.segmentIds.length) {
    if (normalized.asset !== QUERY_ASSET_SEALED) return null;
    return list.find((series) => series.key === "sealedMarket" && series.available !== false) || null;
  }
  if (normalized.segmentIds.length !== 1) return null;
  const backendKey = normalized.segmentIds[0];
  if (normalized.asset !== QUERY_ASSET_SEALED) return null;
  return list.find((series) =>
    series.group === "sealed" && series.isParent === false &&
    series.backendKey === backendKey && series.available !== false
  ) || null;
}
