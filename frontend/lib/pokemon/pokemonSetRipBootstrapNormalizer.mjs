const CONTRACT_VERSION = "pokemon-set-rip-bootstrap-v1";

function object(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

export function normalizePokemonSetRipBootstrap(payload) {
  const source = object(payload);
  const canonical = object(source.canonicalRip);
  const collectorSubjects = Array.isArray(source.collectorSubjects) ? source.collectorSubjects : [];
  const overall = object(canonical.overall);
  const financial = object(canonical.financial);
  const collector = { ...object(canonical.collector), topSubjects: collectorSubjects };
  return {
    contractVersion: source.contractVersion || null,
    available: source.contractVersion === CONTRACT_VERSION,
    set: object(source.set),
    calculationRunId: source.calculationRunId || null,
    marketDate: source.marketDate || null,
    canonical: { overall, financial, collector },
    canonicalSource: {
      publicRipContractV10: {
        overallRip: overall,
        financialRip: financial,
        collectorAppeal: collector,
      },
    },
    summary: object(source.summary),
    ripDecision: object(source.ripDecision),
    collectorSubjects,
    publicAnalyticsStatus: object(source.publicAnalyticsStatus),
    meta: object(source.meta),
  };
}

