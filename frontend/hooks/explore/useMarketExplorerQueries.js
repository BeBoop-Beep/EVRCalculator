"use client";

import { useCallback, useState } from "react";
import { buildQueryKey, queryResultToSeries, resolveBenchmarkSpec } from "@/lib/explore/marketExplorerQuery.mjs";

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
    if (response.status === 401 || response.status === 403) {
      throw new Error("Sign in to build a custom market.");
    }
    throw new Error(payload?.message || payload?.detail || "Unable to execute this market query");
  }
  const series = queryResultToSeries(payload);
  if (!series) throw new Error("The query response did not contain a market series");
  return series;
}

export default function useMarketExplorerQueries() {
  const [querySeries, setQuerySeries] = useState([]);
  const addQuery = useCallback(async (spec) => {
    const requestedKey = buildQueryKey(spec);
    if (querySeries.some((entry) => entry.spec && buildQueryKey(entry.spec) === requestedKey)) return "duplicate";
    const result = await executeQuery(spec);
    if (querySeries.some((entry) => entry.queryFingerprint === result.queryFingerprint)) return "duplicate";
    const benchmarkSpec = resolveBenchmarkSpec(spec);
    const benchmark = benchmarkSpec ? await executeQuery(benchmarkSpec) : null;
    setQuerySeries((current) => {
      const additions = [benchmark, result].filter(Boolean);
      return [...current, ...additions.filter((entry) => !current.some((existing) => existing.queryFingerprint === entry.queryFingerprint))];
    });
    return "added";
  }, [querySeries]);
  const removeQuery = useCallback((key) => setQuerySeries((current) => current.filter((entry) => entry.key !== key)), []);
  // Clear Graph's bulk action. A distinct entry point from `removeQuery` so a
  // graph-wide clear is one state update, not N re-renders of one filter each.
  const clearAll = useCallback(() => setQuerySeries([]), []);
  return { querySeries, addQuery, removeQuery, clearAll };
}
