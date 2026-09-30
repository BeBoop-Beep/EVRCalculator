export const ACTIVITY_STATUS = Object.freeze({ idle: "idle", loading: "loading", ready: "ready", error: "error" });

export function activityScopeKey(scope) {
  if (!scope) return null;
  const roster = scope.rosterRef || {};
  return [scope.focusMarketKey || "", scope.marketKey, scope.activityGenerationId, roster.kind, roster.marketKey, roster.generationId,
    scope.evidenceFingerprint || "", scope.asOf, scope.windowDays, scope.tier || scope.grade || "RAW"].join("|");
}

const sameRoster = (left, right) => Boolean(left && right
  && left.kind === right.kind && left.marketKey === right.marketKey && left.generationId === right.generationId);

export function hasExactActivityCapability(capability) {
  return Boolean(capability?.available === true
    && capability.marketKey && capability.activityGenerationId && capability.rosterRef
    && capability.rosterRef.kind && capability.rosterRef.marketKey && capability.rosterRef.generationId
    && capability.evidenceFingerprint && capability.asOf
    && [7, 30, 90, 180].includes(capability.windowDays)
    && (capability.tier || capability.grade));
}

export function validateActivityResponseScope(payload, scope) {
  if (!payload || payload.contractVersion !== "market_activity_v1.1") throw new Error("Activity response contract version does not match the request scope.");
  if (!scope || payload.request?.marketKey !== scope.marketKey) throw new Error("Activity response market does not match the request scope.");
  if (payload.request?.activityGenerationId !== scope.activityGenerationId
    || (payload.activityGenerationId !== null && payload.activityGenerationId !== scope.activityGenerationId)) throw new Error("Activity response generation does not match the request scope.");
  if (!sameRoster(payload.request?.rosterRef, scope.rosterRef)) throw new Error("Activity response roster does not match the request scope.");
  if (payload.request?.asOf !== scope.asOf) throw new Error("Activity response as-of date does not match the request scope.");
  if (payload.request?.windowDays !== scope.windowDays) throw new Error("Activity response window does not match the request scope.");
  const responseTier = payload.instrument?.tier || payload.series?.sales?.tier || payload.sales?.tier || null;
  if (responseTier && responseTier !== (scope.tier || scope.grade)) throw new Error("Activity response tier does not match the request scope.");
  if (scope.evidenceFingerprint && payload.evidenceFingerprint !== scope.evidenceFingerprint) throw new Error("Activity response evidence fingerprint does not match the request scope.");
  return payload;
}

export function createActivityRequestOwner(load) {
  let sequence = 0;
  let controller = null;
  return {
    cancel() { sequence += 1; controller?.abort(); controller = null; },
    async request(scope) {
      const requestSequence = ++sequence;
      controller?.abort();
      controller = new AbortController();
      const signal = controller.signal;
      try {
        const data = validateActivityResponseScope(await load({ ...scope, signal }), scope);
        if (signal.aborted || requestSequence !== sequence) return { stale: true };
        return { stale: false, data, scopeKey: activityScopeKey(scope) };
      } catch (error) {
        if (signal.aborted || requestSequence !== sequence || error?.name === "AbortError") return { stale: true };
        return { stale: false, error, scopeKey: activityScopeKey(scope) };
      }
    },
  };
}

export function activityDateGeometry(points = [], canonicalDates = []) {
  const indexByDate = new Map(canonicalDates.map((date, index) => [date, index]));
  const denominator = Math.max(canonicalDates.length - 1, 1);
  return points.flatMap((point) => {
    const index = indexByDate.get(point.date);
    return index === undefined ? [] : [{ ...point, canonicalIndex: index, xPercent: 2 + (index / denominator) * 96 }];
  });
}

export function capabilityIsCurrent(capability, evaluatedAt = Date.now()) {
  if (!capability?.available) return false;
  return !capability.expiresAt || Date.parse(capability.expiresAt) > Number(evaluatedAt);
}

export function activityPointAtDate(payload, view, date) {
  if (!payload?.series || !date) return { state: "UNKNOWN", point: null };
  const series = view === "supply" ? payload.series.supply?.listings : payload.series.sales?.counts;
  const point = series?.points?.find((entry) => entry.date === date) || null;
  if (point) return { state: point.value === 0 || point.observedCount === 0 ? "PROVEN_ZERO" : point.proofState || "OBSERVED", point };
  const span = view === "sales" ? payload.series.sales?.provenSpan : null;
  if (span && date >= span.startDate && date <= span.endDate) return { state: "PROVEN_ZERO", point: null };
  return { state: "UNKNOWN", point: null };
}

