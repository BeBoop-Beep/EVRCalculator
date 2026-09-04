import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";
import { getBackendRequestAuthHeaders, getPublicBackendRequestHeaders } from "@/lib/authServer";
import { normaliseRipStatisticsPayload } from "./ripStatisticsNormalizer.mjs";

const BACKEND_URL = getBackendApiBaseUrl();

const DEFAULT_TARGETS_LIMIT = 150;
const MAX_TARGETS_LIMIT = 200;
const MIN_LIMIT = 1;
const TARGETS_REQUEST_FAILED_WARNING =
  "RIP Statistics targets unavailable; continuing with direct set snapshot fallback.";
const TARGETS_STALE_WARNING =
  "RIP Statistics targets request failed; using stale cached targets.";


function sanitiseLimit(value, defaultValue, maxValue) {
  const parsed = Number.parseInt(String(value), 10);
  if (Number.isNaN(parsed)) {
    return defaultValue;
  }
  if (parsed < MIN_LIMIT) {
    return MIN_LIMIT;
  }
  if (parsed > maxValue) {
    return maxValue;
  }
  return parsed;
}

// The backend builds the ENTIRE target cohort regardless of `limit` and only
// then truncates it: `meta.timings` is byte-identical for limit=5 and
// limit=200, and the limit=5 targets are an exact prefix of limit=200. So a
// small limit buys no backend work, while a per-limit cache key costs a second
// full ~1.6s cold computation whenever a caller asking for 60 (Rankings,
// Market, landing) is followed by one asking for 150 (set detail) — which is
// precisely the Rankings -> Set navigation. One cohort is fetched and cached
// once; each caller's `limit` is applied by slicing that shared result.
const CANONICAL_COHORT_LIMIT = MAX_TARGETS_LIMIT;

// Bounded process cache + in-flight join for the canonical cohort fetch.
// publicOnly and authenticated reads are cached separately (public headers
// vs ambient session headers must never cross-pollinate), each with its own
// 120s TTL consistent with the snapshot's prior publication cadence. Fresh
// miss -> one backend read; concurrent misses -> one backend request with
// every waiter joining the same in-flight promise; warm reads inside TTL
// short-circuit entirely; TTL expiry triggers exactly one refresh; a failed
// refresh falls back to the existing recoverable/stale payload shape rather
// than serving stale-forever.
const COHORT_TTL_MS = 120_000;
const cohortCache = new Map(); // key -> { data, expiresAt }
const cohortInFlight = new Map(); // key -> Promise

export function __resetRipStatisticsTargetsCacheForTests() {
  cohortCache.clear();
  cohortInFlight.clear();
}

export function normalisePayload(payload) {
  return normaliseRipStatisticsPayload(payload);
}

function appendUnique(list, value) {
  const next = Array.isArray(list) ? [...list] : [];
  if (value && !next.includes(value)) {
    next.push(value);
  }
  return next;
}

function withTargetsRequestFailureMeta(payload, { stale = false, fallback = false, warning = TARGETS_REQUEST_FAILED_WARNING } = {}) {
  const normalised = normalisePayload(payload);
  const meta = normalised.meta && typeof normalised.meta === "object" ? { ...normalised.meta } : {};
  return {
    ...normalised,
    meta: {
      ...meta,
      stale: Boolean(stale || meta.stale),
      fallback: Boolean(fallback || meta.fallback),
      requestFailed: true,
      warnings: appendUnique(meta.warnings, warning),
    },
  };
}

function toBackendFailureWarning({ status = null, detail = null } = {}) {
  const statusText = status ? `status ${status}` : "request error";
  const detailText = String(detail || "").trim();
  if (!detailText) {
    return `${TARGETS_REQUEST_FAILED_WARNING} (${statusText})`;
  }
  return `${TARGETS_REQUEST_FAILED_WARNING} (${statusText}: ${detailText})`;
}

function getRecoverableTargetsPayload(warning) {
  return withTargetsRequestFailureMeta(null, {
    fallback: true,
    warning: warning || TARGETS_REQUEST_FAILED_WARNING,
  });
}

