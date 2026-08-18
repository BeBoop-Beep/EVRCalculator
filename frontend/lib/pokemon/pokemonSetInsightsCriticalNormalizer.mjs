function toOptionalString(value) {
  const normalized = String(value || "").trim();
  return normalized || null;
}

function toPlainObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function toNullablePlainObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : null;
}

export function normalizePokemonSetInsightsCriticalPayload(payload) {
  return {
    ripDecision: toNullablePlainObject(payload?.ripDecision),
    set: {
      id: toOptionalString(payload?.set?.id),
      name: toOptionalString(payload?.set?.name),
      slug: toOptionalString(payload?.set?.slug ?? payload?.set?.canonicalKey),
    },
    summary: toPlainObject(payload?.summary),
    recommendation: toPlainObject(payload?.recommendation),
    ripScore: toPlainObject(payload?.ripScore),
    rip: toPlainObject(payload?.rip),
    ripCore: toPlainObject(payload?.ripCore),
    financialRipV3: toPlainObject(payload?.financialRipV3),
    overallRipV5: toPlainObject(payload?.overallRipV5),
    publicRipContractV5: toPlainObject(payload?.publicRipContractV5),
    overallRipV6: toPlainObject(payload?.overallRipV6),
    publicRipContractV6: toPlainObject(payload?.publicRipContractV6),
    overallRipV8: toPlainObject(payload?.overallRipV8),
    publicRipContractV8: toPlainObject(payload?.publicRipContractV8),
    overallRipV9: toPlainObject(payload?.overallRipV9),
    publicRipContractV9: toPlainObject(payload?.publicRipContractV9),
    openingExperience: toPlainObject(payload?.openingExperience),
    publicAnalyticsCohort: toPlainObject(payload?.publicAnalyticsCohort),
    publicAnalyticsStatus: toOptionalString(payload?.publicAnalyticsStatus),
    interpretation: toPlainObject(payload?.interpretation),
    meta: payload?.meta || { warnings: [] },
  };
}
