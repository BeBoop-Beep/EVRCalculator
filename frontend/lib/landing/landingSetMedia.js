import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

/**
 * Pokemon-native product content for the homepage: the chase cards a set is
 * actually known for, and the sealed products it actually sells as.
 *
 * NO NEW PIPELINE. These are the SAME two published endpoints the set detail
 * Overview already reads — /market/top-chase and /market/sealed — called
 * server-side for the one or two sets the homepage features. The targets
 * payload the rest of the page runs on carries set logos only, so card imagery
 * cannot come from it; this is the minimum additional read that lets the page
 * show real Pokemon cards instead of describing them.
 *
 * Every call is bounded, cached, and non-fatal: a failure returns null and the
 * caller falls back down the ladder (sealed product -> set logo + chase cards
 * -> intelligence panel alone) rather than rendering a broken tile.
 */

const BACKEND_URL = getBackendApiBaseUrl();
const FETCH_TIMEOUT_MS = 6_000;
const SUCCESS_TTL_MS = 300_000;
const FAILURE_TTL_MS = 30_000;

const mediaCache = new Map();

function readCache(key) {
  const entry = mediaCache.get(key);
  if (!entry || entry.expiresAt <= Date.now()) return undefined;
  return entry.data;
}

/**
 * A payload with nothing in it is cached like a failure, not like a success.
 *
 * The backend legitimately answers 200 with an empty list while a snapshot is
 * being rebuilt. Holding that for the full success TTL left the homepage with
 * no card art for five minutes after a momentary blip; at the failure TTL it
 * recovers on the next request.
 */
function writeCache(key, data, isEmpty = false) {
  const shortLived = data === null || isEmpty;
  mediaCache.set(key, {
    data,
    expiresAt: Date.now() + (shortLived ? FAILURE_TTL_MS : SUCCESS_TTL_MS),
  });
}

async function fetchSetModule(slug, backendPath, isEmptyPayload = () => false) {
  const setSlug = String(slug || "").trim();
  if (!setSlug) return null;

  const cacheKey = `${backendPath}:${setSlug}`;
  const cached = readCache(cacheKey);
  if (cached !== undefined) return cached;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const response = await fetch(
      `${BACKEND_URL}/tcgs/pokemon/sets/${encodeURIComponent(setSlug)}/${backendPath}`,
      { cache: "no-store", signal: controller.signal }
    );
    if (!response.ok) {
      console.warn("[landing-set-media] module_unavailable", { setSlug, backendPath, status: response.status });
      writeCache(cacheKey, null);
      return null;
    }
    const payload = await response.json();
    const empty = isEmptyPayload(payload);
    if (empty) {
      console.warn("[landing-set-media] module_empty", { setSlug, backendPath });
    }
    writeCache(cacheKey, payload, empty);
    return payload;
  } catch (error) {
    console.warn("[landing-set-media] module_error", {
      setSlug,
      backendPath,
      error: error?.name === "AbortError" ? "timeout" : String(error?.message || error),
    });
    writeCache(cacheKey, null);
    return null;
  } finally {
    clearTimeout(timer);
  }
}

function hasRows(value) {
  return Array.isArray(value) && value.length > 0;
}

export function getSetChaseCardsPayload(slug) {
  return fetchSetModule(
    slug,
    "market/top-chase",
    (payload) => !hasRows(payload?.topChaseCards) && !hasRows(payload?.top_chase_cards)
  );
}

export function getSetSealedPayload(slug) {
  return fetchSetModule(slug, "market/sealed", (payload) => !hasRows(payload?.products));
}
