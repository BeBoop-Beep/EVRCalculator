import { PRICING_SNAPSHOT_CONTRACT_VERSION } from "./pricingSnapshotContract.mjs";
import {
  isRetryableTopChaseStatus,
  validateTopChasePayload,
} from "./topChasePayloadContract.mjs";

function toOptionalString(value) {
  const text = String(value || "").trim();
  return text || null;
}

const MARKET_DASHBOARD_TTL_MS = 6 * 60 * 60 * 1000;
const marketDashboardCache = new Map();
const marketDashboardInflight = new Map();
const isDev = process.env.NODE_ENV !== "production";
const RETRYABLE_SNAPSHOT_STATUSES = new Set([404, 500, 502, 503, 504]);
const DEFAULT_MARKET_DASHBOARD_WINDOW = "365d";

// Shared in-flight join map for the slim per-module Overview fetches
// (overview, top-chase, movers, value-history). React 18 StrictMode
// double-invokes effects in development, and each of these effects has no
// AbortController — only a local isCancelled flag that ignores the second
// result. Both requests still hit the network, doubling load on an already
// slow backend read path (see pokemon_set_market_service.py market movers)
// and occasionally tripping a Windows httpx/HTTP2 connection-pool race under
// concurrent duplicate load. Joining identical concurrent calls onto one
// in-flight promise (same pattern as marketDashboardInflight above) removes
// the duplicate network round trip without adding any persistent caching.
const slimModuleInflight = new Map();
const SET_VALUE_SNAPSHOT_CONTRACT_VERSION = "set-value-v2";

// Bounded completion policy for the slim module fetches.
//
// The Next proxy already aborts a stalled backend read after
// BACKEND_FETCH_TIMEOUT_MS (12s) and answers with a structured, retryable 504
// (see lib/pokemon/slimSetModuleProxyContract.mjs). This client-side bound is
// the backstop for the leg the proxy cannot cover — a browser->Next request
// that never produces a response at all. Without it, such a request left the
// section's Promise permanently unsettled, which both stranded the section on
// its skeleton and pinned this key in slimModuleInflight (only cleared in
// .finally()), so every later visit and every Retry joined the same dead
// Promise instead of issuing a new request.
//
// Deliberately larger than the proxy's own timeout so an ordinary slow read
// still completes normally and is reported by the proxy, not pre-empted here.
const SLIM_MODULE_REQUEST_TIMEOUT_MS = 20_000;

export function createSlimModuleTimeoutError() {
  const error = new Error("This section timed out while loading.");
  error.code = "SLIM_MODULE_REQUEST_TIMEOUT";
  error.status = 504;
  error.retryable = true;
  error.isTimeout = true;
  return error;
}

/**
 * Join identical concurrent calls onto one in-flight request, and guarantee
 * that request settles. The key is released on success, on error and on
 * timeout, so a retry always creates a fresh request rather than joining a
 * request that can never resolve.
 *
 * `manageSignal` (default true) wraps the whole joined operation in ONE
 * AbortController + timeout. That is correct for a single-attempt module, but
 * wrong for an operation that makes more than one attempt: once the shared
 * controller aborts, every later attempt inherits an already-aborted signal and
 * fails instantly. Multi-attempt callers pass `manageSignal: false` and bound
 * each attempt themselves (see `runTopChaseAttempt`). The in-flight join/release
 * semantics are identical either way.
 */
function joinSlimModuleRequest(key, factory, { manageSignal = true } = {}) {
  if (slimModuleInflight.has(key)) {
    return slimModuleInflight.get(key);
  }

  if (!manageSignal) {
    const unmanaged = Promise.resolve()
      .then(() => factory({ signal: undefined }))
      .finally(() => {
        slimModuleInflight.delete(key);
      });
    slimModuleInflight.set(key, unmanaged);
    return unmanaged;
  }

  const controller = typeof AbortController === "function" ? new AbortController() : null;
  let timeoutHandle = null;

  const request = new Promise((resolve, reject) => {
    timeoutHandle = setTimeout(() => {
      // Abort the underlying request so the socket is released, then settle
      // the Promise as an error the section can render a Retry for.
      try {
        controller?.abort();
      } catch {
        // An environment without abort support still gets a settled Promise.
      }
      debugTiming("slim_module.request_timeout", { key, timeoutMs: SLIM_MODULE_REQUEST_TIMEOUT_MS });
      reject(createSlimModuleTimeoutError());
    }, SLIM_MODULE_REQUEST_TIMEOUT_MS);

    Promise.resolve()
      .then(() => factory({ signal: controller?.signal }))
      .then(resolve, reject);
  }).finally(() => {
    if (timeoutHandle) {
      clearTimeout(timeoutHandle);
    }
    slimModuleInflight.delete(key);
  });

  slimModuleInflight.set(key, request);
  return request;
}

export function __getSlimModuleInflightSizeForTests() {
  return slimModuleInflight.size;
}

export function __hasSlimModuleInflightForTests(key) {
  return slimModuleInflight.has(key);
}

function nowMs() {
  return Date.now();
}

function debugTiming(label, details = {}) {
  if (!isDev) {
    return;
  }
  console.debug(`[pokemon-set-perf] ${label}`, details);
}

export function normalizeMarketDashboardWindow(window = DEFAULT_MARKET_DASHBOARD_WINDOW) {
  const text = String(window || DEFAULT_MARKET_DASHBOARD_WINDOW).trim();
  return (text || DEFAULT_MARKET_DASHBOARD_WINDOW).toLowerCase();
}

function getMarketDashboardCacheKey(setId, { window = DEFAULT_MARKET_DASHBOARD_WINDOW, days = null } = {}) {
  return `pokemon-market-dashboard:${String(setId || "").trim()}:window=${normalizeMarketDashboardWindow(window)}:days=${days || ""}`;
}

function readMarketDashboardCache(cacheKey, { allowStale = false } = {}) {
  const cached = marketDashboardCache.get(cacheKey);
  if (!cached) {
    return null;
  }
  if (!allowStale && cached.expiresAt <= nowMs()) {
    if (cached) {
      marketDashboardCache.delete(cacheKey);
    }
    return null;
  }
  return cached.payload;
}

function writeMarketDashboardCache(cacheKey, payload) {
  marketDashboardCache.set(cacheKey, {
    payload,
    cachedAt: nowMs(),
    expiresAt: nowMs() + MARKET_DASHBOARD_TTL_MS,
  });
}

function wait(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function isRetryableSnapshotError(error) {
  return RETRYABLE_SNAPSHOT_STATUSES.has(Number(error?.status));
}

function toOptionalNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizeDateKey(value) {
  const text = String(value || "").trim();
  if (!text) {
    return null;
  }
  if (/^\d{4}-\d{2}-\d{2}/.test(text)) {
    return text.slice(0, 10);
  }
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) {
    return text.slice(0, 10) || null;
  }
  return date.toISOString().slice(0, 10);
}

