const DEFAULT_MARKET_DASHBOARD_SOURCE_WINDOW = "365d";
const DEFAULT_TOP_MARKET_CARDS_WINDOW = "30D";
const SET_VALUE_SCOPE_OPTIONS = [
  { key: "standard", label: "Checklist" },
  { key: "hits", label: "Hits" },
  { key: "top10", label: "Top 10" },
];

function normalizeDashboardWindow(window = DEFAULT_MARKET_DASHBOARD_SOURCE_WINDOW) {
  const text = String(window || DEFAULT_MARKET_DASHBOARD_SOURCE_WINDOW).trim();
  return (text || DEFAULT_MARKET_DASHBOARD_SOURCE_WINDOW).toLowerCase();
}

function normalizeSetId(setId) {
  const text = String(setId || "").trim();
  return text || null;
}

export function createMarketDashboardState({
  status = "idle",
  setId = null,
  payload = null,
  error = null,
  sourceWindow = DEFAULT_MARKET_DASHBOARD_SOURCE_WINDOW,
} = {}) {
  return {
    status,
    setId: normalizeSetId(setId),
    payload: payload || null,
    error: error || null,
    sourceWindow: normalizeDashboardWindow(sourceWindow),
  };
}

export function marketDashboardReducer(state, action) {
  const sourceWindow = action?.sourceWindow || state?.sourceWindow || DEFAULT_MARKET_DASHBOARD_SOURCE_WINDOW;
  const setId = normalizeSetId(action?.setId);

  switch (action?.type) {
    case "visible_window_changed":
      return state;
    case "reset":
      return createMarketDashboardState({
        status: action.status || "idle",
        setId,
        sourceWindow,
      });
    case "loading": {
      const keepPayload = state?.setId === setId && state?.payload ? state.payload : null;
      return createMarketDashboardState({
        status: "loading",
        setId,
        payload: keepPayload,
        sourceWindow,
      });
    }
    case "success":
      return createMarketDashboardState({
        status: "success",
        setId,
        payload: action.payload,
        sourceWindow,
      });
    case "error":
      return createMarketDashboardState({
        status: "error",
        setId,
        payload: state?.setId === setId ? state?.payload : null,
        error: action.error || "Unable to load market dashboard for this set.",
        sourceWindow,
      });
    default:
      return state || createMarketDashboardState();
  }
}

export function hydrateMarketDashboardStateFromCachedPayload({
  setId,
  cachedPayload,
  sourceWindow = DEFAULT_MARKET_DASHBOARD_SOURCE_WINDOW,
} = {}) {
  if (!cachedPayload) {
    return null;
  }
  return marketDashboardReducer(null, {
    type: "success",
    setId,
    payload: cachedPayload,
    sourceWindow,
  });
}

export function buildMarketDashboardStateFromPayload(payload) {
  const rawHistoriesByScope = payload?.setValueHistoriesByScope || {};
  const historiesByScope = Object.fromEntries(
    SET_VALUE_SCOPE_OPTIONS.map((scopeOption) => [
      scopeOption.key,
      Array.isArray(rawHistoriesByScope?.[scopeOption.key]) ? rawHistoriesByScope[scopeOption.key] : [],
    ])
  );
  const availableScopeKeys = new Set(
    (payload?.availableScopes || []).map((entry) => entry?.key).filter(Boolean)
  );
  Object.entries(historiesByScope).forEach(([scope, history]) => {
    if (history.length > 0) {
      availableScopeKeys.add(scope);
    }
  });

  const availableScopes = SET_VALUE_SCOPE_OPTIONS.filter((entry) =>
    availableScopeKeys.size === 0 ? true : availableScopeKeys.has(entry.key)
  );
  const history = historiesByScope.standard || [];
  const hasAnyHistory = Object.values(historiesByScope).some((scopeHistory) => scopeHistory.length > 0);
  const cards = Array.isArray(payload?.topChaseCards) ? payload.topChaseCards : [];
  const marketMovers = payload?.marketMovers && typeof payload.marketMovers === "object"
    ? payload.marketMovers
    : { heatingUp: [], coolingOff: [], all: [], window: DEFAULT_TOP_MARKET_CARDS_WINDOW, windowDays: 30 };
  const meta = payload?.meta || null;

  return {
    topCards: { cards, meta, marketMovers },
    setValue: { history, historiesByScope, availableScopes, meta, hasAnyHistory },
  };
}
