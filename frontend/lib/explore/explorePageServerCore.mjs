const DEFAULT_SET_PAGE_WARNING = "Set page backend payload unavailable; rendered fallback shell.";
const TIMEOUT_SET_PAGE_WARNING = "Set page snapshot request timed out; retrying.";
const STALE_SET_PAGE_WARNING = "Using stale set page payload because backend refresh failed.";
const BODY_PREVIEW_LIMIT = 500;

function toOptionalString(value) {
  const text = String(value || "").trim();
  return text || null;
}

function toOptionalNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function appendUnique(list, value) {
  const next = Array.isArray(list) ? [...list] : [];
  if (value && !next.includes(value)) {
    next.push(value);
  }
  return next;
}

export function previewResponseBody(body, limit = BODY_PREVIEW_LIMIT) {
  const text = String(body || "");
  return text.length > limit ? `${text.slice(0, limit)}...` : text;
}

export function sanitizeBackendPath(urlLike) {
  try {
    return new URL(String(urlLike)).pathname;
  } catch {
    const text = String(urlLike || "");
    const pathStart = text.indexOf("/");
    return pathStart >= 0 ? text.slice(pathStart).split("?")[0] : text;
  }
}

export function normalisePayload(payload) {
  return {
    summary: payload?.summary || {},
    rankings: Array.isArray(payload?.rankings) ? payload.rankings : [],
    rip_statistics: payload?.rip_statistics || {
      pack_paths: {},
      normal_pack_states: {},
    },
    percentiles: Array.isArray(payload?.percentiles) ? payload.percentiles : [],
    distribution_bins: Array.isArray(payload?.distribution_bins) ? payload.distribution_bins : [],
    threshold_bins: Array.isArray(payload?.threshold_bins) ? payload.threshold_bins : [],
    top_hits: Array.isArray(payload?.top_hits) ? payload.top_hits : [],
    history_trend: Array.isArray(payload?.history_trend) ? payload.history_trend : [],
    openingDesirability: payload?.openingDesirability || payload?.opening_desirability || null,
    pull_rate_assumptions: payload?.pull_rate_assumptions || payload?.pullRateAssumptions || null,
    interpretation: payload?.interpretation || {},
    meta: payload?.meta || { warnings: [], timings: {}, sources: {} },
  };
}

export function isSetPageRequestTimeoutPayload(payload) {
  const meta = payload?.meta || {};
  if (meta.requestTimeout === true || meta.fallbackReason === "request_timeout" || meta.isTransportFallback === true) {
    return true;
  }
  const errors = Array.isArray(meta.errors) ? meta.errors : [];
  return errors.some((error) => String(error?.code || "").includes("TIMEOUT"));
}

function getFallbackSummary({ targetId, fallbackTarget }) {
  const target = fallbackTarget && typeof fallbackTarget === "object" ? fallbackTarget : {};
  const targetSummary = target.summary && typeof target.summary === "object" ? target.summary : {};
  const resolvedTargetId = toOptionalString(target.target_id ?? target.id ?? targetId);
  const name = toOptionalString(target.name ?? target.set_name ?? target.label ?? targetId);

  return {
    ...targetSummary,
    target_id: resolvedTargetId,
    set_id: toOptionalString(target.set_id ?? target.id ?? resolvedTargetId),
    name,
    slug: toOptionalString(target.slug),
    canonical_key: toOptionalString(target.canonical_key),
    era: toOptionalString(target.era),
    logo_url: toOptionalString(target.logo_url ?? target.logoUrl),
    image_url: toOptionalString(target.image_url ?? target.imageUrl),
    pack_score: toOptionalNumber(targetSummary.pack_score ?? target.pack_score),
    relative_pack_score: toOptionalNumber(targetSummary.relative_pack_score ?? target.relative_pack_score),
  };
}

function getRecoverableError({
  code = "SET_PAGE_PAYLOAD_UNAVAILABLE",
  status = null,
  elapsedMs = null,
  backendPath = null,
  bodyPreview = null,
  message = null,
}) {
  return {
    code,
    status,
    elapsedMs,
    backendPath,
    bodyPreview,
    message: message ? previewResponseBody(message, BODY_PREVIEW_LIMIT) : null,
  };
}