function normalizeDailyPriceHistory(history) {
  const dailyPoints = new Map();

  (Array.isArray(history) ? history : []).forEach((point) => {
    const date = normalizeDateKey(point?.date ?? point?.capturedAt ?? point?.captured_at);
    const marketPrice = toOptionalNumber(point?.marketPrice ?? point?.market_price ?? point?.price);
    if (!date) {
      return;
    }
    dailyPoints.set(date, {
      date,
      marketPrice,
      source: toOptionalString(point?.source ?? point?.provider),
      provider: toOptionalString(point?.provider ?? point?.source),
      conditionId: toOptionalString(point?.conditionId ?? point?.condition_id),
      condition_id: toOptionalString(point?.condition_id ?? point?.conditionId),
      isObserved: Boolean(point?.isObserved ?? point?.is_observed),
      is_observed: Boolean(point?.is_observed ?? point?.isObserved),
      isCarriedForward: Boolean(point?.isCarriedForward ?? point?.is_carried_forward),
      is_carried_forward: Boolean(point?.is_carried_forward ?? point?.isCarriedForward),
      sourceDate: toOptionalString(point?.sourceDate ?? point?.source_date),
      source_date: toOptionalString(point?.source_date ?? point?.sourceDate),
    });
  });

  return Array.from(dailyPoints.values()).sort((a, b) => a.date.localeCompare(b.date));
}

function getPriceHistoryStats(history) {
  const validPoints = (Array.isArray(history) ? history : []).filter((point) => {
    const date = String(point?.date || "").slice(0, 10);
    return /^\d{4}-\d{2}-\d{2}$/.test(date) && toOptionalNumber(point?.marketPrice ?? point?.market_price ?? point?.price) !== null;
  });

  return {
    pointCount: validPoints.length,
    startDate: validPoints[0]?.date || null,
    endDate: validPoints[validPoints.length - 1]?.date || null,
  };
}

function chooseTopChaseHistory(embeddedHistory, mappedHistory) {
  const embeddedStats = getPriceHistoryStats(embeddedHistory);
  const mappedStats = getPriceHistoryStats(mappedHistory);

  if (embeddedStats.pointCount === 0 && mappedStats.pointCount === 0) {
    return {
      history: [],
      source: "embedded_card_history",
      embeddedStats,
      mappedStats,
      selectedStats: embeddedStats,
    };
  }

  let selectedSource = "embedded_card_history";
  if (embeddedStats.pointCount === 0) {
    selectedSource = "top_chase_card_histories";
  } else if (mappedStats.pointCount === 0) {
    selectedSource = "embedded_card_history";
  } else if (embeddedStats.pointCount < 30 && mappedStats.pointCount >= 30) {
    selectedSource = "top_chase_card_histories";
  } else if (mappedStats.pointCount < 30 && embeddedStats.pointCount >= 30) {
    selectedSource = "embedded_card_history";
  } else if (
    mappedStats.endDate &&
    mappedStats.endDate === embeddedStats.endDate &&
    mappedStats.startDate &&
    (!embeddedStats.startDate || mappedStats.startDate < embeddedStats.startDate)
  ) {
    selectedSource = "top_chase_card_histories";
  } else if (
    embeddedStats.endDate &&
    embeddedStats.endDate === mappedStats.endDate &&
    embeddedStats.startDate &&
    (!mappedStats.startDate || embeddedStats.startDate < mappedStats.startDate)
  ) {
    selectedSource = "embedded_card_history";
  } else if (mappedStats.pointCount > embeddedStats.pointCount) {
    selectedSource = "top_chase_card_histories";
  } else if (
    mappedStats.endDate &&
    embeddedStats.endDate &&
    mappedStats.endDate > embeddedStats.endDate
  ) {
    selectedSource = "top_chase_card_histories";
  }

  const history = selectedSource === "top_chase_card_histories" ? mappedHistory : embeddedHistory;
  const selectedStats = selectedSource === "top_chase_card_histories" ? mappedStats : embeddedStats;
  return {
    history,
    source: selectedSource,
    embeddedStats,
    mappedStats,
    selectedStats,
  };
}

function normalizeTopChaseCardHistories(payload) {
  const source =
    payload?.topChaseCardHistories && typeof payload.topChaseCardHistories === "object"
      ? payload.topChaseCardHistories
      : payload?.top_chase_card_histories && typeof payload.top_chase_card_histories === "object"
      ? payload.top_chase_card_histories
      : {};

  if (Array.isArray(source)) {
    return Object.fromEntries(
      source
        .map((entry, index) => {
          const key =
            toOptionalString(entry?.cardVariantId ?? entry?.card_variant_id) ||
            toOptionalString(entry?.cardId ?? entry?.card_id) ||
            toOptionalString(entry?.rank ? `rank:${entry.rank}` : null) ||
            `rank:${index + 1}`;
          const history = Array.isArray(entry?.history)
            ? entry.history
            : Array.isArray(entry?.priceHistory)
            ? entry.priceHistory
            : Array.isArray(entry?.price_history)
            ? entry.price_history
            : [];
          return key ? [key, normalizeDailyPriceHistory(history)] : null;
        })
        .filter(Boolean)
    );
  }

  return Object.fromEntries(
    Object.entries(source).map(([key, history]) => [
      key,
      normalizeDailyPriceHistory(Array.isArray(history) ? history : []),
    ])
  );
}

function getTopChaseHistoryForCard(card, histories, index) {
  const keys = [
    toOptionalString(card?.cardVariantId ?? card?.card_variant_id),
    toOptionalString(card?.cardId ?? card?.card_id),
    toOptionalString(card?.id),
    toOptionalString(card?.rank),
    toOptionalString(card?.marketRank ?? card?.market_rank),
    `rank:${index + 1}`,
    String(index + 1),
  ].filter(Boolean);

  for (const key of keys) {
    if (Array.isArray(histories?.[key]) && histories[key].length > 0) {
      return histories[key];
    }
  }
  return [];
}

function normalizeDailySetValueHistory(history) {
  const dailyPoints = new Map();

  (Array.isArray(history) ? history : []).forEach((point) => {
    const date = normalizeDateKey(point?.date);
    const setValue = toOptionalNumber(point?.setValue ?? point?.set_value ?? point?.value);
    if (!date) {
      return;
    }
    dailyPoints.set(date, {
      date,
      valueScope: toOptionalString(point?.valueScope ?? point?.value_scope),
      value_scope: toOptionalString(point?.value_scope ?? point?.valueScope),
      setValue,
      cardCountPriced: toOptionalNumber(point?.cardCountPriced ?? point?.card_count_priced),
      source: toOptionalString(point?.source ?? point?.provider),
      provider: toOptionalString(point?.provider ?? point?.source),
      calculationRunId: toOptionalString(point?.calculationRunId ?? point?.calculation_run_id),
      calculation_run_id: toOptionalString(point?.calculation_run_id ?? point?.calculationRunId),
      isCarriedForward: Boolean(point?.isCarriedForward ?? point?.is_carried_forward),
      is_carried_forward: Boolean(point?.is_carried_forward ?? point?.isCarriedForward),
      sourceDate: toOptionalString(point?.sourceDate ?? point?.source_date),
      source_date: toOptionalString(point?.source_date ?? point?.sourceDate),
    });
  });

  return Array.from(dailyPoints.values()).sort((a, b) => a.date.localeCompare(b.date));
}

