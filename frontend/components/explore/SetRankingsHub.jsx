"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import PlanLock from "@/components/membership/PlanLock";
import { INDEX_PLAN_PLUS } from "@/lib/access/indexPlanAccess.mjs";
import styles from "./explore.module.css";
import { findSetRankingView, SET_RANKING_VIEWS } from "./setRankingViews.mjs";

const SetRipScoreLeaderboard = dynamic(() => import("./SetRipScoreLeaderboard"));
const SetPackMetrics = dynamic(() => import("./SetPackMetrics"));
const ExploreTableClient = dynamic(() => import("./ExploreTableClient"));
const SetMetricRankingsTable = dynamic(() => import("./SetMetricRankingsTable"));

export default function SetRankingsHub({ targets = [], openingEconomics, loadError = false, canViewRankingsIntelligence = false, eraFilter = null, onClearEraFilter, marketDate = null, initialView = "ripScore" }) {
  const [view, setView] = useState(initialView);
  const selectedView = findSetRankingView(view);
  const locked = Boolean(selectedView.requiredPlan && !canViewRankingsIntelligence);
  return (
    <div data-set-rankings-hub data-default-view="ripScore">
      <nav aria-label="Set ranking view" className="mb-3 flex gap-2 overflow-x-auto pb-1" data-set-ranking-tabs>
        {SET_RANKING_VIEWS.map((option) => <button key={option.value} type="button" aria-pressed={view === option.value} onClick={() => setView(option.value)} className={`${styles.productFamilyTab} shrink-0 whitespace-nowrap ${view === option.value ? styles.productFamilyTabActive : ""}`}>{option.requiredPlan && !canViewRankingsIntelligence ? <span aria-hidden="true" className="mr-1">🔒</span> : null}{option.label}</button>)}
      </nav>
      {eraFilter ? <div className="mb-3 flex flex-wrap items-center gap-2" data-era-filter-chip><span className="text-xs text-[var(--text-secondary)]">Showing sets from</span><span className="inline-flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2.5 py-1 text-xs font-medium text-[var(--text-primary)]">{eraFilter}<button type="button" onClick={onClearEraFilter} aria-label={`Clear the ${eraFilter} filter and show all sets`} className="text-[var(--text-secondary)] hover:text-[var(--text-primary)]">×</button></span></div> : null}
      {locked ? <PlanLock requiredPlan={INDEX_PLAN_PLUS} source={`rankings-set-${view}`} description={`${selectedView.label} rankings are available with Index Plus.`} /> : view === "ripScore" ? <SetRipScoreLeaderboard targets={targets} eraFilter={eraFilter} marketDate={marketDate} /> : view === "packEconomics" ? <SetPackMetrics sets={openingEconomics?.sets} targets={targets} eraFilter={eraFilter} marketDate={openingEconomics?.marketDate} canViewRankingsIntelligence={canViewRankingsIntelligence} /> : view === "compareMetrics" ? <ExploreTableClient targets={targets} loadError={loadError} canViewProductRipIntelligence eraFilter={eraFilter} marketDate={marketDate} /> : <SetMetricRankingsTable kind={view} targets={targets} eraFilter={eraFilter} marketDate={marketDate} />}
    </div>
  );
}
