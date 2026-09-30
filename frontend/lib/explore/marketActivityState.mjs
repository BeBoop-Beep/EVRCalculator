export const ACTIVITY_STATUS = Object.freeze({ idle: "idle", loading: "loading", ready: "ready", error: "error" });

export function activityScopeKey(scope) {
  if (!scope) return null;
  const roster = scope.rosterRef || {};
  return [scope.marketKey, scope.activityGenerationId, roster.kind, roster.marketKey, roster.generationId,
    scope.evidenceFingerprint || "", scope.asOf, scope.windowDays, scope.grade || "raw"].join("|");
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
        const data = await load({ ...scope, signal });
        if (signal.aborted || requestSequence !== sequence) return { stale: true };
        return { stale: false, data, scopeKey: activityScopeKey(scope) };
      } catch (error) {
        if (signal.aborted || requestSequence !== sequence || error?.name === "AbortError") return { stale: true };
        return { stale: false, error, scopeKey: activityScopeKey(scope) };
      }
    },
  };
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