function normalizeStoredMarketDeltaWindows(source) {
  if (!source || typeof source !== "object") return null;
  const entries = Object.entries(source)
    .filter(([key, movement]) => ["1D", "7D", "30D"].includes(String(key).toUpperCase()) && movement && typeof movement === "object")
    .map(([key, movement]) => {
      const normalizedKey = String(key).toUpperCase();
      return [normalizedKey, {
        ...movement,
        window: toOptionalString(movement?.window) || normalizedKey,
        windowDays: toOptionalNumber(movement?.windowDays ?? movement?.window_days),
        windowConvention: toOptionalString(movement?.windowConvention ?? movement?.window_convention),
        targetStartDate: toOptionalString(movement?.targetStartDate ?? movement?.target_start_date),
        startDate: toOptionalString(movement?.startDate ?? movement?.start_date),
        endDate: toOptionalString(movement?.endDate ?? movement?.end_date),
        startingPrice: toOptionalNumber(movement?.startingPrice ?? movement?.starting_price),
        currentPrice: toOptionalNumber(movement?.currentPrice ?? movement?.current_price),
        changeAmount: toOptionalNumber(movement?.changeAmount ?? movement?.change_amount),
        changePercent: toOptionalNumber(movement?.changePercent ?? movement?.change_percent),
        cardVariantId: toOptionalString(movement?.cardVariantId ?? movement?.card_variant_id),
        conditionId: toOptionalString(movement?.conditionId ?? movement?.condition_id),
        fullWindowCoverage: Boolean(movement?.fullWindowCoverage ?? movement?.full_window_coverage),
        isPartialWindow: Boolean(movement?.isPartialWindow ?? movement?.is_partial_window),
      }];
    });
  return entries.length > 0 ? Object.fromEntries(entries) : null;
}

function normalizeTopMarketCardsPayload(payload) {
  const cards = Array.isArray(payload?.cards) ? payload.cards : [];
  const topChaseCardHistories = normalizeTopChaseCardHistories(payload);
  const snapshotMeta = payload?.meta?.snapshot && typeof payload.meta.snapshot === "object"
    ? payload.meta.snapshot
    : {};
  const movementGeneration = payload?.meta?.movementGeneration && typeof payload.meta.movementGeneration === "object"
    ? payload.meta.movementGeneration
    : {};
  const isLegacyMovementSnapshot = snapshotMeta?.isLegacyMovementSnapshot === true;
  const allowsLegacyHistoryFallback = snapshotMeta?.allowsLegacyHistoryFallback === true;
  const dashboardLatestMarketDate = toOptionalString(
    payload?.latestMarketDate ?? payload?.latest_market_date ?? snapshotMeta?.latestMarketDate
  );

  if (process.env.NODE_ENV !== "production" && movementGeneration?.matches === false) {
    console.warn("[pokemon-market-delta] Cards and Market Dashboard snapshot generations differ", {
      cardsGenerationId: movementGeneration?.cardsGenerationId ?? null,
      marketDashboardGenerationId: movementGeneration?.marketDashboardGenerationId ?? null,
      status: movementGeneration?.status ?? null,
    });
  }

  return {
    set: {
      id: toOptionalString(payload?.set?.id),
      name: toOptionalString(payload?.set?.name),
      slug: toOptionalString(payload?.set?.slug),
    },
    cards: cards.map((card, index) => {
      const explicitHistory =
        Array.isArray(card?.priceHistory) ? card.priceHistory : Array.isArray(card?.price_history) ? card.price_history : [];
      const embeddedHistory = normalizeDailyPriceHistory(explicitHistory);
      const mappedHistory = getTopChaseHistoryForCard(card, topChaseCardHistories, index);
      const selectedHistory = chooseTopChaseHistory(embeddedHistory, mappedHistory);
      const priceHistory = selectedHistory.history;
      const marketDeltaWindows = normalizeStoredMarketDeltaWindows(
        card?.marketDeltaWindows ?? card?.market_delta_windows
      );

      return {
        id: toOptionalString(card?.cardId ?? card?.card_id ?? card?.id),
        cardId: toOptionalString(card?.cardId ?? card?.card_id ?? card?.id),
        cardVariantId: toOptionalString(card?.cardVariantId ?? card?.card_variant_id),
        canonicalCardId: toOptionalString(card?.canonicalCardId ?? card?.canonical_card_id ?? card?.cardId ?? card?.card_id ?? card?.id),
        conditionId: toOptionalString(card?.conditionId ?? card?.condition_id ?? card?.conditionIdUsed ?? card?.condition_id_used),
        setId: toOptionalString(card?.setId ?? card?.set_id),
        name: toOptionalString(card?.name),
        imageUrl: toOptionalString(card?.imageUrl ?? card?.image_url),
        imageSmallUrl: toOptionalString(card?.imageSmallUrl ?? card?.image_small_url),
        imageLargeUrl: toOptionalString(card?.imageLargeUrl ?? card?.image_large_url),
        rarity: toOptionalString(card?.rarity),
        setNumber: toOptionalString(card?.setNumber ?? card?.set_number),
        cardNumber: toOptionalString(card?.setNumber ?? card?.set_number),
        estimatedMarketPrice: toOptionalNumber(card?.estimatedMarketPrice ?? card?.estimated_market_price),
        // The stored top_chase_cards_json price is the snapshot builder's own
        // marketPrice/currentPrice (see the comment above _pick_fresher_top_chase_row
        // in pokemon_public_snapshot_service.py). Reading only marketPrice/
        // estimatedMarketPrice rendered a priced card as a blank price cell
        // whenever the stored row carried currentPrice or a snake_case key.
        marketPrice: toOptionalNumber(
          card?.marketPrice ??
            card?.market_price ??
            card?.currentPrice ??
            card?.current_price ??
            card?.estimatedMarketPrice ??
            card?.estimated_market_price
        ),
        marketDate: toOptionalString(card?.marketDate ?? card?.market_date),
        dashboardLatestMarketDate,
        windowConvention: toOptionalString(card?.windowConvention ?? card?.window_convention),
        marketDeltaWindows,
        market_delta_windows: marketDeltaWindows,
        movementSnapshotLegacy: isLegacyMovementSnapshot,
        allowLegacyMovementHistoryFallback: allowsLegacyHistoryFallback,
        movementGeneration,
        priceUpdatedAt: toOptionalString(card?.priceUpdatedAt ?? card?.price_updated_at),
        source: toOptionalString(card?.source ?? card?.provider),
        provider: toOptionalString(card?.provider ?? card?.source),
        rank: toOptionalNumber(card?.rank ?? card?.marketRank ?? card?.market_rank) ?? index + 1,
        deltas: card?.deltas && typeof card.deltas === "object" ? card.deltas : null,
        priceHistory,
        price_history: priceHistory,
        embeddedHistoryPointCount: selectedHistory.embeddedStats.pointCount,
        mappedHistoryPointCount: selectedHistory.mappedStats.pointCount,
        selectedHistoryPointCount: selectedHistory.selectedStats.pointCount,
        selectedHistorySource: selectedHistory.source,
        selectedHistoryStartDate: selectedHistory.selectedStats.startDate,
        selectedHistoryEndDate: selectedHistory.selectedStats.endDate,
        historyPointCount: toOptionalNumber(card?.historyPointCount ?? card?.history_point_count),
        historyStartDate: toOptionalString(card?.historyStartDate ?? card?.history_start_date),
        historyEndDate: toOptionalString(card?.historyEndDate ?? card?.history_end_date),
        conditionIdUsed: toOptionalString(card?.conditionIdUsed ?? card?.condition_id_used),
        matchingConditionObservationCount: toOptionalNumber(
          card?.matchingConditionObservationCount ?? card?.matching_condition_observation_count
        ),
        historyDiagnostics:
          card?.historyDiagnostics && typeof card.historyDiagnostics === "object"
            ? card.historyDiagnostics
            : card?.history_diagnostics && typeof card.history_diagnostics === "object"
            ? card.history_diagnostics
            : null,
      };
    }),
    topChaseCardHistories,
    top_chase_card_histories: topChaseCardHistories,
    meta: payload?.meta || { sources: {}, warnings: [] },
  };
}

