"use client";

import { useEffect, useMemo, useState } from "react";
import PullRatesTab from "@/components/pokemon/set-page/PullRates/PullRatesTab";
import { getPokemonSetPullRates } from "@/lib/pokemon/pokemonSetPullRatesClient";

const CACHE_LIMIT = 12;
const successfulPullRates = new Map();
const pendingPullRates = new Map();

function remember(setId, payload) {
  successfulPullRates.delete(setId);
  successfulPullRates.set(setId, payload);
  while (successfulPullRates.size > CACHE_LIMIT) successfulPullRates.delete(successfulPullRates.keys().next().value);
}

function requestPullRates(setId, force) {
  if (!force && successfulPullRates.has(setId)) return Promise.resolve(successfulPullRates.get(setId));
  if (!force && pendingPullRates.has(setId)) return pendingPullRates.get(setId);
  const request = getPokemonSetPullRates(setId).then((payload) => {
    remember(setId, payload);
    return payload;
  }).finally(() => pendingPullRates.delete(setId));
  pendingPullRates.set(setId, request);
  return request;
}

export default function PullRatesSetTab({ setId, initialData = null }) {
  const validInitial = initialData?.set?.id === setId ? initialData : null;
  const cached = successfulPullRates.get(setId) || validInitial;
  const [retryNonce, setRetryNonce] = useState(0);
  const [timedOut, setTimedOut] = useState(false);
  const [state, setState] = useState(() => ({ status: cached ? "success" : "idle", setId, payload: cached, error: null }));

  useEffect(() => {
    if (!setId) return;
    let cancelled = false;
    const staleGood = successfulPullRates.get(setId) || (state.setId === setId ? state.payload : null);
    setTimedOut(false);
    setState({ status: staleGood ? "refreshing" : "loading", setId, payload: staleGood, error: null });
    const timer = window.setTimeout(() => { if (!cancelled) setTimedOut(true); }, 8000);
    requestPullRates(setId, retryNonce > 0).then((payload) => {
      if (!cancelled) setState({ status: "success", setId, payload, error: null });
    }).catch((error) => {
      if (!cancelled) setState({ status: "error", setId, payload: staleGood, error: error?.message || "Unable to load pull rates." });
    }).finally(() => window.clearTimeout(timer));
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [setId, retryNonce]);

  const active = state.setId === setId ? state : { status: "loading", setId, payload: null, error: null };
  const assumptions = active.payload?.pullRateAssumptions || null;
  const renderState = useMemo(() => ({ ...active, error: active.error }), [active]);
  return (
    <div className="space-y-3">
      <PullRatesTab pullRateAssumptions={assumptions} pullRatesTabPending={!assumptions && ["idle", "loading", "refreshing"].includes(active.status)} pullRatesPendingTimedOut={timedOut} activePullRatesState={renderState} resolvedSetResourceId={setId} />
      {active.status === "error" ? <button type="button" onClick={() => setRetryNonce((value) => value + 1)} className="rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm font-semibold">Retry pull rates</button> : null}
    </div>
  );
}