async function _fetchRipStatisticsTargetsUncached(request = null, { publicOnly = false } = {}) {
  const limit = CANONICAL_COHORT_LIMIT;
    const url = new URL(`${BACKEND_URL}/explore/rip-statistics/targets`);
    url.searchParams.set("limit", String(CANONICAL_COHORT_LIMIT));

    let res;
    try {
      // The bounded process cache below is the single cross-request freshness
      // boundary. A second Next data-cache TTL used to stack with it and could
      // keep a superseded persisted snapshot visible unpredictably longer.
      //
      // publicOnly callers (the homepage/landing reader) must never resolve
      // ambient request cookies/headers, so they get the fixed public header
      // set instead of getBackendRequestAuthHeaders(request).
      res = await fetch(url.toString(), {
        cache: "no-store",
        headers: publicOnly
          ? await getPublicBackendRequestHeaders()
          : await getBackendRequestAuthHeaders(request),
      });
    } catch (error) {
      const warning = toBackendFailureWarning({ detail: error?.message || String(error) });
      console.warn("[rip-statistics-server] targets_request_failed", {
        limit,
        error: error?.message || String(error),
      });
      console.warn("[rip-statistics-server] stale_fallback", { limit });
      return getRecoverableTargetsPayload(warning);
    }

    if (res.status === 404) {
      const emptyPayload = normalisePayload(null);
      return emptyPayload;
    }

    if (!res.ok) {
      const body = await res.text().catch(() => "");
      const bodyPreview = body.slice(0, 500);
      const warning = toBackendFailureWarning({ status: res.status, detail: bodyPreview });
      console.warn("[rip-statistics-server] targets_backend_error", {
        limit,
        status: res.status,
        bodyPreview,
      });
      return getRecoverableTargetsPayload(warning);
    }

    const payload = normalisePayload(await res.json());
    console.info("[rip-statistics-server] fresh_response", {
      limit,
      builtAt: payload?.meta?.snapshot?.builtAt ?? null,
      marketDate: payload?.meta?.comparisonSnapshots?.currentMarketDate ?? null,
    });
    return payload;
}

// Only the publicOnly cohort (fixed Accept-only headers, identical for every
// visitor) is ever process-cached or in-flight-joined here. Authenticated
// reads resolve ambient session/plan headers and MUST stay uncached — a
// Plus/Premium response cached under a bare "authenticated" key would leak
// across a Base viewer's request within the TTL window. This deliberately
// preserves the pre-existing "no cross-request cache for entitlement-
// sensitive cohorts" contract for the authenticated path while giving the
// Homepage's publicOnly reader the bounded cache/in-flight-join required by
// this effort.
const PUBLIC_COHORT_KEY = "public";

async function _fetchRipStatisticsTargets(request = null, { publicOnly = false } = {}) {
  if (!publicOnly) {
    return _fetchRipStatisticsTargetsUncached(request, { publicOnly: false });
  }
  const key = PUBLIC_COHORT_KEY;
  const cached = cohortCache.get(key);
  if (cached && cached.expiresAt > Date.now()) {
    console.info("[rip-statistics-server] cache_hit", { key });
    return cached.data;
  }
  const existingInFlight = cohortInFlight.get(key);
  if (existingInFlight) {
    console.info("[rip-statistics-server] in_flight_join", { key });
    return existingInFlight;
  }
  const startedAt = Date.now();
  const promise = (async () => {
    try {
      const data = await _fetchRipStatisticsTargetsUncached(request, { publicOnly: true });
      // Never cache a recoverable/fallback payload as if it were a fresh
      // cohort — that would hide a real outage behind a fake TTL hit and
      // could also hide a genuinely new publication indefinitely.
      if (!data?.meta?.requestFailed) {
        cohortCache.set(key, { data, expiresAt: Date.now() + COHORT_TTL_MS });
      }
      console.info("[rip-statistics-server] cohort_fetch_complete", {
        key,
        elapsedMs: Date.now() - startedAt,
        requestFailed: Boolean(data?.meta?.requestFailed),
      });
      return data;
    } finally {
      cohortInFlight.delete(key);
    }
  })();
  cohortInFlight.set(key, promise);
  return promise;
}

export async function getRipStatisticsTargets(options = {}) {
  const limit = sanitiseLimit(options.limit, DEFAULT_TARGETS_LIMIT, MAX_TARGETS_LIMIT);
  const cohort = await _fetchRipStatisticsTargets(options.request || null, {
    publicOnly: Boolean(options.public),
  });
  // Return a fresh payload per caller — the cached cohort object is shared by
  // every consumer in this process and must never be truncated in place.
  return {
    ...cohort,
    targets: cohort.targets.slice(0, limit),
    meta: {
      ...cohort.meta,
      // Report back what this caller asked for, not the canonical cohort size.
      request: { ...(cohort.meta?.request || {}), limit },
    },
  };
}