function normalizeMarketMoverCard(card, window = "30D") {
  const currentPrice = toOptionalNumber(card?.currentPrice ?? card?.current_price ?? card?.marketPrice ?? card?.market_price);
  const change30dAmount = toOptionalNumber(card?.change30dAmount ?? card?.change_30d_amount);
  const change30dPercent = toOptionalNumber(card?.change30dPercent ?? card?.change_30d_percent);
  const changeAmount = toOptionalNumber(card?.changeAmount ?? card?.change_amount ?? change30dAmount);
  const changePercent = toOptionalNumber(card?.changePercent ?? card?.change_percent ?? change30dPercent);
  const movementScore = toOptionalNumber(card?.movementScore ?? card?.movement_score);
  const movementLabel = toOptionalString(card?.movementLabel ?? card?.movement_label);
  const normalizedWindow = String(window || card?.window || "30D").toUpperCase();
  const reliable = card?.reliable ?? card?.movementReliable ?? card?.movement_reliable;
  const reliability = toOptionalString(card?.reliability);

  return {
    id: toOptionalString(card?.cardId ?? card?.card_id ?? card?.id),
    cardId: toOptionalString(card?.cardId ?? card?.card_id ?? card?.id),
    canonicalCardId: toOptionalString(card?.canonicalCardId ?? card?.canonical_card_id ?? card?.cardId ?? card?.card_id ?? card?.id),
    cardVariantId: toOptionalString(card?.cardVariantId ?? card?.card_variant_id),
    conditionId: toOptionalString(card?.conditionId ?? card?.condition_id ?? card?.conditionIdUsed ?? card?.condition_id_used),
    setId: toOptionalString(card?.setId ?? card?.set_id),
    name: toOptionalString(card?.name),
    imageUrl: toOptionalString(card?.imageUrl ?? card?.image_url),
    imageSmallUrl: toOptionalString(card?.imageSmallUrl ?? card?.image_small_url),
    imageLargeUrl: toOptionalString(card?.imageLargeUrl ?? card?.image_large_url),
    rarity: toOptionalString(card?.rarity),
    setNumber: toOptionalString(card?.setNumber ?? card?.set_number ?? card?.cardNumber ?? card?.card_number),
    cardNumber: toOptionalString(card?.cardNumber ?? card?.card_number ?? card?.setNumber ?? card?.set_number),
    currentPrice,
    marketPrice: currentPrice,
    changeAmount,
    changePercent,
    ...(normalizedWindow === "1D" ? { change1dAmount: changeAmount, change1dPercent: changePercent } : {}),
    ...(normalizedWindow === "7D" ? {
      change7dAmount: changeAmount,
      change7dPercent: changePercent,
      movement7d: {
        changeAmount,
        changePercent,
        reliable: reliable === undefined ? null : Boolean(reliable),
        reliability,
        fullWindowCoverage: Boolean(card?.fullWindowCoverage ?? card?.full_window_coverage),
        isPartialWindow: Boolean(card?.isPartialWindow ?? card?.is_partial_window),
      },
    } : {}),
    ...(normalizedWindow === "30D" ? { change30dAmount: changeAmount, change30dPercent: changePercent } : {}),
    window: normalizedWindow,
    windowDays: toOptionalNumber(card?.windowDays ?? card?.window_days),
    windowConvention: toOptionalString(card?.windowConvention ?? card?.window_convention),
    targetStartDate: toOptionalString(card?.targetStartDate ?? card?.target_start_date),
    startDate: toOptionalString(card?.startDate ?? card?.start_date ?? card?.historyStartDate ?? card?.history_start_date),
    endDate: toOptionalString(card?.endDate ?? card?.end_date ?? card?.historyEndDate ?? card?.history_end_date),
    fullWindowCoverage: Boolean(card?.fullWindowCoverage ?? card?.full_window_coverage),
    isPartialWindow: Boolean(card?.isPartialWindow ?? card?.is_partial_window),
    movementScore,
    movementLabel,
    moverEligible: card?.moverEligible ?? card?.mover_eligible,
    reliable: reliable === undefined ? null : Boolean(reliable),
    reliability,
    enoughHistory: Boolean(card?.enoughHistory ?? card?.enough_history),
    confidence: toOptionalString(card?.confidence),
    historyPointCount: toOptionalNumber(card?.historyPointCount ?? card?.history_point_count),
    historyStartDate: toOptionalString(card?.historyStartDate ?? card?.history_start_date),
    historyEndDate: toOptionalString(card?.historyEndDate ?? card?.history_end_date),
  };
}

function normalizeMarketMoversEntry(source, payload) {
  const heating = Array.isArray(source?.heatingUp)
    ? source.heatingUp
    : Array.isArray(source?.heating_up)
    ? source.heating_up
    : [];
  const cooling = Array.isArray(source?.coolingOff)
    ? source.coolingOff
    : Array.isArray(source?.cooling_off)
    ? source.cooling_off
    : [];
  const all = Array.isArray(source?.all) ? source.all : [...heating, ...cooling];

  const window = toOptionalString(source?.window ?? payload?.window ?? payload?.window_key) || "30D";
  return {
    window,
    windowDays: toOptionalNumber(source?.windowDays ?? source?.window_days ?? payload?.windowDays ?? payload?.window_days) ?? 30,
    heatingUp: heating.map((card) => normalizeMarketMoverCard(card, window)).filter((card) => card.name),
    coolingOff: cooling.map((card) => normalizeMarketMoverCard(card, window)).filter((card) => card.name),
    all: all.map((card) => normalizeMarketMoverCard(card, window)).filter((card) => card.name),
  };
}

export function normalizeMarketMoversPayload(payload) {
  const source =
    payload?.marketMovers && typeof payload.marketMovers === "object"
      ? payload.marketMovers
      : payload?.market_movers && typeof payload.market_movers === "object"
      ? payload.market_movers
      : {};
  const entry = normalizeMarketMoversEntry(source, payload);
  const meta = payload?.meta && typeof payload.meta === "object" ? payload.meta : { warnings: [] };
  if (
    process.env.NODE_ENV !== "production" &&
    meta?.snapshot?.usedLegacyMoverList === true
  ) {
    console.warn("[pokemon-market-delta] Market movers response used a legacy mover list (not the canonical Cards filter)", {
      setId: toOptionalString(payload?.set?.id),
      source: toOptionalString(meta?.snapshot?.source),
      window: entry.window,
    });
  }
  return {
    ...entry,
    set: {
      id: toOptionalString(payload?.set?.id),
      name: toOptionalString(payload?.set?.name),
      slug: toOptionalString(payload?.set?.slug),
    },
    latestMarketDate: toOptionalString(payload?.latestMarketDate ?? payload?.latest_market_date),
    // meta carries the canonical query/totals/snapshot metadata
    // (marketAsOfDate, generationId, movementTotals, usedLegacyMoverList)
    // used by the shared market-date resolution and dev diagnostics.
    meta,
  };
}

function normalizeMarketMoversByWindowPayload(payload) {
  const source =
    payload?.marketMoversByWindow && typeof payload.marketMoversByWindow === "object"
      ? payload.marketMoversByWindow
      : payload?.market_movers_by_window && typeof payload.market_movers_by_window === "object"
      ? payload.market_movers_by_window
      : null;
  if (!source) {
    return null;
  }
  return Object.fromEntries(
    Object.entries(source)
      .filter(([, entry]) => entry && typeof entry === "object")
      .map(([windowKey, entry]) => [windowKey, normalizeMarketMoversEntry(entry, payload)])
  );
}

