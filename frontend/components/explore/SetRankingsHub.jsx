"use client";

import { useCallback, useEffect, useState } from "react";
import { readPackEconomics } from "@/lib/rankings/packEconomicsClient.mjs";
import { readPublicPackEconomicsPreview } from "@/lib/rankings/rankingsPublicClient.mjs";
import { beginLastGoodRefresh, failLastGoodRefresh } from "@/lib/rankings/rankingsLastGoodState.mjs";
import styles from "./explore.module.css";
import { SET_RANKING_VIEWS } from "./setRankingViews.mjs";
import SetRipScoreLeaderboard from "./SetRipScoreLeaderboard";
import SetPackMetrics from "./SetPackMetrics";

const isRenderablePackEconomics = (state) => state?.status === "ready" && Array.isArray(state?.contract?.sets) && state.contract.sets.length > 0;

export default function SetRankingsHub({ publicScorecards = null, sessionCache = null, canViewRankingsIntelligence = false, eraFilter = null, onClearEraFilter, initialView = "ripScore" }) {
  const [view, setView] = useState(initialView);
  const [packState, setPackState] = useState(() => {
    const contract = sessionCache?.peek("sets:pack-economics");
    return contract?.status === "available" ? { status: "ready", contract } : { status: "idle", contract: null };
  });
  const loadPackEconomics = useCallback(async ({ force = false } = {}) => {
    const cached = !force && sessionCache?.peek("sets:pack-economics");
    if (cached?.status === "available") {
      setPackState({ status: "ready", contract: cached });
      return cached;
    }
    setPackState((current) => beginLastGoodRefresh(current, isRenderablePackEconomics));
    try {
      const contract = canViewRankingsIntelligence
        ? await readPackEconomics({ sessionCache, force })
        : await readPublicPackEconomicsPreview({ sessionCache, force });
      if (contract?.status !== "available" || !Array.isArray(contract?.sets) || !contract.sets.length) throw new Error("Pack Economics are unavailable");
      const next = { status: "ready", contract, refreshing: false, refreshError: null };
      setPackState(next);
      return next;
    } catch (error) {
      const failed = { status: "error", contract: null, error: error.message };
      setPackState((current) => failLastGoodRefresh(current, error, isRenderablePackEconomics, failed));
      return failed;
    }
  }, [canViewRankingsIntelligence, sessionCache]);
  useEffect(() => { if (view === "packEconomics" && packState.status === "idle") loadPackEconomics(); }, [loadPackEconomics, packState.status, view]);
  useEffect(() => {
    if (!canViewRankingsIntelligence || packState.status !== "idle") return undefined;
    let live = true;
    const run = () => { if (live) loadPackEconomics(); };
    const handle = typeof requestIdleCallback === "function" ? requestIdleCallback(run, { timeout: 1800 }) : setTimeout(run, 240);
    return () => { live = false; if (typeof cancelIdleCallback === "function" && typeof requestIdleCallback === "function") cancelIdleCallback(handle); else clearTimeout(handle); };
  }, [canViewRankingsIntelligence, loadPackEconomics, packState.status]);
  useEffect(() => { if (!canViewRankingsIntelligence) setPackState({ status: "idle", contract: null }); }, [canViewRankingsIntelligence]);
  return (
    <div data-set-rankings-hub data-default-view="ripScore">
      <nav aria-label="Set ranking view" className="mb-3 flex gap-2 overflow-x-auto pb-1" data-set-ranking-tabs>
        {SET_RANKING_VIEWS.map((option) => <button key={option.value} type="button" aria-pressed={view === option.value} onPointerEnter={() => option.value === "packEconomics" && loadPackEconomics()} onFocus={() => option.value === "packEconomics" && loadPackEconomics()} onPointerDown={() => option.value === "packEconomics" && loadPackEconomics()} onClick={() => setView(option.value)} className={`${styles.productFamilyTab} shrink-0 whitespace-nowrap ${view === option.value ? styles.productFamilyTabActive : ""}`}>{option.label}</button>)}
      </nav>
      {eraFilter ? <div className="mb-3 flex flex-wrap items-center gap-2" data-era-filter-chip><span className="text-xs text-[var(--text-secondary)]">Showing sets from</span><span className="inline-flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2.5 py-1 text-xs font-medium text-[var(--text-primary)]">{eraFilter}<button type="button" onClick={onClearEraFilter} aria-label={`Clear the ${eraFilter} filter and show all sets`} className="text-[var(--text-secondary)] hover:text-[var(--text-primary)]">×</button></span></div> : null}
      {view === "ripScore" ? <SetRipScoreLeaderboard scorecards={publicScorecards} eraFilter={eraFilter} sessionCache={sessionCache} canViewRankingsIntelligence={canViewRankingsIntelligence} /> : view === "packEconomics" ? packState.status === "idle" || packState.status === "loading" ? <section aria-busy="true" className={`${styles.surface} min-h-64 p-5`}><div className="h-5 w-52 animate-pulse rounded bg-white/10" /><div className="mt-5 h-40 animate-pulse rounded-xl bg-white/[.045]" /></section> : packState.status === "error" ? <section className={`${styles.surface} p-5 text-sm text-[var(--text-secondary)]`}>Pack Economics are temporarily unavailable. <button type="button" className="ml-2 underline" onClick={() => loadPackEconomics({ force: true })}>Retry</button></section> : <><SetPackMetrics contract={packState.contract} eraFilter={eraFilter} entitled={canViewRankingsIntelligence} />{packState.refreshError ? <p role="status" className="mt-2 text-xs text-[var(--text-secondary)]">Refresh failed; showing the last available Pack Economics.</p> : null}</> : null}
    </div>
  );
}
