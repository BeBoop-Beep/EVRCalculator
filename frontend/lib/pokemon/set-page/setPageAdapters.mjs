import { createDiagnostics, SET_PAGE_CONTRACT_VERSION, SET_VALUE_SCOPES } from "./setPageContracts.mjs";
import { selectCardDemandValidation } from "../../../components/pokemon/set-page/Insights/cardDemandValidationSelector.mjs";
import { selectDesirabilityValidation } from "../../../components/pokemon/set-page/Insights/desirabilityValidationSelector.mjs";
import { selectTopChaseCards } from "../../../components/pokemon/set-page/Overview/topChaseCardsSelector.mjs";
import { selectCards } from "../../../components/pokemon/set-page/Cards/cardsSelector.mjs";
import { selectCompactSetValue } from "../../../components/pokemon/set-page/PokemonSetHero/compactSetValueSelector.mjs";
import { selectSimulationDrivers } from "../../../components/explore/simulationDriversSelector.mjs";
import { selectDecisionSignals } from "../../../components/explore/decisionSignalsSelector.mjs";

function toOptionalString(value) {
  const text = String(value || "").trim();
  return text || null;
}

function toOptionalNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function firstNumber(entries, diagnostics) {
  for (const entry of entries) {
    const value = toOptionalNumber(entry.value);
    if (value !== null) {
      return { key: entry.key, value };
    }
  }
  diagnostics.missingFields.push(...entries.map((entry) => entry.key));
  return { key: null, value: null };
}

function normalizeSet(raw) {
  const set = raw?.set || raw?.meta?.set || raw?.meta?.setIdentity || raw?.meta?.set_identity || {};
  return {
    id: toOptionalString(set.id ?? set.set_id ?? raw?.set_id),
    name: toOptionalString(set.name ?? set.set_name ?? raw?.set_name),
    slug: toOptionalString(set.slug ?? set.canonical_key ?? raw?.canonical_key),
    pokemonApiSetId: toOptionalString(set.pokemon_api_set_id ?? set.pokemonApiSetId),
  };
}

function asObject(value) {
  return value && typeof value === "object" ? value : {};
}

function firstObject(candidates = []) {
  for (const candidate of candidates) {
    if (
      candidate &&
      typeof candidate === "object" &&
      !Array.isArray(candidate) &&
      Object.keys(candidate).length > 0
    ) {
      return candidate;
    }
  }
  return {};
}

function firstArray(candidates = []) {
  for (const candidate of candidates) {
    if (Array.isArray(candidate)) {
      return candidate;
    }
  }
  return [];
}

function normalizeDashboardPayload(payload = {}) {
  const market = asObject(payload?.marketDashboard || payload?.market_dashboard);
  const setValueHistoriesByScope =
    asObject(payload?.setValueHistoriesByScope).standard || asObject(payload?.set_value_histories_by_scope).standard
      ? firstObject([payload?.setValueHistoriesByScope, payload?.set_value_histories_by_scope])
      : firstObject([market?.setValueHistoriesByScope, market?.set_value_histories_by_scope]);

  return {
    ...market,
    ...payload,
    topChaseCards: firstArray([payload?.topChaseCards, payload?.top_chase_cards, market?.topChaseCards, market?.top_chase_cards]),
    top_chase_cards: firstArray([payload?.top_chase_cards, payload?.topChaseCards, market?.top_chase_cards, market?.topChaseCards]),
    marketMovers: firstObject([payload?.marketMovers, payload?.market_movers, market?.marketMovers, market?.market_movers]),
    market_movers: firstObject([payload?.market_movers, payload?.marketMovers, market?.market_movers, market?.marketMovers]),
    setValueHistoriesByScope,
    set_value_histories_by_scope: setValueHistoriesByScope,
    availableScopes: firstArray([payload?.availableScopes, payload?.available_scopes, market?.availableScopes, market?.available_scopes]),
    available_scopes: firstArray([payload?.available_scopes, payload?.availableScopes, market?.available_scopes, market?.availableScopes]),
    meta: firstObject([payload?.meta, market?.meta]),
  };
}

function normalizeCardsPayload(payload = {}) {
  const cards = firstArray([
    payload?.cards,
    payload?.payload_json?.cards,
    payload?.snapshot?.cards,
    payload?.pokemon_set_cards_snapshot_latest?.cards,
  ]);
  return {
    ...payload,
    cards,
    cardAppealMarketPriceCorrelation: firstObject([
      payload?.cardAppealMarketPriceCorrelation,
      payload?.card_appeal_market_price_correlation,
      payload?.meta?.cardAppealMarketPriceCorrelation,
      payload?.meta?.card_appeal_market_price_correlation,
    ]),
  };
}