function normalizeSimulationPerformanceHistory(history) {
  const dailyPoints = new Map();

  (Array.isArray(history) ? history : []).forEach((point) => {
    const date = normalizeDateKey(
      point?.snapshot_date ?? point?.snapshotDate ?? point?.date
    );
    if (!date) {
      return;
    }
    const existing = dailyPoints.get(date);
    const isCarriedForward = Boolean(point?.isCarriedForward ?? point?.is_carried_forward);
    if (existing && !existing.isCarriedForward && isCarriedForward) {
      return;
    }
    dailyPoints.set(date, {
      date,
      snapshot_date: date,
      snapshotDate: date,
      sourceDate: toOptionalString(point?.sourceDate ?? point?.source_date) ?? date,
      source_date: toOptionalString(point?.source_date ?? point?.sourceDate) ?? date,
      calculationRunId: toOptionalString(point?.calculationRunId ?? point?.calculation_run_id),
      calculation_run_id: toOptionalString(point?.calculation_run_id ?? point?.calculationRunId),
      runCreatedAt: toOptionalString(point?.runCreatedAt ?? point?.run_created_at),
      run_created_at: toOptionalString(point?.run_created_at ?? point?.runCreatedAt),
      packCost: toOptionalNumber(point?.packCost ?? point?.pack_cost),
      pack_cost: toOptionalNumber(point?.pack_cost ?? point?.packCost),
      meanValue: toOptionalNumber(point?.meanValue ?? point?.mean_value),
      mean_value: toOptionalNumber(point?.mean_value ?? point?.meanValue),
      medianValue: toOptionalNumber(point?.medianValue ?? point?.median_value),
      median_value: toOptionalNumber(point?.median_value ?? point?.medianValue),
      meanValueToCostRatio: toOptionalNumber(point?.meanValueToCostRatio ?? point?.mean_value_to_cost_ratio),
      mean_value_to_cost_ratio: toOptionalNumber(point?.mean_value_to_cost_ratio ?? point?.meanValueToCostRatio),
      simulatedMeanPackValueVsPackCost: toOptionalNumber(
        point?.simulatedMeanPackValueVsPackCost ?? point?.simulated_mean_pack_value_vs_pack_cost
      ),
      simulated_mean_pack_value_vs_pack_cost: toOptionalNumber(
        point?.simulated_mean_pack_value_vs_pack_cost ?? point?.simulatedMeanPackValueVsPackCost
      ),
      medianValueToCostRatio: toOptionalNumber(point?.medianValueToCostRatio ?? point?.median_value_to_cost_ratio),
      median_value_to_cost_ratio: toOptionalNumber(point?.median_value_to_cost_ratio ?? point?.medianValueToCostRatio),
      simulatedMedianPackValueVsPackCost: toOptionalNumber(
        point?.simulatedMedianPackValueVsPackCost ?? point?.simulated_median_pack_value_vs_pack_cost
      ),
      simulated_median_pack_value_vs_pack_cost: toOptionalNumber(
        point?.simulated_median_pack_value_vs_pack_cost ?? point?.simulatedMedianPackValueVsPackCost
      ),
      p95ValueToCostRatio: toOptionalNumber(point?.p95ValueToCostRatio ?? point?.p95_value_to_cost_ratio),
      p95_value_to_cost_ratio: toOptionalNumber(point?.p95_value_to_cost_ratio ?? point?.p95ValueToCostRatio),
      source: toOptionalString(point?.source ?? point?.provider),
      provider: toOptionalString(point?.provider ?? point?.source),
      isCarriedForward,
      is_carried_forward: isCarriedForward,
    });
  });

  return Array.from(dailyPoints.values()).sort((a, b) => a.date.localeCompare(b.date));
}

function normalizeSetValueHistoryPayload(payload) {
  const history = Array.isArray(payload?.history) ? payload.history : [];
  const availableScopes = Array.isArray(payload?.meta?.availableScopes)
    ? payload.meta.availableScopes
    : Array.isArray(payload?.meta?.available_scopes)
    ? payload.meta.available_scopes
    : [];

  return {
    set: {
      id: toOptionalString(payload?.set?.id),
      name: toOptionalString(payload?.set?.name),
      slug: toOptionalString(payload?.set?.slug),
    },
    history: normalizeDailySetValueHistory(history),
    meta: {
      ...(payload?.meta || { sources: {}, warnings: [] }),
      valueScope: toOptionalString(payload?.meta?.valueScope ?? payload?.meta?.value_scope),
      value_scope: toOptionalString(payload?.meta?.value_scope ?? payload?.meta?.valueScope),
      availableScopes: availableScopes.map((scope) => ({
        key: toOptionalString(scope?.key),
        label: toOptionalString(scope?.label),
        latestDate: toOptionalString(scope?.latestDate ?? scope?.latest_date),
      })).filter((scope) => scope.key),
    },
  };
}

export function normalizePreparedMarketIndex(value) {
  if (!value || typeof value !== "object") return null;
  return {
    ...value,
    currentValue: value.currentValue ?? value.current_value ?? null,
    baseValue: value.baseValue ?? value.base_value ?? null,
    trackingSince: value.trackingSince ?? value.tracking_since ?? null,
    history: Array.isArray(value.history) ? value.history.map((point) => ({
      ...point,
      indexValue: point?.indexValue ?? point?.index_value ?? null,
      chainSegmentId: point?.chainSegmentId ?? point?.chain_segment_id ?? null,
      isNewSegment: point?.isNewSegment ?? point?.is_new_segment ?? false,
      segmentStartDate: point?.segmentStartDate ?? point?.segment_start_date ?? null,
    })) : [],
    movements: value.movements && typeof value.movements === "object" ? value.movements : {},
  };
}

export function normalizePreparedCardsMarket(value) {
  if (!value || typeof value !== "object") return null;
  return {
    ...value,
    available: value.available !== false,
    marketIndex: normalizePreparedMarketIndex(value.marketIndex || value.market_index),
    marketBreadth: value.marketBreadth || value.market_breadth || {},
  };
}

