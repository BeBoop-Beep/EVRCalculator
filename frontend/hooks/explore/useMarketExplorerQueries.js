"use client";

import { useCallback, useRef, useState } from "react";
import { buildQueryKey, queryResultToSeries, resolveBenchmarkSpec } from "@/lib/explore/marketExplorerQuery.mjs";
import { attachMarketInstance, replaceMarketInstance, specsAreEquivalent } from "@/lib/explore/marketExplorerInstances.mjs";

export const MARKET_QUERY_OUTCOME = Object.freeze({
  emptyNow: "QUERY_EMPTY_NOW",
  noHistory: "QUERY_NO_HISTORY",
  building: "QUERY_BUILDING",
  refreshing: "QUERY_CACHE_REFRESHING",
  rateLimited: "QUERY_RATE_LIMITED",
  invalid: "QUERY_INVALID",
  unavailable: "QUERY_UNAVAILABLE",
  failed: "QUERY_FAILED",
});

const STATUS_CODE = {
  400: MARKET_QUERY_OUTCOME.invalid,
  404: MARKET_QUERY_OUTCOME.unavailable,
  429: MARKET_QUERY_OUTCOME.rateLimited,
  503: MARKET_QUERY_OUTCOME.building,
};

export class MarketExplorerQueryApiError extends Error {
  constructor(message, { code, status, retryAfter } = {}) {
    super(message);
    this.name = "MarketExplorerQueryApiError";
    this.code = code || MARKET_QUERY_OUTCOME.failed;
    this.status = status || 0;
    this.retryAfter = retryAfter ?? null;
  }
}

async function executeQuery(spec) {
  const response = await fetch("/api/market/explorer/query", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    // SUMMARY, NEVER FULL. Building a market only needs its chart series and
    // headline numbers; `currentConstituents` for a broad universe (Global
    // All Raw alone is 33,955 rows) has no business riding along with every
    // Build Market click. Composition is fetched separately, a page at a
    // time, only when and if the Constituents section actually inspects this
    // market — see useMarketExplorerConstituentPage.
    body: JSON.stringify({ ...spec, responseMode: "summary" }),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    // FastAPI answers with `detail`, the app's own routes with `message`.
    // Reading only one of them turned an auth answer into a generic failure.
    const detail = payload?.detail && typeof payload.detail === "object" ? payload.detail : null;
    const message = payload?.message || detail?.message || (typeof payload?.detail === "string" ? payload.detail : null);
    throw new MarketExplorerQueryApiError(
      (response.status === 401 || response.status === 403)
        ? "Sign in to build a custom market."
        : message || "Unable to execute this market query",
      {
        code: payload?.code || detail?.code || STATUS_CODE[response.status] || MARKET_QUERY_OUTCOME.failed,
        status: response.status,
        retryAfter: response.headers.get("Retry-After") || payload?.retryAfter || detail?.retryAfter || null,
      },
    );
  }
  const series = queryResultToSeries(payload);
  if (!series) throw new Error("The query response did not contain a market series");
  return series;
}

export default function useMarketExplorerQueries() {
  const [querySeries, setQuerySeries] = useState([]);
  const pendingKeys = useRef(new Set());
  const addQuery = useCallback(async (spec, { exactItems = [] } = {}) => {
    const requestedKey = buildQueryKey(spec);
    if (querySeries.some((entry) => entry.spec && buildQueryKey(entry.spec) === requestedKey) || pendingKeys.current.has(requestedKey)) return "duplicate";
    pendingKeys.current.add(requestedKey);
    try {
      const result = await executeQuery(spec);
      const benchmarkSpec = resolveBenchmarkSpec(spec);
      const benchmark = benchmarkSpec ? await executeQuery(benchmarkSpec) : null;
      let outcome = "added";
      setQuerySeries((current) => {
        if (current.some((entry) => entry.queryFingerprint === result.queryFingerprint)) { outcome = "duplicate"; return current; }
        const additions = [];
        const resultInstance = attachMarketInstance(result, { exactItems });
        if (benchmark && !current.some((entry) => entry.queryFingerprint === benchmark.queryFingerprint)) additions.push({ ...attachMarketInstance(benchmark), benchmarkForInstanceId: resultInstance.instanceId });
        additions.push(resultInstance);
        return [...current, ...additions];
      });
      return outcome;
    } finally { pendingKeys.current.delete(requestedKey); }
  }, [querySeries]);
  const updateQuery = useCallback(async (instanceId, spec, { exactItems = [] } = {}) => {
    const current = querySeries.find((entry) => entry.instanceId === instanceId);
    if (!current) return "missing";
    if (specsAreEquivalent(current.spec, spec)) return "unchanged";
    const requestedKey = buildQueryKey(spec);
    if (pendingKeys.current.has(requestedKey)) return "pending";
    if (querySeries.some((entry) => entry.instanceId !== instanceId && specsAreEquivalent(entry.spec, spec))) return "duplicate";
    pendingKeys.current.add(requestedKey);
    try {
      const result = await executeQuery(spec);
      const benchmarkSpec = resolveBenchmarkSpec(spec);
      const benchmark = benchmarkSpec ? await executeQuery(benchmarkSpec) : null;
      setQuerySeries((entries) => {
        let foundBenchmark = false;
        const updated = entries.flatMap((entry) => {
          if (entry.instanceId === instanceId) return [replaceMarketInstance(entry, result, { exactItems })];
          if (entry.benchmarkForInstanceId === instanceId) {
            if (!benchmark) return [];
            foundBenchmark = true;
            return [{ ...replaceMarketInstance(entry, benchmark), benchmarkForInstanceId: instanceId }];
          }
          return [entry];
        });
        if (benchmark && !foundBenchmark && !updated.some((entry) => entry.queryFingerprint === benchmark.queryFingerprint)) {
          updated.push({ ...attachMarketInstance(benchmark), benchmarkForInstanceId: instanceId });
        }
        return updated;
      });
      return "updated";
    } finally { pendingKeys.current.delete(requestedKey); }
  }, [querySeries]);
  const removeQuery = useCallback((key) => setQuerySeries((current) => current.filter((entry) => entry.key !== key)), []);
  // Clear Graph's bulk action. A distinct entry point from `removeQuery` so a
  // graph-wide clear is one state update, not N re-renders of one filter each.
  const clearAll = useCallback(() => setQuerySeries([]), []);
  return { querySeries, addQuery, updateQuery, removeQuery, clearAll };
}
