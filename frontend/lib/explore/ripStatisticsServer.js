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

async function _fetchRipStatisticsTargets(request = null, { publicOnly = false } = {}) {
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
