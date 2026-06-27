export const SET_PAGE_CONTRACT_VERSION = "pokemon_set_page_contract_v1";

export const SET_VALUE_SCOPES = Object.freeze([
  { key: "standard", label: "Checklist" },
  { key: "hits", label: "Hits" },
  { key: "top10", label: "Top 10" },
]);

export const SetShellContract = Object.freeze({
  version: SET_PAGE_CONTRACT_VERSION,
  fields: ["set", "summary", "setValueSummary", "diagnostics"],
});

export const SetValueTrendContract = Object.freeze({
  version: SET_PAGE_CONTRACT_VERSION,
  fields: ["set", "historiesByScope", "availableScopes", "diagnostics"],
});

export const TopChaseCardsContract = Object.freeze({
  version: SET_PAGE_CONTRACT_VERSION,
  fields: ["set", "cards", "marketMovers", "diagnostics"],
});

export const CardsContract = Object.freeze({
  version: SET_PAGE_CONTRACT_VERSION,
  fields: ["set", "cards", "cardAppealMarketPriceCorrelation", "diagnostics"],
});

export const DesirabilityValidationContract = Object.freeze({
  version: SET_PAGE_CONTRACT_VERSION,
  fields: ["rows", "points", "pearson", "spearman", "sampleCount", "diagnostics"],
});

export const CardDemandValidationContract = Object.freeze({
  version: SET_PAGE_CONTRACT_VERSION,
  fields: ["rows", "points", "pearson", "spearman", "sampleCount", "diagnostics"],
});

export function createDiagnostics(source, details = {}) {
  return {
    source,
    contractVersion: SET_PAGE_CONTRACT_VERSION,
    missingFields: [],
    warnings: [],
    ...details,
  };
}
