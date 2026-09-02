import { buildRipDistributionMarkers, selectBasicRipDistributionMarkers } from "../../components/explore/ripDistributionMarkers.mjs";

function number(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function dualKeyCase(value) {
  if (Array.isArray(value)) return value.map(dualKeyCase);
  if (!value || typeof value !== "object") return value;
  const result = {};
  for (const [key, inner] of Object.entries(value)) {
    const converted = dualKeyCase(inner);
    result[key] = converted;
    const snakeKey = key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
    if (!(snakeKey in result)) result[snakeKey] = converted;
  }
  return result;
}

/**
 * Adapt the PUBLIC /rip/simulation-evidence projection (contractVersion
 * "pokemon-set-rip-simulation-evidence-v1") for the homepage's shared
 * RipDistributionChart. This is the SAME public marker policy the Set RIP
 * tab uses (RipDecisionPage's Basic path, via ripDistributionMarkers.mjs) —
 * the homepage never invents its own vocabulary and never shows a paid
 * marker's real value (P25/P75/Bad Floor/Big Hit/Strong Upside/Jackpot
 * Upside/Best Pull all render locked, not absent, matching the set page).
 */
export function selectLandingDistribution(payload) {
  const bins = Array.isArray(payload?.distributionBins) ? payload.distributionBins : [];
  const thresholdBins = Array.isArray(payload?.thresholdBins) ? payload.thresholdBins : [];
  if (bins.length === 0 && thresholdBins.length === 0) return null;

  const summary = payload?.summary || {};
  const simulationCount = number(summary?.simulation_count) ?? number(summary?.simulationCount);
  const fullMarkers = buildRipDistributionMarkers({ summary, percentiles: [] });
  const markers = selectBasicRipDistributionMarkers(fullMarkers).filter((marker) => marker.value !== null || marker.locked);

  return {
    bins: dualKeyCase(bins),
    thresholdBins: dualKeyCase(thresholdBins),
    markers,
    simulationCount,
  };
}