export function adaptSetShell(rawPayload = {}) {
  const diagnostics = createDiagnostics("set_page_shell_payload");
  const summary = rawPayload?.summary && typeof rawPayload.summary === "object" ? { ...rawPayload.summary } : {};
  if (!rawPayload?.summary) diagnostics.missingFields.push("summary");

  const setValueSummary = firstNumber(
    [
      { key: "summary.currentChecklistSetValue", value: summary.currentChecklistSetValue },
      { key: "summary.current_checklist_set_value", value: summary.current_checklist_set_value },
      { key: "summary.set_value_for_validation", value: summary.set_value_for_validation },
      { key: "summary.checklistSetValue", value: summary.checklistSetValue },
      { key: "summary.checklist_set_value", value: summary.checklist_set_value },
      { key: "summary.simulated_set_value", value: summary.simulated_set_value },
      { key: "summary.simulatedSetValue", value: summary.simulatedSetValue },
    ],
    diagnostics
  );
  const compactSetValue = selectCompactSetValue({
    history: rawPayload?.setValueHistory || rawPayload?.set_value_history || [],
    historiesByScope: rawPayload?.setValueHistoriesByScope || rawPayload?.set_value_histories_by_scope || {},
    fallbackMetric: setValueSummary,
  });
  const currentValue = compactSetValue.value ?? setValueSummary.value;
  const delta30dAmount = compactSetValue.deltaAmount ?? null;
  const delta30dPercent = compactSetValue.deltaPercent ?? null;

  return {
    contractVersion: SET_PAGE_CONTRACT_VERSION,
    set: normalizeSet(rawPayload),
    summary,
    setValueSummary: {
      currentValue,
      value: currentValue,
      valueScope: "standard",
      asOf:
        compactSetValue.asOf ||
        toOptionalString(rawPayload?.meta?.asOfDate ?? rawPayload?.meta?.as_of_date ?? rawPayload?.meta?.run_at ?? summary.run_at),
      delta30dAmount,
      delta30dPercent,
      trend30d: delta30dAmount === null ? null : delta30dAmount > 0 ? "up" : delta30dAmount < 0 ? "down" : "flat",
      source:
        compactSetValue.sourceKey === "setValueHistoriesByScope.standard"
          ? "set_value_history"
          : setValueSummary.key
          ? "summary"
          : null,
      confidence: toOptionalString(summary.set_value_confidence ?? summary.setValueConfidence) || null,
      sourceKey: compactSetValue.sourceKey || setValueSummary.key,
      compact: compactSetValue,
    },
    diagnostics,
  };
}

export function adaptSetValueTrend(rawPayload = {}) {
  const diagnostics = createDiagnostics("set_value_trend_payload");
  const historiesByScope =
    rawPayload?.setValueHistoriesByScope && typeof rawPayload.setValueHistoriesByScope === "object"
      ? rawPayload.setValueHistoriesByScope
      : rawPayload?.set_value_histories_by_scope && typeof rawPayload.set_value_histories_by_scope === "object"
      ? rawPayload.set_value_histories_by_scope
      : rawPayload?.history
      ? { [rawPayload?.meta?.valueScope || rawPayload?.meta?.value_scope || "standard"]: rawPayload.history }
      : {};

  const normalizedHistories = Object.fromEntries(
    SET_VALUE_SCOPES.map((scope) => [
      scope.key,
      Array.isArray(historiesByScope[scope.key]) ? historiesByScope[scope.key].map((point) => ({ ...point })) : [],
    ])
  );

  if (!Object.values(normalizedHistories).some((history) => history.length > 0)) {
    diagnostics.missingFields.push("setValueHistoriesByScope");
  }

  return {
    contractVersion: SET_PAGE_CONTRACT_VERSION,
    set: normalizeSet(rawPayload),
    historiesByScope: normalizedHistories,
    availableScopes: Array.isArray(rawPayload?.availableScopes)
      ? rawPayload.availableScopes.map((entry) => ({ ...entry }))
      : Array.isArray(rawPayload?.meta?.availableScopes)
      ? rawPayload.meta.availableScopes.map((entry) => ({ ...entry }))
      : SET_VALUE_SCOPES.map((entry) => ({ ...entry })),
    diagnostics,
  };
}

export function adaptSetValueHistories(rawPayload = {}) {
  return adaptSetValueTrend(rawPayload);
}

