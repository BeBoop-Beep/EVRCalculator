// Financial RIP history on top of the EXISTING Rankings session cache.
//
// The session cache is already scoped to `${access identity}:${publication}`, so
// everything stored here is per user/access state and per publication; nothing is
// global.  Keys additionally carry entity type, date range and the normalised
// entity ids.  A completed, wider response for the SAME session/type/range can
// serve a narrower selection locally (a pure row filter - nothing is invented).
import { dedupeBenchmarkEntities, readFinancialRipHistory } from "./ripBenchmarkClient.mjs";

export const FINANCIAL_HISTORY_API_CEILING = 22;

// sessionCache -> Map(rangeKey -> Map(cacheKey -> Set(entityId)))
const completed = new WeakMap();

const rowEntityId = (row) => String(row?.entityId ?? row?.entity_id ?? "");

function normalise(entities) {
  const unique = dedupeBenchmarkEntities(entities);
  if (!unique.length) return null;
  const types = new Set(unique.map((entity) => entity.entity_type));
  if (types.size !== 1) return null;
  const entityType = unique[0].entity_type;
  const ids = unique.map((entity) => String(entity.entity_id)).sort();
  return { unique, entityType, ids };
}

export function financialHistoryRangeKey(entityType, startDate, endDate) {
  return `${entityType}|${startDate}|${endDate}`;
}

export function financialHistoryKey(entityType, ids, startDate, endDate) {
  return `financial-history:${financialHistoryRangeKey(entityType, startDate, endDate)}:${ids.join(",")}`;
}

function project(payload, idSet) {
  return { ...payload, rows: (Array.isArray(payload?.rows) ? payload.rows : []).filter((row) => idSet.has(rowEntityId(row))) };
}

/** Synchronous cache lookup: exact entry, else a completed superset for the same type/range. */
export function peekFinancialHistory(entities, { sessionCache, startDate, endDate }) {
  if (!sessionCache || !startDate || !endDate) return undefined;
  const normal = normalise(entities);
  if (!normal) return undefined;
  const exact = sessionCache.peek(financialHistoryKey(normal.entityType, normal.ids, startDate, endDate));
  if (exact !== undefined) return exact;
  const bucket = completed.get(sessionCache)?.get(financialHistoryRangeKey(normal.entityType, startDate, endDate));
  if (!bucket) return undefined;
  let best = null;
  for (const [cacheKey, idSet] of bucket) {
    if (idSet.size < normal.ids.length || !normal.ids.every((id) => idSet.has(id))) continue;
    if (sessionCache.peek(cacheKey) === undefined) continue;
    if (!best || idSet.size < best.idSet.size) best = { cacheKey, idSet };
  }
  return best ? project(sessionCache.peek(best.cacheKey), new Set(normal.ids)) : undefined;
}

/** Cache-first read.  Identical in-flight requests are shared by the session cache. */
export async function readFinancialHistoryCached(entities, { sessionCache = null, startDate, endDate, fetchImpl = fetch, force = false } = {}) {
  const normal = normalise(entities);
  if (!normal) throw new Error("Financial RIP history requires Sets or Eras of a single type.");
  if (normal.ids.length > FINANCIAL_HISTORY_API_CEILING) throw new Error("Financial RIP history requires 1–22 Sets/Eras.");
  const load = () => readFinancialRipHistory(normal.unique, { startDate, endDate, fetchImpl });
  if (!sessionCache) return load();
  if (!force) {
    const hit = peekFinancialHistory(normal.unique, { sessionCache, startDate, endDate });
    if (hit !== undefined) return hit;
  }
  const cacheKey = financialHistoryKey(normal.entityType, normal.ids, startDate, endDate);
  const payload = await sessionCache.request(cacheKey, load, { force });
  let ranges = completed.get(sessionCache);
  if (!ranges) completed.set(sessionCache, (ranges = new Map()));
  const rangeKey = financialHistoryRangeKey(normal.entityType, startDate, endDate);
  let bucket = ranges.get(rangeKey);
  if (!bucket) ranges.set(rangeKey, (bucket = new Map()));
  bucket.set(cacheKey, new Set(normal.ids));
  return payload;
}

/**
 * Start the default chart request early (parent-owned) through the SAME key the
 * chart consumes.  Never called for viewers who are not entitled.
 */
export function prewarmFinancialHistory(plan, { sessionCache, entitled, authStatus, fetchImpl = fetch } = {}) {
  if (!plan || !sessionCache || !entitled || !(authStatus === "resolved" || authStatus === "degraded")) return Promise.resolve(null);
  return readFinancialHistoryCached(plan.entities, { sessionCache, startDate: plan.startDate, endDate: plan.endDate, fetchImpl }).catch(() => null);
}

/**
 * Optional, bounded idle prefetch of the full cohort for the SAME range as the
 * default view.  An optimisation only: one request, <= 22 entities, entitled
 * viewers, and never under save-data.
 */
export function planCohortPrefetch(plan, { saveData = false, entitled = false } = {}) {
  if (!plan || !entitled || saveData) return null;
  const ids = plan.cohortEntities || [];
  if (ids.length <= plan.entities.length || ids.length > FINANCIAL_HISTORY_API_CEILING) return null;
  return { entities: ids, startDate: plan.startDate, endDate: plan.endDate };
}