export function normalizeMarketDashboardPayload(payload) {
  const historiesByScope =
    payload?.setValueHistoriesByScope && typeof payload.setValueHistoriesByScope === "object"
      ? payload.setValueHistoriesByScope
      : payload?.set_value_histories_by_scope && typeof payload.set_value_histories_by_scope === "object"
      ? payload.set_value_histories_by_scope
      : {};
  const availableScopes = Array.isArray(payload?.availableScopes)
    ? payload.availableScopes
    : Array.isArray(payload?.available_scopes)
    ? payload.available_scopes
    : Array.isArray(payload?.meta?.availableScopes)
    ? payload.meta.availableScopes
    : [];
  const topCardsPayload = normalizeTopMarketCardsPayload({
    set: payload?.set,
    cards: payload?.topChaseCards || payload?.top_chase_cards || [],
    topChaseCardHistories: payload?.topChaseCardHistories,
    top_chase_card_histories: payload?.top_chase_card_histories,
    meta: payload?.meta,
  });
  const marketMovers = normalizeMarketMoversPayload(payload);
  const marketMoversByWindow = normalizeMarketMoversByWindowPayload(payload);
  const cardsMarket = normalizePreparedCardsMarket(payload?.cardsMarket || payload?.cards_market);

  const normalizedHistoriesByScope = Object.fromEntries(
    Object.entries(historiesByScope).map(([scope, history]) => [
      scope,
      normalizeDailySetValueHistory(Array.isArray(history) ? history : []),
    ])
  );

  return {
    set: {
      id: toOptionalString(payload?.set?.id),
      name: toOptionalString(payload?.set?.name),
      slug: toOptionalString(payload?.set?.slug),
    },
    window: toOptionalString(payload?.window ?? payload?.window_key ?? payload?.meta?.window ?? payload?.meta?.window_key),
    topChaseCards: topCardsPayload.cards,
    top_chase_cards: topCardsPayload.cards,
    topChaseCardHistories: topCardsPayload.topChaseCardHistories,
    top_chase_card_histories: topCardsPayload.top_chase_card_histories,
    marketMovers,
    market_movers: marketMovers,
    marketMoversByWindow,
    market_movers_by_window: marketMoversByWindow,
    cardsMarket,
    cards_market: cardsMarket,
    setValueHistoriesByScope: normalizedHistoriesByScope,
    set_value_histories_by_scope: normalizedHistoriesByScope,
    performanceVsCostHistory: normalizeSimulationPerformanceHistory(
      payload?.performanceVsCostHistory || payload?.performance_vs_cost_history || []
    ),
    performance_vs_cost_history: normalizeSimulationPerformanceHistory(
      payload?.performanceVsCostHistory || payload?.performance_vs_cost_history || []
    ),
    availableScopes: availableScopes
      .map((scope) => ({
        key: toOptionalString(scope?.key),
        label: toOptionalString(scope?.label),
        latestDate: toOptionalString(scope?.latestDate ?? scope?.latest_date),
      }))
      .filter((scope) => scope.key),
    latestMarketDate: toOptionalString(payload?.latestMarketDate ?? payload?.latest_market_date),
    meta: payload?.meta || { sources: {}, warnings: [] },
  };
}

async function readJsonResponse(response, fallbackMessage) {
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const message = payload?.message || payload?.error || fallbackMessage;
    const requestError = new Error(message);
    requestError.status = response.status;
    // Carry the structured body through so callers can branch on the declared
    // contract (code / retryable) instead of re-deriving it from the status.
    if (payload?.code) {
      requestError.code = payload.code;
    }
    if (typeof payload?.retryable === "boolean") {
      requestError.retryable = payload.retryable;
    }
    throw requestError;
  }

  return payload;
}

export async function getPokemonSetMarketDashboard(setId, { window = DEFAULT_MARKET_DASHBOARD_WINDOW, days = null } = {}) {
  const resolvedSetId = String(setId || "").trim();
  if (!resolvedSetId) {
    throw new Error("Set id is required");
  }

  const normalizedWindow = normalizeMarketDashboardWindow(window);
  const cacheOptions = { window: normalizedWindow, days };
  const cacheKey = getMarketDashboardCacheKey(resolvedSetId, cacheOptions);
  const cached = readMarketDashboardCache(cacheKey);
  if (cached) {
    debugTiming("market_dashboard.cache_hit", { setId: resolvedSetId, window: normalizedWindow, days });
    return cached;
  }
  if (marketDashboardInflight.has(cacheKey)) {
    debugTiming("market_dashboard.inflight_join", { setId: resolvedSetId, window: normalizedWindow, days });
    return marketDashboardInflight.get(cacheKey);
  }

  const params = new URLSearchParams();
  if (normalizedWindow) {
    params.set("window", normalizedWindow);
  }
  if (days) {
    params.set("days", String(days));
  }

  const startedAt = performance.now();
  debugTiming("market_dashboard.fetch_start", { setId: resolvedSetId, window: normalizedWindow, days });

  const request = (async () => {
    const url = `/api/tcgs/pokemon/sets/${encodeURIComponent(resolvedSetId)}/market/dashboard${
      params.toString() ? `?${params}` : ""
    }`;
    const staleCached = readMarketDashboardCache(cacheKey, { allowStale: true });
    let normalized = null;
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        const response = await fetch(url, {
          method: "GET",
        });
        normalized = normalizeMarketDashboardPayload(
          await readJsonResponse(response, "Unable to load market dashboard")
        );
        break;
      } catch (error) {
        if (attempt > 0 || !isRetryableSnapshotError(error)) {
          if (staleCached) {
            debugTiming("market_dashboard.fetch_stale_cache_fallback", {
              setId: resolvedSetId,
              window: normalizedWindow,
              days,
              status: error?.status,
              error: error?.message || String(error),
            });
            return staleCached;
          }
          throw error;
        }
        debugTiming("market_dashboard.fetch_retry", {
          setId: resolvedSetId,
          window: normalizedWindow,
          days,
          status: error?.status,
          error: error?.message || String(error),
        });
        await wait(175);
      }
    }
    writeMarketDashboardCache(cacheKey, normalized);
    debugTiming("market_dashboard.fetch_success", {
      setId: resolvedSetId,
      window: normalizedWindow,
      days,
      elapsedMs: Math.round(performance.now() - startedAt),
      topCards: normalized.topChaseCards.length,
      scopes: Object.keys(normalized.setValueHistoriesByScope || {}).length,
    });
    return normalized;
  })().finally(() => {
    marketDashboardInflight.delete(cacheKey);
  });

  marketDashboardInflight.set(cacheKey, request);
  return request;
}

export function getCachedPokemonSetMarketDashboard(setId, options = {}) {
  const resolvedSetId = String(setId || "").trim();
  return resolvedSetId ? readMarketDashboardCache(getMarketDashboardCacheKey(resolvedSetId, options)) : null;
}

export function prefetchPokemonSetMarketDashboard(setId, options = {}) {
  const resolvedSetId = String(setId || "").trim();
  if (!resolvedSetId) {
    return Promise.resolve(null);
  }
  return getPokemonSetMarketDashboard(resolvedSetId, options).catch((error) => {
    debugTiming("market_dashboard.prefetch_error", {
      setId: resolvedSetId,
      window: normalizeMarketDashboardWindow(options.window || DEFAULT_MARKET_DASHBOARD_WINDOW),
      error: error?.message || String(error),
    });
    return null;
  });
}

export async function getPokemonSetTopMarketCards(setId, { limit = 10, days = 365 } = {}) {
  const resolvedSetId = String(setId || "").trim();
  if (!resolvedSetId) {
    throw new Error("Set id is required");
  }

  const params = new URLSearchParams();
  if (limit) {
    params.set("limit", String(limit));
  }
  if (days) {
    params.set("days", String(days));
  }

  const response = await fetch(
    `/api/tcgs/pokemon/sets/${encodeURIComponent(resolvedSetId)}/market/top-cards${params.toString() ? `?${params}` : ""}`,
    {
      method: "GET",
    }
  );

  return normalizeTopMarketCardsPayload(
    await readJsonResponse(response, "Unable to load top market cards")
  );
}

export function normalizeTopChasePayload(payload) {
  return normalizeTopMarketCardsPayload({
    set: payload?.set,
    cards: payload?.topChaseCards || payload?.top_chase_cards || [],
    topChaseCardHistories: payload?.topChaseCardHistories,
    top_chase_card_histories: payload?.top_chase_card_histories,
    latestMarketDate: payload?.latestMarketDate ?? payload?.latest_market_date,
    meta: payload?.meta,
  });
}

