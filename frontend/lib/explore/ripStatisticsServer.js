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

function toCacheKey(limit) {
  return `rip-statistics-targets:${limit}`;
}

function normalisePayload(payload) {
  return {
    targets: Array.isArray(payload?.targets) ? payload.targets : [],
    default_target: payload?.default_target || null,
    meta: payload?.meta || { warnings: [], timings: {}, sources: {} },
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

const _fetchRipStatisticsTargets = cache(async function _fetchRipStatisticsTargets(limit) {
  const cacheKey = toCacheKey(limit);
  const now = Date.now();

  const cached = targetsCache.get(cacheKey);
  if (cached && cached.expiresAt > now) {
    return cached.data;
  }

  if (inflightRequests.has(cacheKey)) {
    return inflightRequests.get(cacheKey);
  }

  const promise = (async () => {
    const url = new URL(`${BACKEND_URL}/explore/rip-statistics/targets`);
    url.searchParams.set("limit", String(limit));

    let res;
    try {
      res = await fetch(url.toString(), { next: { revalidate: 300 } });
    } catch (error) {
      const warning = toBackendFailureWarning({ detail: error?.message || String(error) });
      console.warn("[rip-statistics-server] targets_request_failed", {
        limit,
        error: error?.message || String(error),
      });
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
  return _fetchRipStatisticsTargets(limit);
}
