// Shared, framework-agnostic timing helpers for section-level instrumentation.
// Follows the exact conventions already established by
// components/explore/RipStatisticsPageClient.jsx's markSetPagePerformance /
// debugSetPagePerf and the near-identical copies in pokemonSetMarketClient.js
// / pokemonSetCardsClient.js — dev-console only today (no analytics/RUM sink
// exists in this codebase), same `{module}Ms` naming shape as the existing
// server-side "[set-page-route] timings" log in page.js.

const isDevPerfLoggingEnabled = process.env.NODE_ENV !== "production";

export function markSectionTiming(name, detail = {}) {
  if (!isDevPerfLoggingEnabled || typeof performance === "undefined") {
    return;
  }
  try {
    performance.mark(name, { detail });
  } catch {
    try {
      performance.mark(name);
    } catch {
      // Ignore mark failures in older browsers.
    }
  }
}

export function debugSectionTiming(logPrefix, label, details = {}) {
  if (!isDevPerfLoggingEnabled) {
    return;
  }
  console.debug(`${logPrefix} ${label}`, details);
}
