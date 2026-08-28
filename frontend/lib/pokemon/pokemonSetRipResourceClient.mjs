const MAX_ENTRIES = 8;
const TTL_MS = 5 * 60 * 1000;
const BROWSER_TIMEOUT_MS = 20_000;

const caches = {
  "global-context": new Map(),
  "simulation-evidence": new Map(),
  advanced: new Map(),
};

function trim(cache) {
  while (cache.size > MAX_ENTRIES) cache.delete(cache.keys().next().value);
}

export function clearSetRipResourceCache(resource, key = null) {
  const cache = caches[resource];
  if (!cache) return;
  if (key === null) cache.clear();
  else cache.delete(key);
}

export function buildSetRipResourceKey(setId, calculationRunId) {
  return `${String(setId || "").trim()}::${String(calculationRunId || "").trim()}`;
}

export function getCachedSetRipResource(resource, setId, calculationRunId, { force = false } = {}) {
  const id = String(setId || "").trim();
  const runId = String(calculationRunId || "").trim();
  if (!id || !runId || !caches[resource]) return Promise.reject(new Error("Set RIP resource identity is required"));
  const key = buildSetRipResourceKey(id, runId);
  const cache = caches[resource];
  if (force) cache.delete(key);
  const existing = cache.get(key);
  if (existing && Date.now() - existing.createdAt < TTL_MS) return existing.promise;
  if (existing) cache.delete(key);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), BROWSER_TIMEOUT_MS);
  const url = new URL(`/api/tcgs/pokemon/sets/${encodeURIComponent(id)}/rip/${resource}`, window.location.origin);
  if (resource === "global-context") url.searchParams.set("expected_calculation_run_id", runId);
  const promise = fetch(url, { cache: "no-store", headers: { Accept: "application/json" }, signal: controller.signal })
    .then(async (response) => {
      if (!response.ok) throw new Error(`Set RIP ${resource} request failed (${response.status})`);
      return response.json();
    })
    .catch((error) => {
      cache.delete(key);
      if (error?.name === "AbortError") {
        const timeout = new Error(`Set RIP ${resource} request timed out`);
        timeout.code = "SET_RIP_BROWSER_TIMEOUT";
        throw timeout;
      }
      throw error;
    })
    .finally(() => clearTimeout(timer));
  cache.set(key, { createdAt: Date.now(), promise });
  trim(cache);
  return promise;
}

export const SET_RIP_RESOURCE_CACHE_LIMIT = MAX_ENTRIES;
export const SET_RIP_RESOURCE_TTL_MS = TTL_MS;
