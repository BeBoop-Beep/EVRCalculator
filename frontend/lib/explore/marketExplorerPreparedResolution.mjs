import {
  QUERY_ASSET_CARDS,
  QUERY_ASSET_SEALED,
  QUERY_MODE_ALL,
  normalizeQuerySpec,
} from "./marketExplorerQuery.mjs";

/** Resolve exact semantic equivalence to an already-published prepared series. */
export function resolvePreparedSeriesForSpec(spec, preparedSeries = []) {
  const normalized = normalizeQuerySpec(spec);
  if (normalized.mode !== QUERY_MODE_ALL || normalized.eraIds.length || normalized.setIds.length ||
      normalized.pokemonIds.length || normalized.priceSegmentIds.length || normalized.releaseAgeCohortIds.length) return null;
  const list = Array.isArray(preparedSeries) ? preparedSeries : [];
  if (!normalized.segmentIds.length) {
    const key = normalized.asset === QUERY_ASSET_SEALED ? "sealedMarket" : "raw";
    return list.find((series) => series.key === key && series.available !== false) || null;
  }
  if (normalized.segmentIds.length !== 1) return null;
  const backendKey = normalized.segmentIds[0];
  if (normalized.asset === QUERY_ASSET_CARDS) {
    return list.find((series) =>
      series.group === "card" && series.isParent === false &&
      series.parentSeriesId === "raw" && series.backendKey === backendKey && series.available !== false
    ) || null;
  }
  return list.find((series) =>
    series.group === "sealed" && series.isParent === false &&
    series.backendKey === backendKey && series.available !== false
  ) || null;
}