// --- Top Chase last-known-good cache ----------------------------------------
//
// Keyed by set + window + limit so a stale payload can only ever be reused for
// the exact request that produced it. Nothing is written here unless the
// dedicated payload validated as COMPLETE, which is what stops a degraded or
// previous-generation response from being resurrected later and presented as if
// it were current.
const topChaseLastKnownGood = new Map();

function getTopChaseIdentityKey(setId, window, limit) {
  return `top-chase:${setId}:${window || ""}:${limit || ""}`;
}

export function __resetTopChaseLastKnownGoodForTests() {
  topChaseLastKnownGood.clear();
}

export function getCachedPokemonSetTopChase(setId, { window = "365d", limit = 10 } = {}) {
  const resolvedSetId = String(setId || "").trim();
  if (!resolvedSetId) {
    return null;
  }
  return topChaseLastKnownGood.get(getTopChaseIdentityKey(resolvedSetId, window, limit)) || null;
}

// Exactly one automatic retry (two attempts total). A bounded, single retry
// covers the transient cases — a cold backend read, a 5xx, an aborted socket —
// without turning a genuinely broken section into a polling loop.
const TOP_CHASE_RETRY_STATUSES = new Set([500, 502, 503, 504]);
const TOP_CHASE_RETRY_DELAY_MS = 400;

function isRetryableTopChaseError(error) {
  if (!error) {
    return false;
  }
  if (error.retryable === true || error.isTimeout === true) {
    return true;
  }
  if (error.name === "AbortError") {
    return true;
  }
  return TOP_CHASE_RETRY_STATUSES.has(Number(error.status));
}

function buildTopChaseContractError(verdict) {
  const error = new Error("Top chase cards response was incomplete.");
  error.code = "POKEMON_SET_TOP_CHASE_SNAPSHOT_INCOMPLETE";
  error.status = 503;
  error.retryable = true;
  error.topChaseVerdict = verdict;
  return error;
}

async function fetchTopChaseOnce(resolvedSetId, params, signal) {
  const response = await fetch(
    `/api/tcgs/pokemon/sets/${encodeURIComponent(resolvedSetId)}/market/top-chase${params.toString() ? `?${params}` : ""}`,
    { method: "GET", signal, cache: "no-store" }
  );

  const payload = await readJsonResponse(response, "Unable to load top chase cards");
  return normalizeTopChasePayload(payload);
}

/**
 * One bounded Top Chase attempt with its OWN AbortController and timeout.
 *
 * Each attempt must own its abort lifecycle. Previously all attempts shared the
 * single controller created by `joinSlimModuleRequest`, so when the outer
 * timeout fired it aborted that controller and attempt two started with an
 * already-aborted signal — the retry could never succeed, it just re-reported
 * the same AbortError. A fresh controller per attempt makes the retry real.
 *
 * The timeout handle is always released in `finally`, so a fast attempt never
 * leaves a pending timer behind.
 */
async function runTopChaseAttempt(resolvedSetId, params, { attempt } = {}) {
  const controller = typeof AbortController === "function" ? new AbortController() : null;
  let timeoutHandle = null;

  try {
    return await new Promise((resolve, reject) => {
      timeoutHandle = setTimeout(() => {
        try {
          controller?.abort();
        } catch {
          // An environment without abort support still gets a settled Promise.
        }
        debugTiming("top_chase.attempt_timeout", {
          setId: resolvedSetId,
          attempt,
          timeoutMs: SLIM_MODULE_REQUEST_TIMEOUT_MS,
        });
        reject(createSlimModuleTimeoutError());
      }, SLIM_MODULE_REQUEST_TIMEOUT_MS);

      Promise.resolve()
        .then(() => fetchTopChaseOnce(resolvedSetId, params, controller?.signal))
        .then(resolve, reject);
    });
  } finally {
    if (timeoutHandle) {
      clearTimeout(timeoutHandle);
    }
  }
}

export async function getPokemonSetTopChase(setId, { window = "365d", limit = 10 } = {}) {
  const resolvedSetId = String(setId || "").trim();
  if (!resolvedSetId) {
    throw new Error("Set id is required");
  }

  const params = new URLSearchParams();
  params.set("snapshot_contract", PRICING_SNAPSHOT_CONTRACT_VERSION);
  if (window) {
    params.set("window", String(window));
  }
  if (limit) {
    params.set("limit", String(limit));
  }

  const identityKey = getTopChaseIdentityKey(resolvedSetId, window, limit);

  // The in-flight key is released in .finally() below, so it is cleared after
  // final success, error, timeout AND contract-validation failure alike.
  //
  // `manageSignal: false`: this operation makes up to two attempts, and each one
  // owns its own controller/timeout via runTopChaseAttempt. A single shared
  // controller would abort attempt two before it started.
  return joinSlimModuleRequest(
    identityKey,
    async () => {
      let lastError = null;

      for (let attempt = 1; attempt <= 2; attempt += 1) {
        try {
          const normalized = await runTopChaseAttempt(resolvedSetId, params, { attempt });
          const verdict = validateTopChasePayload(normalized, {
            setId: resolvedSetId,
            window,
            limit,
          });

          const result = {
            ...normalized,
            topChaseVerdict: verdict,
            isStale: false,
            isLastKnownGood: false,
          };

          // Settle ONLY on a complete payload or on a settled, non-retryable
          // truth (genuinely new set / empty snapshot).
          //
          // The previous condition was `verdict.renderable || !retryable`. A
          // partially complete payload is BOTH renderable and structurally
          // incomplete, so it settled immediately and the cards missing history
          // kept displaying "Awaiting trend" with no automatic retry. Partial
          // and identity-mismatch payloads are now retried.
          if (verdict.complete || !isRetryableTopChaseStatus(verdict.status)) {
            // Only a COMPLETE payload is ever stored as last-known-good, so a
            // degraded response can never be resurrected later as if current.
            if (verdict.complete) {
              topChaseLastKnownGood.set(identityKey, { ...result, isLastKnownGood: true, isStale: true });
            }
            return result;
          }

          lastError = buildTopChaseContractError(verdict);
        } catch (error) {
          lastError = error;
          if (!isRetryableTopChaseError(error)) {
            // A non-retryable 4xx is a settled answer; do not spend attempt two.
            break;
          }
        }

        if (attempt === 1) {
          await new Promise((resolve) => setTimeout(resolve, TOP_CHASE_RETRY_DELAY_MS));
        }
      }

      // Both attempts are spent. A validated same-set + same-window + same-limit
      // payload may stand in, clearly marked stale. A different set's payload
      // never may, and generic checklist rows are never a Top Chase result.
      const lastKnownGood = topChaseLastKnownGood.get(identityKey);
      if (lastKnownGood) {
        debugTiming("top_chase.serving_last_known_good", { setId: resolvedSetId, window, limit });
        return { ...lastKnownGood, isStale: true, isLastKnownGood: true };
      }

      // No last-known-good. A partially complete payload is NOT an acceptable
      // final answer — rendering half a grid with the rest stuck on "Awaiting
      // trend" is the misleading outcome this contract exists to prevent. Throw
      // so the section shows its existing error state and Retry button.
      throw lastError || buildTopChaseContractError(null);
    },
    { manageSignal: false }
  );
}

