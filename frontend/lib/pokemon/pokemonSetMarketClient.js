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

function joinSlimModuleRequest(key, factory) {
  if (slimModuleInflight.has(key)) {
    return slimModuleInflight.get(key);
  }
  const request = factory().finally(() => {
    slimModuleInflight.delete(key);
  });
  slimModuleInflight.set(key, request);
  return request;
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

function normalizeTopMarketCardsPayload(payload) {
  const cards = Array.isArray(payload?.cards) ? payload.cards : [];
  const topChaseCardHistories = normalizeTopChaseCardHistories(payload);

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

      return {
        id: toOptionalString(card?.cardId ?? card?.card_id ?? card?.id),
        cardId: toOptionalString(card?.cardId ?? card?.card_id ?? card?.id),
        cardVariantId: toOptionalString(card?.cardVariantId ?? card?.card_variant_id),
        setId: toOptionalString(card?.setId ?? card?.set_id),
        name: toOptionalString(card?.name),
        imageUrl: toOptionalString(card?.imageUrl ?? card?.image_url),
        imageSmallUrl: toOptionalString(card?.imageSmallUrl ?? card?.image_small_url),
        imageLargeUrl: toOptionalString(card?.imageLargeUrl ?? card?.image_large_url),
        rarity: toOptionalString(card?.rarity),
        setNumber: toOptionalString(card?.setNumber ?? card?.set_number),
        cardNumber: toOptionalString(card?.setNumber ?? card?.set_number),
        estimatedMarketPrice: toOptionalNumber(card?.estimatedMarketPrice ?? card?.estimated_market_price),
        marketPrice: toOptionalNumber(card?.marketPrice ?? card?.estimatedMarketPrice ?? card?.estimated_market_price),
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

function normalizeMarketMoverCard(card) {
  const currentPrice = toOptionalNumber(card?.currentPrice ?? card?.current_price ?? card?.marketPrice ?? card?.market_price);
  const change30dAmount = toOptionalNumber(card?.change30dAmount ?? card?.change_30d_amount);
  const change30dPercent = toOptionalNumber(card?.change30dPercent ?? card?.change_30d_percent);
  const movementScore = toOptionalNumber(card?.movementScore ?? card?.movement_score);
  const movementLabel = toOptionalString(card?.movementLabel ?? card?.movement_label);

  return {
    id: toOptionalString(card?.cardId ?? card?.card_id ?? card?.id),
    cardId: toOptionalString(card?.cardId ?? card?.card_id ?? card?.id),
    cardVariantId: toOptionalString(card?.cardVariantId ?? card?.card_variant_id),
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
    change30dAmount,
    change30dPercent,
    movementScore,
    movementLabel,
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

  return {
    window: toOptionalString(source?.window ?? payload?.window ?? payload?.window_key) || "30D",
    windowDays: toOptionalNumber(source?.windowDays ?? source?.window_days ?? payload?.windowDays ?? payload?.window_days) ?? 30,
    heatingUp: heating.map(normalizeMarketMoverCard).filter((card) => card.name),
    coolingOff: cooling.map(normalizeMarketMoverCard).filter((card) => card.name),
    all: all.map(normalizeMarketMoverCard).filter((card) => card.name),
  };
}

export function normalizeMarketMoversPayload(payload) {
  const source =
    payload?.marketMovers && typeof payload.marketMovers === "object"
      ? payload.marketMovers
      : payload?.market_movers && typeof payload.market_movers === "object"
      ? payload.market_movers
      : {};
  return normalizeMarketMoversEntry(source, payload);
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
    meta: payload?.meta,
  });
}

export async function getPokemonSetTopChase(setId, { window = "30D", limit = 10 } = {}) {
  const resolvedSetId = String(setId || "").trim();
  if (!resolvedSetId) {
    throw new Error("Set id is required");
  }

  const params = new URLSearchParams();
  if (window) {
    params.set("window", String(window));
  }
  if (limit) {
    params.set("limit", String(limit));
  }

  const cacheKey = `top-chase:${resolvedSetId}:${window || ""}:${limit || ""}`;
  return joinSlimModuleRequest(cacheKey, async () => {
    const response = await fetch(
      `/api/tcgs/pokemon/sets/${encodeURIComponent(resolvedSetId)}/market/top-chase${params.toString() ? `?${params}` : ""}`,
      {
        method: "GET",
      }
    );

    return normalizeTopChasePayload(
      await readJsonResponse(response, "Unable to load top chase cards")
    );
  });
}

export async function getPokemonSetValueHistory(setId, { days = 365, scope = "standard" } = {}) {
  const resolvedSetId = String(setId || "").trim();
  if (!resolvedSetId) {
    throw new Error("Set id is required");
  }

  const params = new URLSearchParams();
  if (days) {
    params.set("days", String(days));
  }
  if (scope) {
    params.set("scope", String(scope));
  }

  const cacheKey = `value-history:${resolvedSetId}:${days || ""}:${scope || ""}`;
  return joinSlimModuleRequest(cacheKey, async () => {
    const response = await fetch(
      `/api/tcgs/pokemon/sets/${encodeURIComponent(resolvedSetId)}/market/value-history${params.toString() ? `?${params}` : ""}`,
      {
        method: "GET",
      }
    );

    return normalizeSetValueHistoryPayload(
      await readJsonResponse(response, "Unable to load set value history")
    );
  });
}

export function normalizeOverviewPayload(payload) {
  const historiesByScope =
    payload?.setValueHistoriesByScope && typeof payload.setValueHistoriesByScope === "object"
      ? payload.setValueHistoriesByScope
      : {};
  const normalizedHistoriesByScope = Object.fromEntries(
    Object.entries(historiesByScope).map(([scope, history]) => [
      scope,
      normalizeDailySetValueHistory(Array.isArray(history) ? history : []),
    ])
  );
  const availableScopes = Array.isArray(payload?.availableScopes) ? payload.availableScopes : [];

  return {
    set: {
      id: toOptionalString(payload?.set?.id),
      name: toOptionalString(payload?.set?.name),
      slug: toOptionalString(payload?.set?.slug),
    },
    window: toOptionalString(payload?.window),
    setValueHistoriesByScope: normalizedHistoriesByScope,
    performanceVsCostHistory: normalizeSimulationPerformanceHistory(payload?.performanceVsCostHistory || []),
    availableScopes: availableScopes
      .map((scope) => ({
        key: toOptionalString(scope?.key),
        label: toOptionalString(scope?.label),
        latestDate: toOptionalString(scope?.latestDate),
      }))
      .filter((scope) => scope.key),
    latestMarketDate: toOptionalString(payload?.latestMarketDate),
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
  if (normalizedWindow) {
    params.set("window", normalizedWindow);
  }

  const cacheKey = `overview:${resolvedSetId}:${normalizedWindow || ""}`;
  return joinSlimModuleRequest(cacheKey, async () => {
    const response = await fetch(
      `/api/tcgs/pokemon/sets/${encodeURIComponent(resolvedSetId)}/overview${params.toString() ? `?${params}` : ""}`,
      {
        method: "GET",
      }
    );

    return normalizeOverviewPayload(
      await readJsonResponse(response, "Unable to load set overview")
    );
  });
}

export async function getPokemonSetMarketMovers(setId, { window = "30D", limit = 5 } = {}) {
  const resolvedSetId = String(setId || "").trim();
  if (!resolvedSetId) {
    throw new Error("Set id is required");
  }

  const params = new URLSearchParams();
  if (window) {
    params.set("window", String(window));
  }
  if (limit) {
    params.set("limit", String(limit));
  }

  const cacheKey = `movers:${resolvedSetId}:${window || ""}:${limit || ""}`;
  return joinSlimModuleRequest(cacheKey, async () => {
    const response = await fetch(
      `/api/tcgs/pokemon/sets/${encodeURIComponent(resolvedSetId)}/market/movers${params.toString() ? `?${params}` : ""}`,
      {
        method: "GET",
      }
    );

    return normalizeMarketMoversPayload(
      await readJsonResponse(response, "Unable to load market movers")
    );
  });
}
