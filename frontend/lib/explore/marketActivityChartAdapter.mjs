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
  const listingByDate = new Map(listings.map((point) => [point.date, point]));
  const quantities = points(series.supply?.quantity);
  const quantityByDate = new Map(quantities.map((point) => [point.date, point]));
  // FMA v1.1 does not require listing and quantity point dates to align. Build
  // from their union and preserve a missing side as null (including real zero).
  const supplyDates = [...new Set([...listingByDate.keys(), ...quantityByDate.keys()])].sort();
  const supply = supplyDates.map((date) => ({
    date,
    listingOfferCount: listingByDate.get(date)?.value ?? null,
    listedQuantity: quantityByDate.get(date)?.value ?? null,
    contributingConstituents: listingByDate.get(date)?.contributingConstituents
      ?? quantityByDate.get(date)?.contributingConstituents ?? null,
    source: series.supply?.source || null,
    quantityProvenance: series.supply?.aggregation || null,
    observedAt: listingByDate.get(date)?.observedAt ?? quantityByDate.get(date)?.observedAt ?? null,
    currentUntil: listingByDate.get(date)?.currentUntil ?? quantityByDate.get(date)?.currentUntil ?? null,
    state: listingByDate.get(date)?.state ?? quantityByDate.get(date)?.state ?? "HISTORICAL_OBSERVATION",
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