export async function getPokemonSetSealedMarket(setId) {
  const resolvedSetId = String(setId || "").trim();
  if (!resolvedSetId) {
    throw new Error("Set id is required");
  }
  const cacheKey = `sealed:${resolvedSetId}`;
  return joinSlimModuleRequest(cacheKey, async ({ signal } = {}) => {
    const response = await fetch(
      `/api/tcgs/pokemon/sets/${encodeURIComponent(resolvedSetId)}/market/sealed`,
      { method: "GET", signal }
    );
    const payload = await readJsonResponse(response, "Unable to load sealed market history");
    const identity = payload?.set || {};
    const target = resolvedSetId.toLowerCase().replace(/[^a-z0-9]+/g, "");
    const matches = [identity.id, identity.canonicalKey, identity.slug]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().replace(/[^a-z0-9]+/g, "") === target);
    if (!matches) {
      const error = new Error("Sealed market response did not match the requested set");
      error.code = "POKEMON_SET_SEALED_MARKET_IDENTITY_MISMATCH";
      error.retryable = false;
      throw error;
    }
    const setMarket = payload?.setMarket || payload?.set_market || null;
    const normalizedSetMarket = setMarket
      ? {
          ...setMarket,
          history: setMarket.history || [],
          productCount: setMarket.productCount ?? setMarket.product_count ?? payload?.products?.length ?? null,
          marketBreadth: setMarket.marketBreadth || setMarket.market_breadth || {},
          marketIndex: normalizePreparedMarketIndex(setMarket.marketIndex || setMarket.market_index),
        }
      : null;
    return {
      ...payload,
      products: Array.isArray(payload?.products) ? payload.products : [],
      setMarket: normalizedSetMarket,
      set_market: normalizedSetMarket,
    };
  });
}

export async function getPokemonSetValueHistory(setId, { days = 365, scope = "standard" } = {}) {
  const resolvedSetId = String(setId || "").trim();
  if (!resolvedSetId) {
    throw new Error("Set id is required");
  }

  const params = new URLSearchParams();
  params.set("snapshot_contract", SET_VALUE_SNAPSHOT_CONTRACT_VERSION);
  if (days) {
    params.set("days", String(days));
  }
  if (scope) {
    params.set("scope", String(scope));
  }

  const cacheKey = `value-history:${resolvedSetId}:${days || ""}:${scope || ""}`;
  return joinSlimModuleRequest(cacheKey, async ({ signal } = {}) => {
    const response = await fetch(
      `/api/tcgs/pokemon/sets/${encodeURIComponent(resolvedSetId)}/market/value-history${params.toString() ? `?${params}` : ""}`,
      {
        method: "GET",
        signal,
      }
    );

    return normalizeSetValueHistoryPayload(
      await readJsonResponse(response, "Unable to load set value history")
    );
  });
}

export function normalizeOverviewPayload(payload) {
  // Every field accepts the snake_case alias too. normalizeMarketDashboardPayload
  // already did, and Opening Profit vs Cost silently rendered as "no data"
  // if the slim /overview response ever came back snake_cased.
  const historiesByScope =
    payload?.setValueHistoriesByScope && typeof payload.setValueHistoriesByScope === "object"
      ? payload.setValueHistoriesByScope
      : payload?.set_value_histories_by_scope && typeof payload.set_value_histories_by_scope === "object"
      ? payload.set_value_histories_by_scope
      : {};
  const normalizedHistoriesByScope = Object.fromEntries(
    Object.entries(historiesByScope).map(([scope, history]) => [
      scope,
      normalizeDailySetValueHistory(Array.isArray(history) ? history : []),
    ])
  );
  const availableScopes = Array.isArray(payload?.availableScopes)
    ? payload.availableScopes
    : Array.isArray(payload?.available_scopes)
    ? payload.available_scopes
    : [];
  const performanceVsCostHistory = normalizeSimulationPerformanceHistory(
    payload?.performanceVsCostHistory || payload?.performance_vs_cost_history || []
  );
  const cardsMarket = normalizePreparedCardsMarket(payload?.cardsMarket || payload?.cards_market);

  return {
    set: {
      id: toOptionalString(payload?.set?.id),
      name: toOptionalString(payload?.set?.name),
      slug: toOptionalString(payload?.set?.slug),
    },
    window: toOptionalString(payload?.window ?? payload?.window_key),
    setValueHistoriesByScope: normalizedHistoriesByScope,
    set_value_histories_by_scope: normalizedHistoriesByScope,
    performanceVsCostHistory,
    performance_vs_cost_history: performanceVsCostHistory,
    cardsMarket,
    cards_market: cardsMarket,
    availableScopes: availableScopes
      .map((scope) => ({
        key: toOptionalString(scope?.key),
        label: toOptionalString(scope?.label),
        latestDate: toOptionalString(scope?.latestDate ?? scope?.latest_date),
      }))
      .filter((scope) => scope.key),
    latestMarketDate: toOptionalString(payload?.latestMarketDate ?? payload?.latest_market_date),
    meta: payload?.meta || { warnings: [] },
  };
}

export async function getPokemonSetOverview(setId, { window = DEFAULT_MARKET_DASHBOARD_WINDOW } = {}) {
  const resolvedSetId = String(setId || "").trim();
  if (!resolvedSetId) {
    throw new Error("Set id is required");
  }

  const normalizedWindow = normalizeMarketDashboardWindow(window);
  const params = new URLSearchParams();
  params.set("snapshot_contract", SET_VALUE_SNAPSHOT_CONTRACT_VERSION);
  if (normalizedWindow) {
    params.set("window", normalizedWindow);
  }

  const cacheKey = `overview:${resolvedSetId}:${normalizedWindow || ""}`;
  return joinSlimModuleRequest(cacheKey, async ({ signal } = {}) => {
    const response = await fetch(
      `/api/tcgs/pokemon/sets/${encodeURIComponent(resolvedSetId)}/overview${params.toString() ? `?${params}` : ""}`,
      {
        method: "GET",
        // Overview carries the Opening Profit vs Cost history, so a browser/BFcache
        // hit on a payload from the previous market date is a visible correctness
        // bug, not a saved request. Paired with the proxy's no-store success
        // policy. Deliberately NOT a cache-busting query param: the URL stays
        // stable so the shared in-flight key and any server-side keying still work.
        cache: "no-store",
        signal,
      }
    );

    return normalizeOverviewPayload(
      await readJsonResponse(response, "Unable to load set overview")
    );
  });
}

export async function getPokemonSetMarketMovers(setId, { window = "30D", limit = 10, movement = "all", surface = null, metric = null } = {}) {
  const resolvedSetId = String(setId || "").trim();
  if (!resolvedSetId) {
    throw new Error("Set id is required");
  }

  const params = new URLSearchParams();
  params.set("snapshot_contract", PRICING_SNAPSHOT_CONTRACT_VERSION);
  if (window) {
    params.set("window", String(window));
  }
  if (limit) {
    params.set("limit", String(limit));
  }
  // Shared canonical Cards query contract: section=market-movers,
  // movement=all|heating|cooling, sort=largest-dollar-move (backend-implied).
  if (movement) {
    params.set("movement", String(movement));
  }
  if (surface) params.set("surface", String(surface));
  if (metric) params.set("metric", String(metric));

  const cacheKey = `movers:${resolvedSetId}:${window || ""}:${limit || ""}:${movement || ""}:${surface || ""}:${metric || ""}`;
  return joinSlimModuleRequest(cacheKey, async ({ signal } = {}) => {
    const response = await fetch(
      `/api/tcgs/pokemon/sets/${encodeURIComponent(resolvedSetId)}/market/movers${params.toString() ? `?${params}` : ""}`,
      {
        method: "GET",
        signal,
      }
    );

    return normalizeMarketMoversPayload(
      await readJsonResponse(response, "Unable to load market movers")
    );
  });
}
