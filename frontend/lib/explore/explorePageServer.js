import { cache } from "react";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";
import {
  fetchWithTimeout,
  getRecoverableExplorePayload,
  normalisePayload,
  previewResponseBody,
  sanitizeBackendPath,
} from "./explorePageServerCore.mjs";

const BACKEND_URL = getBackendApiBaseUrl();

function readPositiveIntegerEnv(name, fallback) {
  const parsed = Number.parseInt(process.env[name] || "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

const SUCCESS_TTL_MS = 120_000; // 120s
const NOT_FOUND_TTL_MS = 10_000; // 10s
const STALE_TTL_MS = readPositiveIntegerEnv("EXPLORE_PAGE_STALE_TTL_MS", 3_600_000);
const SET_PAGE_FETCH_TIMEOUT_MS = readPositiveIntegerEnv("EXPLORE_PAGE_SET_FETCH_TIMEOUT_MS", 3_000);
const EXPLORE_PAGE_FETCH_TIMEOUT_MS = readPositiveIntegerEnv("EXPLORE_PAGE_FETCH_TIMEOUT_MS", 10_000);
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

function getFetchTimeoutMs(targetType) {
  return targetType === "set" ? SET_PAGE_FETCH_TIMEOUT_MS : EXPLORE_PAGE_FETCH_TIMEOUT_MS;
}

function logRecoverableSetPagePayload(eventName, {
  targetType,
  targetId,
  backendPath,
  status = null,
  elapsedMs = null,
  source,
  fallbackUsed = false,
  bodyPreview = null,
}) {
  console.warn(`[explore-page-server] ${eventName}`, {
    targetType,
    targetId,
    backendPath,
    status,
    elapsedMs,
    source,
    fallbackUsed,
    bodyPreview,
  });
}

const _fetchExplorePayload = cache(async function _fetchExplorePayload(
  targetType,
  targetId,
  limitDistributionBins,
  limitTopHits,
  fallbackTarget = null
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
      source: "cache",
      fallbackUsed: false,
      ttlRemainingMs: cached.expiresAt - now,
    });
    return cached.data;
  }

  // In-flight deduplication
  if (inflightRequests.has(cacheKey)) {
    console.info("[explore-page-server] inflight_dedup", {
      targetType,
      targetId,
      source: "inflight",
      fallbackUsed: false,
    });
    return inflightRequests.get(cacheKey);
  }

  const promise = (async () => {
    const isPokemonSetPage = targetType === "set";
    const url = isPokemonSetPage
      ? new URL(`${BACKEND_URL}/tcgs/pokemon/sets/${encodeURIComponent(targetId)}/page`)
      : new URL(`${BACKEND_URL}/explore/page`);
    if (!isPokemonSetPage) {
      url.searchParams.set("target_type", targetType);
      url.searchParams.set("target_id", targetId);
      url.searchParams.set("limit_distribution_bins", String(limitDistributionBins));
      url.searchParams.set("limit_top_hits", String(limitTopHits));
    }
    const backendPath = sanitizeBackendPath(url);
    const timeoutMs = getFetchTimeoutMs(targetType);

    const startedAt = Date.now();
    console.info("[explore-page-server] fetch_start", {
      targetType,
      targetId,
      backendPath,
      source: "backend",
      fallbackUsed: false,
      timeoutMs,
    });

    let res;
    try {
      res = await fetchWithTimeout(url.toString(), { next: { revalidate: 300 } }, timeoutMs);
    } catch (networkErr) {
      const elapsedMs = Date.now() - startedAt;
      const isTimeout = networkErr?.name === "TimeoutError";
      const recoverablePayload = getRecoverableExplorePayload({
        targetType,
        targetId,
        fallbackTarget,
        staleEntry: cached,
        now: Date.now(),
        elapsedMs,
        backendPath,
        code: isTimeout ? "SET_PAGE_PAYLOAD_TIMEOUT" : "SET_PAGE_PAYLOAD_NETWORK_ERROR",
        message: String(networkErr?.message || networkErr),
      });
      if (recoverablePayload) {
        logRecoverableSetPagePayload(isTimeout ? "fetch_timeout_fallback" : "network_error_fallback", {
          targetType,
          targetId,
          backendPath,
          elapsedMs,
          source: recoverablePayload.meta?.stale ? "stale_cache" : "fallback",
          fallbackUsed: true,
          bodyPreview: previewResponseBody(networkErr?.message || String(networkErr)),
        });
        return recoverablePayload;
      }
      console.error("[explore-page-server] network_error", {
        targetType,
        targetId,
        backendPath,
        elapsedMs,
        source: "backend",
        fallbackUsed: false,
        error: String(networkErr),
      });
      throw networkErr;
    }

    const elapsedMs = Date.now() - startedAt;

    if (res.status === 404) {
      if (isPokemonSetPage) {
        const body = await res.text().catch(() => "");
        const recoverablePayload = getRecoverableExplorePayload({
          targetType,
          targetId,
          fallbackTarget,
          staleEntry: cached,
          now: Date.now(),
          status: res.status,
          elapsedMs,
          backendPath,
          bodyPreview: previewResponseBody(body),
          code: "SET_PAGE_PAYLOAD_NOT_FOUND",
        });
        logRecoverableSetPagePayload("not_found_fallback", {
          targetType,
          targetId,
          backendPath,
          status: res.status,
          elapsedMs,
          source: recoverablePayload.meta?.stale ? "stale_cache" : "fallback",
          fallbackUsed: true,
          bodyPreview: previewResponseBody(body),
        });
        return recoverablePayload;
      }
      console.warn("[explore-page-server] not_found", {
        targetType,
        targetId,
        backendPath,
        status: res.status,
        elapsedMs,
        source: "backend",
        fallbackUsed: false,
      });
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
      const bodyPreview = previewResponseBody(body);
      const recoverablePayload = getRecoverableExplorePayload({
        targetType,
        targetId,
        fallbackTarget,
        staleEntry: cached,
        now: Date.now(),
        status: res.status,
        elapsedMs,
        backendPath,
        bodyPreview,
        code: "SET_PAGE_PAYLOAD_BACKEND_ERROR",
      });
      if (recoverablePayload) {
        logRecoverableSetPagePayload("fetch_error_fallback", {
          targetType,
          targetId,
          backendPath,
          status: res.status,
          elapsedMs,
          source: recoverablePayload.meta?.stale ? "stale_cache" : "fallback",
          fallbackUsed: true,
          bodyPreview,
        });
        return recoverablePayload;
      }
      console.error("[explore-page-server] fetch_error", {
        targetType,
        targetId,
        backendPath,
        status: res.status,
        bodyPreview,
        elapsedMs,
        source: "backend",
        fallbackUsed: false,
      });
      throw new Error(`Explore page backend error ${res.status}`);
    }

    let payload;
    try {
      payload = await res.json();
    } catch (parseErr) {
      const recoverablePayload = getRecoverableExplorePayload({
        targetType,
        targetId,
        fallbackTarget,
        staleEntry: cached,
        now: Date.now(),
        status: res.status,
        elapsedMs,
        backendPath,
        code: "SET_PAGE_PAYLOAD_INVALID_JSON",
        message: String(parseErr?.message || parseErr),
      });
      if (recoverablePayload) {
        logRecoverableSetPagePayload("invalid_json_fallback", {
          targetType,
          targetId,
          backendPath,
          status: res.status,
          elapsedMs,
          source: recoverablePayload.meta?.stale ? "stale_cache" : "fallback",
          fallbackUsed: true,
          bodyPreview: previewResponseBody(parseErr?.message || String(parseErr)),
        });
        return recoverablePayload;
      }
      throw parseErr;
    }
    const normalised = normalisePayload(payload);

    console.info("[explore-page-server] fetch_success", {
      targetType,
      targetId,
      backendPath,
      elapsedMs,
      source: "backend",
      fallbackUsed: false,
      warnings: normalised.meta?.warnings?.length ?? 0,
    });

    explorePageCache.set(cacheKey, {
      data: normalised,
      cachedAt: now,
      expiresAt: now + SUCCESS_TTL_MS,
      staleExpiresAt: now + STALE_TTL_MS,
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
 * @param {{ limitDistributionBins?: number, limitTopHits?: number, fallbackTarget?: object }} options
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

  return _fetchExplorePayload(
    targetType,
    targetId,
    limitDistributionBins,
    limitTopHits,
    options.fallbackTarget || null
  );
}