export function adaptTopChaseCards(rawPayload = {}) {
  return {
    contractVersion: SET_PAGE_CONTRACT_VERSION,
    set: normalizeSet(rawPayload),
    ...selectTopChaseCards(rawPayload),
  };
}

export function adaptMarketDashboard(rawPayload = {}) {
  const normalized = normalizeDashboardPayload(rawPayload);
  return {
    contractVersion: SET_PAGE_CONTRACT_VERSION,
    set: normalizeSet(rawPayload),
    ...selectTopChaseCards(normalized),
    setValue: adaptSetValueTrend(normalized),
    marketMovers: normalized.marketMovers || normalized.market_movers || { heatingUp: [], coolingOff: [], all: [] },
  };
}

export function adaptCards(rawPayload = {}) {
  return {
    contractVersion: SET_PAGE_CONTRACT_VERSION,
    set: normalizeSet(rawPayload),
    ...selectCards(rawPayload),
  };
}

export function adaptSimulationDrivers(rawPayload = {}) {
  return {
    contractVersion: SET_PAGE_CONTRACT_VERSION,
    ...selectSimulationDrivers(rawPayload),
  };
}

export function adaptDecisionSignalRanks(rawPayload = {}, options = {}) {
  const pillarSignals = Array.isArray(options?.pillarSignals)
    ? options.pillarSignals
    : Array.isArray(rawPayload?.pillarSignals)
    ? rawPayload.pillarSignals
    : [];
  return {
    contractVersion: SET_PAGE_CONTRACT_VERSION,
    ...selectDecisionSignals({
      ...rawPayload,
      pillarSignals,
      requestTimeout: rawPayload?.meta?.requestTimeout === true,
    }),
  };
}

export function adaptDesirabilityValidation(rawPayload = {}, options = {}) {
  return {
    contractVersion: SET_PAGE_CONTRACT_VERSION,
    ...selectDesirabilityValidation(rawPayload?.targets || rawPayload?.rows || rawPayload, options),
  };
}

export function adaptCardDemandValidation(rawPayload = {}, options = {}) {
  return {
    contractVersion: SET_PAGE_CONTRACT_VERSION,
    ...selectCardDemandValidation(rawPayload?.cards || rawPayload?.rows || rawPayload, options),
  };
}

export function adaptCardsFromSources({
  explorePayload = {},
  cardsSnapshotPayload = {},
  cardsFetchPayload = {},
} = {}) {
  return adaptCards(
    normalizeCardsPayload(
      firstObject([
        asObject(explorePayload),
        asObject(cardsSnapshotPayload),
        asObject(cardsFetchPayload),
      ])
    )
  );
}

export function adaptSetValueHistoriesFromSources({
  explorePayload = {},
  marketSnapshotPayload = {},
  marketFetchPayload = {},
  valueHistoryFetchPayload = {},
} = {}) {
  return adaptSetValueTrend(
    normalizeDashboardPayload(
      firstObject([
        asObject(explorePayload),
        asObject(marketSnapshotPayload),
        asObject(marketFetchPayload),
        asObject(valueHistoryFetchPayload),
      ])
    )
  );
}

export function adaptMarketDashboardFromSources({
  explorePayload = {},
  marketSnapshotPayload = {},
  marketFetchPayload = {},
} = {}) {
  return adaptMarketDashboard(
    normalizeDashboardPayload(
      firstObject([
        asObject(explorePayload),
        asObject(marketSnapshotPayload),
        asObject(marketFetchPayload),
      ])
    )
  );
}

export function adaptCardDemandValidationFromSources({
  explorePayload = {},
  checklistState = {},
  cardsPayload = {},
  options = {},
} = {}) {
  const correlation =
    explorePayload?.cardAppealMarketPriceCorrelation ||
    explorePayload?.card_appeal_market_price_correlation ||
    checklistState?.cardAppealMarketPriceCorrelation ||
    cardsPayload?.cardAppealMarketPriceCorrelation ||
    cardsPayload?.card_appeal_market_price_correlation ||
    null;
  const rows = firstArray([cardsPayload?.cards, checklistState?.cards, explorePayload?.cards]);
  return adaptCardDemandValidation({ rows }, { ...options, correlation });
}

export function adaptSimulationDriversFromSources({
  explorePayload = {},
  fallbackPayload = {},
} = {}) {
  return adaptSimulationDrivers(firstObject([asObject(explorePayload), asObject(fallbackPayload)]));
}

export function adaptDecisionSignalRanksFromSources({
  explorePayload = {},
  fallbackPayload = {},
  options = {},
} = {}) {
  return adaptDecisionSignalRanks(firstObject([asObject(explorePayload), asObject(fallbackPayload)]), options);
}
