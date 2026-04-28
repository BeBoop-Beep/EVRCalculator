import { cache } from "react";

const BACKEND_URL =
  process.env.BACKEND_API_BASE_URL || "http://127.0.0.1:8000";

const SUCCESS_TTL_MS = 120_000; // 120s
const NOT_FOUND_TTL_MS = 10_000; // 10s
const DEFAULT_DISTRIBUTION_BINS = 50;
const MAX_DISTRIBUTION_BINS = 200;
const DEFAULT_TOP_HITS = 10;
const MAX_TOP_HITS = 50;
const MIN_LIMIT = 1;

/** In-memory TTL cache keyed by target and sanitized limits. */
const explorePageCache = new Map();

/** In-flight promise deduplication */
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

function toCacheKey(targetType, targetId, limitDistributionBins, limitTopHits) {
  return `explore:${targetType}:${targetId}:bins=${limitDistributionBins}:hits=${limitTopHits}`;
}

function normalisePayload(payload) {
  return {
    summary: payload?.summary || {},
    rankings: Array.isArray(payload?.rankings) ? payload.rankings : [],
    rip_statistics: payload?.rip_statistics || {
      pack_paths: {},
      normal_pack_states: {},
    },
    percentiles: Array.isArray(payload?.percentiles) ? payload.percentiles : [],
    distribution_bins: Array.isArray(payload?.distribution_bins)
      ? payload.distribution_bins
      : [],
    threshold_bins: Array.isArray(payload?.threshold_bins)
      ? payload.threshold_bins
      : [],
    top_hits: Array.isArray(payload?.top_hits) ? payload.top_hits : [],
    meta: payload?.meta || { warnings: [], timings: {}, sources: {} },
  };
}

const _fetchExplorePayload = cache(async function _fetchExplorePayload(
  targetType,
  targetId,
  limitDistributionBins,
  limitTopHits
) {
  const cacheKey = toCacheKey(
    targetType,
    targetId,
    limitDistributionBins,
    limitTopHits
  );
  const now = Date.now();

  // TTL cache hit
  const cached = explorePageCache.get(cacheKey);
  if (cached && cached.expiresAt > now) {
    console.info("[explore-page-server] cache_hit", {
      targetType,
      targetId,
      ttlRemainingMs: cached.expiresAt - now,
    });
    return cached.data;
  }

  // In-flight deduplication
  if (inflightRequests.has(cacheKey)) {
    console.info("[explore-page-server] inflight_dedup", { targetType, targetId });
    return inflightRequests.get(cacheKey);
  }

  const promise = (async () => {
    const url = new URL(`${BACKEND_URL}/explore/page`);
    url.searchParams.set("target_type", targetType);
    url.searchParams.set("target_id", targetId);
    url.searchParams.set("limit_distribution_bins", String(limitDistributionBins));
    url.searchParams.set("limit_top_hits", String(limitTopHits));

    const startedAt = Date.now();
    console.info("[explore-page-server] fetch_start", { targetType, targetId });

    let res;
    try {
      res = await fetch(url.toString(), { cache: "no-store" });
    } catch (networkErr) {
      console.error("[explore-page-server] network_error", {
        targetType,
        targetId,
        error: String(networkErr),
      });
      throw networkErr;
    }

    const elapsedMs = Date.now() - startedAt;

    if (res.status === 404) {
      console.warn("[explore-page-server] not_found", { targetType, targetId });
      const notFoundPayload = null;
      explorePageCache.set(cacheKey, {
        data: notFoundPayload,
        cachedAt: now,
        expiresAt: now + NOT_FOUND_TTL_MS,
      });
      return notFoundPayload;
    }

    if (!res.ok) {
      const body = await res.text().catch(() => "");
      console.error("[explore-page-server] fetch_error", {
        targetType,
        targetId,
        status: res.status,
        body,
        elapsedMs,
      });
      throw new Error(`Explore page backend error ${res.status}`);
    }

    const payload = await res.json();
    const normalised = normalisePayload(payload);

    console.info("[explore-page-server] fetch_success", {
      targetType,
      targetId,
      elapsedMs,
      warnings: normalised.meta?.warnings?.length ?? 0,
    });

    explorePageCache.set(cacheKey, {
      data: normalised,
      cachedAt: now,
      expiresAt: now + SUCCESS_TTL_MS,
    });

    return normalised;
  })().finally(() => {
    inflightRequests.delete(cacheKey);
  });

  inflightRequests.set(cacheKey, promise);
  return promise;
});

/**
 * Load the Explore page payload for a given target.
 * Safe to call from any React Server Component.
 *
 * @param {string} targetTypeParam
 * @param {string} targetIdParam
 * @param {{ limitDistributionBins?: number, limitTopHits?: number }} options
 */
export async function getExplorePagePayload(
  targetTypeParam,
  targetIdParam,
  options = {}
) {
  const targetType = String(targetTypeParam || "").trim();
  const targetId = String(targetIdParam || "").trim();
  const limitDistributionBins = sanitiseLimit(
    options.limitDistributionBins,
    DEFAULT_DISTRIBUTION_BINS,
    MAX_DISTRIBUTION_BINS
  );
  const limitTopHits = sanitiseLimit(
    options.limitTopHits,
    DEFAULT_TOP_HITS,
    MAX_TOP_HITS
  );

  return _fetchExplorePayload(targetType, targetId, limitDistributionBins, limitTopHits);
}
