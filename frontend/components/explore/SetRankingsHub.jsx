"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";
import PlanLock from "@/components/membership/PlanLock";
import { INDEX_PLAN_PLUS } from "@/lib/access/indexPlanAccess.mjs";
import { readPackEconomics } from "@/lib/rankings/packEconomicsClient.mjs";
import { beginLastGoodRefresh, failLastGoodRefresh } from "@/lib/rankings/rankingsLastGoodState.mjs";
import styles from "./explore.module.css";
import { findSetRankingView, SET_RANKING_VIEWS } from "./setRankingViews.mjs";

const SetRipScoreLeaderboard = dynamic(() => import("./SetRipScoreLeaderboard"));
const SetPackMetrics = dynamic(() => import("./SetPackMetrics"));
const SetMetricRankingsTable = dynamic(() => import("./SetMetricRankingsTable"));

const isRenderablePackEconomics = (state) => state?.status === "ready" && Array.isArray(state?.contract?.sets) && state.contract.sets.length > 0;

export default function SetRankingsHub({ scorecards = null, sessionCache = null, canViewRankingsIntelligence = false, eraFilter = null, onClearEraFilter, initialView = "ripScore" }) {
  const [view, setView] = useState(initialView);
  const [packState, setPackState] = useState({ status: "idle", contract: null });
  const selectedView = findSetRankingView(view);
  const locked = Boolean(selectedView.requiredPlan && !canViewRankingsIntelligence);
  const loadPackEconomics = useCallback(async ({ force = false } = {}) => {
    if (!canViewRankingsIntelligence) return null;
    setPackState((current) => beginLastGoodRefresh(current, isRenderablePackEconomics));
    try {
      const contract = await readPackEconomics({ sessionCache, force });
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
  useEffect(() => { if (view === "packEconomics" && canViewRankingsIntelligence && packState.status === "idle") loadPackEconomics(); }, [canViewRankingsIntelligence, loadPackEconomics, packState.status, view]);
  return (
    <div data-set-rankings-hub data-default-view="ripScore">
      <nav aria-label="Set ranking view" className="mb-3 flex gap-2 overflow-x-auto pb-1" data-set-ranking-tabs>
        {SET_RANKING_VIEWS.map((option) => <button key={option.value} type="button" aria-pressed={view === option.value} onClick={() => setView(option.value)} className={`${styles.productFamilyTab} shrink-0 whitespace-nowrap ${view === option.value ? styles.productFamilyTabActive : ""}`}>{option.requiredPlan && !canViewRankingsIntelligence ? <span aria-hidden="true" className="mr-1">🔒</span> : null}{option.label}</button>)}
      </nav>
      {eraFilter ? <div className="mb-3 flex flex-wrap items-center gap-2" data-era-filter-chip><span className="text-xs text-[var(--text-secondary)]">Showing sets from</span><span className="inline-flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2.5 py-1 text-xs font-medium text-[var(--text-primary)]">{eraFilter}<button type="button" onClick={onClearEraFilter} aria-label={`Clear the ${eraFilter} filter and show all sets`} className="text-[var(--text-secondary)] hover:text-[var(--text-primary)]">×</button></span></div> : null}
      {locked ? <PlanLock requiredPlan={INDEX_PLAN_PLUS} source={`rankings-set-${view}`} description={`${selectedView.label} rankings are available with Index Plus.`} /> : view === "ripScore" ? <SetRipScoreLeaderboard scorecards={scorecards} eraFilter={eraFilter} /> : view === "packEconomics" ? packState.status === "idle" || packState.status === "loading" ? <section aria-busy="true" className={`${styles.surface} min-h-64 p-5`}><div className="h-5 w-52 animate-pulse rounded bg-white/10" /><div className="mt-5 h-40 animate-pulse rounded-xl bg-white/[.045]" /></section> : packState.status === "error" ? <section className={`${styles.surface} p-5 text-sm text-[var(--text-secondary)]`}>Pack Economics are temporarily unavailable. <button type="button" className="ml-2 underline" onClick={() => loadPackEconomics({ force: true })}>Retry</button></section> : <><SetPackMetrics contract={packState.contract} eraFilter={eraFilter} />{packState.refreshError ? <p role="status" className="mt-2 text-xs text-[var(--text-secondary)]">Refresh failed; showing the last available Pack Economics.</p> : null}</> : <SetMetricRankingsTable kind={view} scorecards={scorecards} eraFilter={eraFilter} />}
    </div>
  );
}
