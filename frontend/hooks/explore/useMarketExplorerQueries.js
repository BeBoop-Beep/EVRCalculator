"use client";

import { useCallback, useState } from "react";
import { queryResultToSeries, resolveBenchmarkSpec } from "@/lib/explore/marketExplorerQuery.mjs";

async function executeQuery(spec) {
  const response = await fetch("/api/market/explorer/query", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(spec),
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
  return { querySeries, addQuery, removeQuery };
}
