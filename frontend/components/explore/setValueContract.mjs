import { selectOverviewSetValueTrendByScope } from "./setValueTrendSelector.mjs";

export const SET_VALUE_CONTRACT_SCOPES = [
  { key: "standard", label: "Checklist" },
  { key: "hits", label: "Hits" },
  { key: "top10", label: "Top 10" },
];

function toOptionalNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function toOptionalString(value) {
  const text = String(value || "").trim();
  return text || null;
}

function normalizeScopeKey(scope) {
  const text = String(scope || "").trim();
  return text || "standard";
}

function normalizeHistory(history) {
  return Array.isArray(history) ? history.map((point) => ({ ...point })) : [];
}

function toObject(value) {
  return value && typeof value === "object" ? value : {};
}

function getScopeHistory({ history, historiesByScope, scope }) {
  const scopeKey = normalizeScopeKey(scope);
  if (Array.isArray(historiesByScope?.[scopeKey])) {
    return normalizeHistory(historiesByScope[scopeKey]);
  }
  return scopeKey === "standard" ? normalizeHistory(history) : [];
}

function getScopeLabel(scope) {
  const scopeKey = normalizeScopeKey(scope);
  return SET_VALUE_CONTRACT_SCOPES.find((entry) => entry.key === scopeKey)?.label || scopeKey;
}

function getScopeFallback({ scope, current }) {
  if (normalizeScopeKey(scope) !== "standard") {
    return { value: null, asOf: null, source: null };
  }
  return {
    value: toOptionalNumber(current?.value ?? current?.currentValue),
    asOf: toOptionalString(current?.asOf),
    source: toOptionalString(current?.source ?? current?.sourceKey),
  };
}

export function buildSetValueContract(input = {}) {
  const safeInput = toObject(input);
  const {
    setId = null,
    current = null,
    history = [],
    historiesByScope = {},
    availableScopes = SET_VALUE_CONTRACT_SCOPES,
    status = "idle",
    error = null,
  } = safeInput;
  const normalizedHistoriesByScope = Object.fromEntries(
    SET_VALUE_CONTRACT_SCOPES.map((scope) => [
      scope.key,
      getScopeHistory({ history, historiesByScope, scope: scope.key }),
    ])
  );
  const availableScopeMap = new Map(SET_VALUE_CONTRACT_SCOPES.map((scope) => [scope.key, scope]));
  (Array.isArray(availableScopes) ? availableScopes : []).forEach((scope) => {
    if (scope?.key) {
      availableScopeMap.set(scope.key, {
        key: scope.key,
        label: scope.label || getScopeLabel(scope.key),
      });
    }
  });

  const scopes = Object.fromEntries(
    SET_VALUE_CONTRACT_SCOPES.map((scope) => {
      const fallback = getScopeFallback({ scope: scope.key, current });
      const selected = selectSetValueTrendFromContractShape({
        scope: scope.key,
        historiesByScope: normalizedHistoriesByScope,
        fallback,
      });
      return [
        scope.key,
        {
          scope: scope.key,
          label: scope.label,
          currentValue: selected.currentValue,
          asOf: selected.asOf,
          delta30dAmount: selected.delta30d,
          delta30dPercent: selected.delta30dPct,
          // `selected.series` is windowed to preferredWindowKey ("30D") by
          // selectSetValueTrendFromContractShape, same as currentValue/asOf
          // above — not the full normalizedHistoriesByScope range. Consumers
          // that need the full range (e.g. Overview's window switcher) read
          // contract.historiesByScope directly instead of this field.
          history: selected.series,
          status: selected.status,
          diagnostics: selected.diagnostics,
        },
      ];
    })
  );

  const standardScope = scopes.standard;
  const contractStatus = Object.values(scopes).some((scope) => scope.status === "ready")
    ? "ready"
    : standardScope?.status === "partial"
    ? "partial"
    : "missing";

  return {
    setId: toOptionalString(setId),
    current: {
      scope: "standard",
      label: "Checklist",
      value: standardScope?.currentValue ?? null,
      asOf: standardScope?.asOf ?? null,
      source: standardScope?.diagnostics?.source || null,
    },
    scopes,
    historiesByScope: normalizedHistoriesByScope,
    availableScopes: Array.from(availableScopeMap.values()),
    status:
      (status === "error" || status === "success_stale") && standardScope?.currentValue !== null
        ? "partial"
        : contractStatus,
    error: error || null,
    diagnostics: {
      source: "set_value_contract",
      upstreamStatus: status,
      error: error || null,
      missingFields: standardScope?.currentValue === null ? ["current.value"] : [],
    },
  };
}

function selectSetValueTrendFromContractShape(input = {}) {
  const safeInput = toObject(input);
  const { scope, historiesByScope, fallback, selectedWindowKey = null } = safeInput;
  const selected = selectOverviewSetValueTrendByScope({
    historiesByScope,
    selectedScope: scope,
    selectedWindowKey,
    preferredWindowKey: "30D",
  });
  const currentValue = selected.currentValue ?? fallback?.value ?? null;
  const hasHistory = Array.isArray(historiesByScope?.[scope]) && historiesByScope[scope].length > 0;
  const status = selected.hasTrend ? "ready" : currentValue !== null ? "partial" : "missing";
  return {
    ...selected,
    currentValue,
    asOf: selected.lastPoint?.date || fallback?.asOf || null,
    status,
    diagnostics: {
      ...selected.diagnostics,
      source: selected.diagnostics?.source || fallback?.source || null,
      fallbackSource: fallback?.source || null,
      hasCurrentFallback: fallback?.value !== null && fallback?.value !== undefined,
      hasHistory,
      status,
    },
  };
}

export function selectSetValueTrendFromContract(input = {}) {
  const safeInput = toObject(input);
  const {
    contract,
    selectedScope = "standard",
    selectedWindowKey = null,
  } = safeInput;
  const scope = normalizeScopeKey(selectedScope);
  const scopeContract = contract?.scopes?.[scope] || null;
  const fallback = {
    value: scopeContract?.currentValue ?? (scope === "standard" ? contract?.current?.value : null),
    asOf: scopeContract?.asOf ?? (scope === "standard" ? contract?.current?.asOf : null),
    source: scopeContract?.diagnostics?.source ?? (scope === "standard" ? contract?.current?.source : null),
  };
  return selectSetValueTrendFromContractShape({
    scope,
    historiesByScope: contract?.historiesByScope || {},
    fallback,
    selectedWindowKey,
  });
}
