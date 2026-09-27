const CURRENT_ENDPOINT = "/api/tcgs/pokemon/rip-benchmark/current";
const HISTORY_ENDPOINT = "/api/tcgs/pokemon/rip-benchmark/history";
const PRODUCT_CURRENT_ENDPOINT = "/api/tcgs/pokemon/rip-benchmark/current-batch";
const DAY = 86_400_000;
const key = (entity) => `${entity.entity_type}:${entity.entity_id}`;
export function dedupeBenchmarkEntities(entities) { return [...new Map((entities || []).filter((e) => e?.entity_type && e?.entity_id).map((e) => [key(e), { entity_type: e.entity_type, entity_id: e.entity_id }])).values()]; }
const chunks = (items, size) => Array.from({ length: Math.ceil(items.length / size) }, (_, index) => items.slice(index * size, (index + 1) * size));
async function json(response) { const payload = await response.json().catch(() => null); if (!response.ok) { const error = new Error(payload?.detail?.message || payload?.message || "Benchmark request failed"); error.status = response.status; error.payload = payload; throw error; } return payload; }
function generation(payload) { return JSON.stringify([payload?.publication_id, payload?.market_date, payload?.calibration_version, payload?.cohort_fingerprint, payload?.freshness]); }
export async function readCurrentBenchmark(entities, { fetchImpl = fetch, sessionCache = null } = {}) {
  const unique = dedupeBenchmarkEntities(entities); if (!unique.length) return { status: "unavailable", rows: [] };
  const cacheKey = `benchmark:current:${unique.map(key).sort().join(",")}`;
  const load = async () => {
    const payloads = await Promise.all(chunks(unique, 10).map((batch) => fetchImpl(CURRENT_ENDPOINT, { method: "POST", credentials: "include", cache: "no-store", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ entities: batch }) }).then(json)));
    const expected = generation(payloads[0]);
    if (payloads.some((payload) => generation(payload) !== expected)) throw new Error("Mixed Benchmark publications; refresh required.");
    return { ...payloads[0], rows: payloads.flatMap((payload) => Array.isArray(payload.rows) ? payload.rows : []) };
  };
  return sessionCache ? sessionCache.request(cacheKey, load) : load();
}
export async function readCurrentProductBenchmark(entities, { fetchImpl = fetch, sessionCache = null, force = false } = {}) {
  const unique = dedupeBenchmarkEntities(entities); if (!unique.length) return { status: "unavailable", rows: [] };
  const cacheKey = `benchmark:products:${unique.map(key).sort().join(",")}`;
  const load = () => fetchImpl(PRODUCT_CURRENT_ENDPOINT, { method: "POST", credentials: "include", cache: "no-store", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ entities: unique }) }).then(json);
  return sessionCache ? sessionCache.request(cacheKey, load, { force }) : load();
}
export function boundedHistoryWindows(startDate, endDate) {
  let cursor = new Date(`${startDate}T00:00:00Z`); const end = new Date(`${endDate}T00:00:00Z`); const result = [];
  while (cursor <= end) { const windowEnd = new Date(Math.min(end.getTime(), cursor.getTime() + 365 * DAY)); result.push([cursor.toISOString().slice(0, 10), windowEnd.toISOString().slice(0, 10)]); cursor = new Date(windowEnd.getTime() + DAY); }
  return result;
}
export async function readBenchmarkHistory(entities, { startDate, endDate, fetchImpl = fetch } = {}) {
  const unique = dedupeBenchmarkEntities(entities); const rows = []; let authority = null; let availableFrom = null; let availableThrough = null; const references = {};
  for (const batch of chunks(unique, 10)) for (const [start_date, end_date] of boundedHistoryWindows(startDate, endDate)) {
    let after = null;
    do {
      const payload = await fetchImpl(HISTORY_ENDPOINT, { method: "POST", credentials: "include", cache: "no-store", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ entities: batch, start_date, end_date, limit: 1000, ...(after ? { after } : {}) }) }).then(json);
      const signature = JSON.stringify([payload?.benchmark_key, payload?.calibration_version, payload?.historyAvailableFrom, payload?.historyAvailableThrough]);
      if (authority && signature !== authority) throw new Error("Benchmark history changed; refresh required.");
      authority ||= signature; availableFrom ||= payload?.historyAvailableFrom || null; availableThrough ||= payload?.historyAvailableThrough || null; Object.assign(references, payload?.opening_economics_references || {}); rows.push(...(payload?.rows || [])); after = payload?.has_more ? payload?.next_cursor : null;
    } while (after);
  }
  return { rows, openingEconomicsReferences: references, historyAvailableFrom: availableFrom, historyAvailableThrough: availableThrough };
}
