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
    case "reset": {
      // A reset for the same set that already has a successful payload must
      // not blank the tab — only a genuine set change (or no set at all)
      // should discard the existing seeded/fetched data.
      const keepPayload = setId && state?.setId === setId && state?.payload ? state.payload : null;
      return createMarketDashboardState({
        status: keepPayload ? "success_stale" : action.status || "idle",
        setId,
        payload: keepPayload,
        sourceWindow,
      });
    }
    case "loading": {
      const keepPayload = state?.setId === setId && state?.payload ? state.payload : null;
      return createMarketDashboardState({
        status: keepPayload ? "success_stale" : "loading",
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
      if (state?.setId === setId && state?.payload) {
        return createMarketDashboardState({
          status: "success_stale",
          setId,
          payload: state.payload,
          error: action.error || "Unable to refresh market dashboard for this set.",
          sourceWindow,
        });
      }
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
  const rawHistoriesByScope =
    payload?.setValueHistoriesByScope ||
    payload?.set_value_histories_by_scope ||
    payload?.marketDashboard?.setValueHistoriesByScope ||
    payload?.marketDashboard?.set_value_histories_by_scope ||
    payload?.market_dashboard?.setValueHistoriesByScope ||
    payload?.market_dashboard?.set_value_histories_by_scope ||
    {};
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
  const cards = Array.isArray(payload?.topChaseCards)
    ? payload.topChaseCards
    : Array.isArray(payload?.top_chase_cards)
    ? payload.top_chase_cards
    : Array.isArray(payload?.topMarketCards)
    ? payload.topMarketCards
    : Array.isArray(payload?.top_market_cards)
    ? payload.top_market_cards
    : Array.isArray(payload?.marketDashboard?.topChaseCards)
    ? payload.marketDashboard.topChaseCards
    : Array.isArray(payload?.marketDashboard?.topMarketCards)
    ? payload.marketDashboard.topMarketCards
    : Array.isArray(payload?.market_dashboard?.top_chase_cards)
    ? payload.market_dashboard.top_chase_cards
    : Array.isArray(payload?.market_dashboard?.top_market_cards)
    ? payload.market_dashboard.top_market_cards
    : [];
  const marketMovers =
    payload?.marketMovers && typeof payload.marketMovers === "object"
      ? payload.marketMovers
      : payload?.market_movers && typeof payload.market_movers === "object"
      ? payload.market_movers
      : payload?.marketDashboard?.marketMovers && typeof payload.marketDashboard.marketMovers === "object"
      ? payload.marketDashboard.marketMovers
      : payload?.market_dashboard?.market_movers && typeof payload.market_dashboard.market_movers === "object"
      ? payload.market_dashboard.market_movers
      : { heatingUp: [], coolingOff: [], all: [], window: DEFAULT_TOP_MARKET_CARDS_WINDOW, windowDays: 30 };
  const marketMoversByWindow =
    payload?.marketMoversByWindow && typeof payload.marketMoversByWindow === "object"
      ? payload.marketMoversByWindow
      : payload?.market_movers_by_window && typeof payload.market_movers_by_window === "object"
      ? payload.market_movers_by_window
      : payload?.marketDashboard?.marketMoversByWindow && typeof payload.marketDashboard.marketMoversByWindow === "object"
      ? payload.marketDashboard.marketMoversByWindow
      : payload?.market_dashboard?.market_movers_by_window && typeof payload.market_dashboard.market_movers_by_window === "object"
      ? payload.market_dashboard.market_movers_by_window
      : null;
  const meta = payload?.meta || null;

  return {
    topCards: { cards, meta, marketMovers, marketMoversByWindow },
    setValue: { history, historiesByScope, availableScopes, meta, hasAnyHistory },
  };
}
