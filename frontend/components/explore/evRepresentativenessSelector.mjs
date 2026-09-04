const finite = (value) => {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
};

const confirmedHorizon = (value) => {
  if (!value || value.status !== "confirmed") return null;
  const packCount = Number.parseInt(String(value.packCount), 10);
  return Number.isFinite(packCount) && packCount > 0 ? { ...value, packCount } : null;
};

export function selectEvRepresentativenessPublicV1(value, expectedCalculationRunId) {
  if (!value || value.contractVersion !== "ev_representativeness_public_v1") return null;
  if (value.methodVersion !== "ev_representativeness_v1") return null;
  if (!expectedCalculationRunId || String(value.calculationRunId) !== String(expectedCalculationRunId)) return null;
  const typicalCapture = finite(value.typicalCapture);
  const top1OutcomeEvShare = finite(value.top1OutcomeEvShare);
  const realizationByPackCount = (Array.isArray(value.realizationByPackCount) ? value.realizationByPackCount : [])
    .map((row) => ({
      packCount: Number.parseInt(String(row?.packCount), 10),
      probabilityAtLeast80PercentEv: finite(row?.probabilityAtLeast80PercentEv),
    }))
    .filter((row) => Number.isFinite(row.packCount) && row.packCount > 0 && row.probabilityAtLeast80PercentEv !== null)
    .sort((a, b) => a.packCount - b.packCount);
  const realizationHorizon = confirmedHorizon(value.realizationHorizon);
  const convergenceHorizon = confirmedHorizon(value.convergenceHorizon);
  if (
    typicalCapture === null &&
    top1OutcomeEvShare === null &&
    !realizationByPackCount.length &&
    !realizationHorizon &&
    !convergenceHorizon
  ) {
    return null;
  }
  return {
    ...value,
    typicalCapture,
    top1OutcomeEvShare,
    realizationHorizon,
    convergenceHorizon,
    realizationByPackCount,
  };
}

export const formatEvRepPercent = (value) => finite(value) === null ? "—" : `${(finite(value) * 100).toFixed(1)}%`;
export const formatEvRepPacks = (value) => value !== null && value !== undefined && Number.isFinite(Number(value)) && Number(value) > 0 ? `${Math.round(Number(value)).toLocaleString("en-US")} packs` : "Unavailable";
