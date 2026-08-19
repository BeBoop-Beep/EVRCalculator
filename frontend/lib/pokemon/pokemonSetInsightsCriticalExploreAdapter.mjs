function dualKeyCase(value) {
  if (Array.isArray(value)) return value.map(dualKeyCase);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(Object.entries(value).flatMap(([key, child]) => {
    const snake = key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
    const normalized = dualKeyCase(child);
    return snake === key ? [[key, normalized]] : [[key, normalized], [snake, normalized]];
  }));
}

/** Pass the already-normalized critical contract into the legacy Explore shape. */
export function adaptCriticalInsightsToExplorePayload(critical) {
  return {
    set: critical?.set || null,
    summary: dualKeyCase(critical?.summary || {}),
    interpretation: critical?.interpretation || {},
    ripDecision: critical?.ripDecision ?? null,
    financialRipV3: critical?.financialRipV3 || null,
    overallRipV5: critical?.overallRipV5 || null,
    publicRipContractV5: critical?.publicRipContractV5 || null,
    overallRipV6: critical?.overallRipV6 || null,
    publicRipContractV6: critical?.publicRipContractV6 || null,
    overallRipV8: critical?.overallRipV8 || null,
    publicRipContractV8: critical?.publicRipContractV8 || null,
    overallRipV9: critical?.overallRipV9 || null,
    publicRipContractV9: critical?.publicRipContractV9 || null,
    // Additive V10/V4 transport. Carried verbatim, never derived from V3/V9.
    financialRipV4: critical?.financialRipV4 || null,
    overallRipV10: critical?.overallRipV10 || null,
    publicRipContractV10: critical?.publicRipContractV10 || null,
  };
}
