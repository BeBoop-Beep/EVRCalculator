export const MARKET_ACTIVITY_SUPPORTED_WINDOWS = Object.freeze([7, 30, 90, 180]);

const points = (value) => Array.isArray(value?.points) ? value.points.map((point) => ({ ...point })) : [];

/** Presentation-only projection of the frozen FMA v1.1 group contract.
 * Dates absent from the source remain absent; this adapter never fills gaps.
 */
export function activityChartDto(payload) {
  const series = payload?.series || {};
  const sales = points(series.sales?.counts).map((point) => ({
    date: point.date,
    observedSoldCount: point.observedCount,
    proofState: point.proofState,
    contributingConstituents: point.contributingConstituents,
    provenConstituents: point.provenConstituents,
  }));
  const listings = points(series.supply?.listings);
  const quantities = new Map(points(series.supply?.quantity).map((point) => [point.date, point]));
  const supply = listings.map((point) => ({
    date: point.date,
    listingOfferCount: point.value,
    listedQuantity: quantities.get(point.date)?.value ?? null,
    contributingConstituents: point.contributingConstituents,
    source: series.supply?.source || null,
    quantityProvenance: series.supply?.aggregation || null,
    observedAt: point.observedAt || `${point.date}T00:00:00Z`,
    currentUntil: point.currentUntil ?? null,
    state: point.state || "HISTORICAL_OBSERVATION",
  }));
  return {
    activityGenerationId: payload?.activityGenerationId || null,
    rosterRef: payload?.roster?.rosterRevision || null,
    asOf: series.asOf || null,
    activityRange: series.activityRange || null,
    canonicalRange: series.canonicalRange || null,
    coverage: payload?.coverage || null,
    totals: payload?.totals || null,
    sales: { source: series.sales?.source || null, points: sales },
    supply: { source: series.supply?.source || null, points: supply },
    storage: series.storage || null,
    zeroRule: series.zeroRule || null,
    supportedWindows: [...MARKET_ACTIVITY_SUPPORTED_WINDOWS],
  };
}