export function buildFallbackSetPagePayload({
  targetId,
  fallbackTarget = null,
  status = null,
  elapsedMs = null,
  backendPath = null,
  bodyPreview = null,
  code = "SET_PAGE_PAYLOAD_UNAVAILABLE",
  message = null,
  requestTimeout = false,
} = {}) {
  const fallbackReason = requestTimeout
    ? "request_timeout"
    : status === 404 || code === "SET_PAGE_PAYLOAD_NOT_FOUND"
    ? "snapshot_missing"
    : code === "SET_PAGE_PAYLOAD_BACKEND_ERROR"
    ? "backend_error"
    : "local_fallback_shell";
  return normalisePayload({
    summary: getFallbackSummary({ targetId, fallbackTarget }),
    rankings: [],
    rip_statistics: { pack_paths: {}, normal_pack_states: {} },
    percentiles: [],
    distribution_bins: [],
    threshold_bins: [],
    top_hits: [],
    history_trend: [],
    openingDesirability: null,
    pull_rate_assumptions: null,
    interpretation: {},
    meta: {
      warnings: [requestTimeout ? TIMEOUT_SET_PAGE_WARNING : DEFAULT_SET_PAGE_WARNING],
      errors: [
        getRecoverableError({
          code,
          status,
          elapsedMs,
          backendPath,
          bodyPreview,
          message,
        }),
      ],
      fallback: true,
      fallbackReason,
      requestTimeout: Boolean(requestTimeout),
      isTransportFallback: Boolean(requestTimeout),
      stale: false,
      sources: {
        setPage: requestTimeout ? "timeout_fallback" : "fallback",
      },
    },
  });
}

export function withStaleSetPageDiagnostics(
  payload,
  { status = null, elapsedMs = null, backendPath = null, bodyPreview = null, code = "SET_PAGE_PAYLOAD_STALE_FALLBACK", message = null } = {}
) {
  const normalised = normalisePayload(payload);
  const meta = normalised.meta && typeof normalised.meta === "object" ? { ...normalised.meta } : {};
  const sources = meta.sources && typeof meta.sources === "object" ? { ...meta.sources } : {};
  const requestTimeout = code === "SET_PAGE_PAYLOAD_TIMEOUT" || isSetPageRequestTimeoutPayload({ meta });
  return {
    ...normalised,
    meta: {
      ...meta,
      warnings: appendUnique(meta.warnings, requestTimeout ? TIMEOUT_SET_PAGE_WARNING : STALE_SET_PAGE_WARNING),
      errors: [
        ...(Array.isArray(meta.errors) ? meta.errors : []),
        getRecoverableError({
          code,
          status,
          elapsedMs,
          backendPath,
          bodyPreview,
          message,
        }),
      ],
      stale: true,
      requestTimeout: requestTimeout || meta.requestTimeout === true,
      isTransportFallback: requestTimeout || meta.isTransportFallback === true,
      fallbackReason: requestTimeout ? "request_timeout" : meta.fallbackReason,
      sources: {
        ...sources,
        setPage: "stale_cache",
      },
    },
  };
}

export function getRecoverableExplorePayload({
  targetType,
  targetId,
  fallbackTarget = null,
  staleEntry = null,
  now = Date.now(),
  status = null,
  elapsedMs = null,
  backendPath = null,
  bodyPreview = null,
  code,
  message = null,
} = {}) {
  if (String(targetType || "").trim() !== "set") {
    return null;
  }
  if (staleEntry?.data && staleEntry.staleExpiresAt && staleEntry.staleExpiresAt > now) {
    return withStaleSetPageDiagnostics(staleEntry.data, {
      status,
      elapsedMs,
      backendPath,
      bodyPreview,
      code: code || "SET_PAGE_PAYLOAD_STALE_FALLBACK",
      message,
    });
  }
  return buildFallbackSetPagePayload({
    targetId,
    fallbackTarget,
    status,
    elapsedMs,
    backendPath,
    bodyPreview,
    code: code || "SET_PAGE_PAYLOAD_UNAVAILABLE",
    message,
    requestTimeout: code === "SET_PAGE_PAYLOAD_TIMEOUT",
  });
}

export async function fetchWithTimeout(url, options = {}, timeoutMs = 0, fetchImpl = globalThis.fetch) {
  if (!timeoutMs || timeoutMs <= 0) {
    return fetchImpl(url, options);
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetchImpl(url, {
      ...options,
      signal: controller.signal,
    });
  } catch (error) {
    if (controller.signal.aborted) {
      const timeoutError = new Error(`Explore page fetch timed out after ${timeoutMs}ms`);
      timeoutError.name = "TimeoutError";
      timeoutError.cause = error;
      throw timeoutError;
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}
