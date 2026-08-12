import { cache } from "react";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

const BACKEND_URL = getBackendApiBaseUrl();

const SUCCESS_TTL_MS = 120_000;
const NOT_FOUND_TTL_MS = 10_000;
const DEFAULT_TARGETS_LIMIT = 150;
const MAX_TARGETS_LIMIT = 200;
const MIN_LIMIT = 1;
const TARGETS_REQUEST_FAILED_WARNING =
  "RIP Statistics targets unavailable; continuing with direct set snapshot fallback.";
const TARGETS_STALE_WARNING =
  "RIP Statistics targets request failed; using stale cached targets.";

const targetsCache = new Map();
const inflightRequests = new Map();

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

function toCacheKey() {
  return "rip-statistics-targets";
}

function normalisePayload(payload) {
  const sourceMeta = payload?.meta && typeof payload.meta === "object"
    ? payload.meta
    : { warnings: [], timings: {}, sources: {} };
  const snapshotFallback = Boolean(sourceMeta?.snapshot?.isStaleFallback);
  return {
    targets: Array.isArray(payload?.targets) ? payload.targets : [],
    default_target: payload?.default_target || null,
    meta: {
      ...sourceMeta,
      stale: Boolean(sourceMeta.stale || snapshotFallback),
      fallback: Boolean(sourceMeta.fallback || snapshotFallback),
    },
  };
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

function getRecoverableTargetsPayload(cacheKey, warning) {
  const cached = targetsCache.get(cacheKey);
  if (cached?.data) {
    return withTargetsRequestFailureMeta(cached.data, {
      stale: true,
      fallback: true,
      warning: warning || TARGETS_STALE_WARNING,
    });
  }
  return withTargetsRequestFailureMeta(null, {
    fallback: true,
    warning: warning || TARGETS_REQUEST_FAILED_WARNING,
  });
}

const _fetchRipStatisticsTargets = cache(async function _fetchRipStatisticsTargets() {
  const limit = CANONICAL_COHORT_LIMIT;
  const cacheKey = toCacheKey();
  const now = Date.now();

  const cached = targetsCache.get(cacheKey);
  if (cached && cached.expiresAt > now) {
    console.info("[rip-statistics-server] process_cached_response", { limit });
    return cached.data;
  }

  if (inflightRequests.has(cacheKey)) {
    return inflightRequests.get(cacheKey);
  }

  const promise = (async () => {
    const url = new URL(`${BACKEND_URL}/explore/rip-statistics/targets`);
    url.searchParams.set("limit", String(CANONICAL_COHORT_LIMIT));

    let res;
    try {
      // The bounded process cache below is the single cross-request freshness
      // boundary. A second Next data-cache TTL used to stack with it and could
      // keep a superseded persisted snapshot visible unpredictably longer.
      res = await fetch(url.toString(), { cache: "no-store" });
    } catch (error) {
      const warning = toBackendFailureWarning({ detail: error?.message || String(error) });
      console.warn("[rip-statistics-server] targets_request_failed", {
        limit,
        error: error?.message || String(error),
      });
      console.warn("[rip-statistics-server] stale_fallback", { limit });
      return getRecoverableTargetsPayload(cacheKey, warning);
    }

    if (res.status === 404) {
      const emptyPayload = normalisePayload(null);
      targetsCache.set(cacheKey, {
        data: emptyPayload,
        expiresAt: now + NOT_FOUND_TTL_MS,
      });
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
      return getRecoverableTargetsPayload(cacheKey, warning);
    }

    const payload = normalisePayload(await res.json());
    console.info("[rip-statistics-server] fresh_response", {
      limit,
      builtAt: payload?.meta?.snapshot?.builtAt ?? null,
      marketDate: payload?.meta?.comparisonSnapshots?.currentMarketDate ?? null,
    });
    targetsCache.set(cacheKey, {
      data: payload,
      expiresAt: now + SUCCESS_TTL_MS,
    });
    return payload;
  })().finally(() => {
    inflightRequests.delete(cacheKey);
  });

  inflightRequests.set(cacheKey, promise);
  return promise;
});

export async function getRipStatisticsTargets(options = {}) {
  const limit = sanitiseLimit(options.limit, DEFAULT_TARGETS_LIMIT, MAX_TARGETS_LIMIT);
  const cohort = await _fetchRipStatisticsTargets();
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
