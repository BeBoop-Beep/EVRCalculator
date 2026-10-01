import { boundedFetch, EXPLORER_REQUEST_BOUNDS_MS } from "./marketExplorerBoundedRequest.mjs";
import { resolveSeriesIdentityColor, softSeriesColor } from "./marketExplorerSeriesColors.mjs";

export async function fetchDirectInstrument({ asset, instrumentId, startDate = null, signal, fetchImpl = fetch }) {
  const { response, payload } = await boundedFetch("/api/market/explorer/direct-instrument", {
    method: "POST", credentials: "include", cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ asset, instrumentId, startDate }),
  }, { signal, fetchImpl, timeoutMs: EXPLORER_REQUEST_BOUNDS_MS.directInstrument,
    timeoutCode: "DIRECT_INSTRUMENT_TIMEOUT",
    timeoutMessage: "This item history took too long to load. Please try again.",
    read: (result) => result.json().catch(() => null) });
  if (!response.ok) {
    const error = new Error(payload?.message || "Direct item history is unavailable");
    error.status = response.status; error.code = payload?.code || "DIRECT_INSTRUMENT_FAILED";
    throw error;
  }
  const color = resolveSeriesIdentityColor(payload.seriesKey, payload.seriesKey);
  return {
    key: payload.seriesKey, canonicalInstrumentId: payload.instrumentId,
    label: payload.label, shortLabel: payload.label, asset: payload.asset,
    group: payload.asset === "sealed" ? "sealed" : "card",
    marketType: "direct_instrument", scopeKind: "instrument",
    compositionKind: "composition", availability: "available", available: true,
    basketValue: payload.currentPrice, browseValue: payload.currentPrice,
    sourceAsOf: payload.asOf, comparisonAsOf: payload.asOf,
    historyStartDate: payload.historyStart, historyEndDate: payload.historyEnd,
    trend: (payload.history || []).map((point) => ({ date: point.date, value: Number(point.indexValue), trackedValue: Number(point.rawPrice) })),
    changes: {}, familyChanges: {}, constituentCount: 1,
    currentConstituents: payload.constituents,
    metadata: { instrumentId: payload.instrumentId, setName: payload.setName,
      imageUrl: payload.imageUrl, directInstrument: true },
    color, softColor: softSeriesColor(color),
  };
}
