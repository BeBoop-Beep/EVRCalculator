import { createDiagnostics, SET_PAGE_CONTRACT_VERSION, SET_VALUE_SCOPES } from "./setPageContracts.mjs";
import { selectCardDemandValidation } from "../../../components/pokemon/set-page/Insights/cardDemandValidationSelector.mjs";
import { selectDesirabilityValidation } from "../../../components/pokemon/set-page/Insights/desirabilityValidationSelector.mjs";
import { selectTopChaseCards } from "../../../components/pokemon/set-page/Overview/topChaseCardsSelector.mjs";
import { selectCards } from "../../../components/pokemon/set-page/Cards/cardsSelector.mjs";
import { selectCompactSetValue } from "../../../components/pokemon/set-page/PokemonSetHero/compactSetValueSelector.mjs";

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

  return {
    contractVersion: SET_PAGE_CONTRACT_VERSION,
    set: normalizeSet(rawPayload),
    summary,
    setValueSummary: {
      value: setValueSummary.value,
      sourceKey: setValueSummary.key,
      compact: selectCompactSetValue({
        history: rawPayload?.setValueHistory || rawPayload?.set_value_history || [],
        historiesByScope: rawPayload?.setValueHistoriesByScope || rawPayload?.set_value_histories_by_scope || {},
        fallbackMetric: setValueSummary,
      }),
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

export function adaptTopChaseCards(rawPayload = {}) {
  return {
    contractVersion: SET_PAGE_CONTRACT_VERSION,
    set: normalizeSet(rawPayload),
    ...selectTopChaseCards(rawPayload),
  };
}

export function adaptCards(rawPayload = {}) {
  return {
    contractVersion: SET_PAGE_CONTRACT_VERSION,
    set: normalizeSet(rawPayload),
    ...selectCards(rawPayload),
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
