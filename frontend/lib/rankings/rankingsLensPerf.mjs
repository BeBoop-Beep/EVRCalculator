const enabled = process.env.NODE_ENV !== "production" || process.env.NEXT_PUBLIC_RANKINGS_PERF_AUDIT === "1";

export function markRankingsLens(lens, event) {
  if (!enabled || typeof performance === "undefined" || typeof performance.mark !== "function") return;
  performance.mark(`rankings:${lens}:${event}`);
  if (event === "render-ready") {
    for (const start of ["selected", "request-start", "module-ready"]) {
      try { performance.measure(`rankings:${lens}:${start}-to-ready`, `rankings:${lens}:${start}`, `rankings:${lens}:render-ready`); } catch { /* optional audit mark */ }
    }
  }
}
