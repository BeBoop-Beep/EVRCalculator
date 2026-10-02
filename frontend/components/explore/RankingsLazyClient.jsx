"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import SegmentedControl from "@/components/ui/SegmentedControl";
import { useRankingsAccess } from "@/lib/rankings/useRankingsAccess";
import { createRankingsSessionCache } from "@/lib/rankings/rankingsSessionCache.mjs";
import { markRankingsLens } from "@/lib/rankings/rankingsLensPerf.mjs";
import { readRankingsScorecards, scorecardSetTarget } from "@/lib/rankings/rankingsScorecardsClient.mjs";
import { readPackEconomics } from "@/lib/rankings/packEconomicsClient.mjs";
import { readPublicRankingsHeadlines } from "@/lib/rankings/rankingsPublicClient.mjs";
import { defaultFinancialHistoryRequest } from "./financialRipHistoryModel.mjs";
import { planCohortPrefetch, prewarmFinancialHistory, readFinancialHistoryCached } from "@/lib/rankings/financialHistoryCache.mjs";
import { beginLastGoodRefresh, failLastGoodRefresh, isRenderableEraState, isRenderableSetState } from "@/lib/rankings/rankingsLastGoodState.mjs";
import { prewarmDefaultChase, prewarmDefaultCollector } from "@/lib/rankings/cardRankingsClient.mjs";
import { prewarmDefaultProduct, prewarmDefaultProductEconomics } from "@/lib/rankings/productRankingsClient.mjs";
import styles from "./explore.module.css";

const lensModules = {
  overall: () => import("./OpeningEconomicsOverall"),
  overviewHighlights: () => import("./RankingsOverviewHighlights"),
  eraEconomics: () => import("./OpeningEconomicsEras"),
  eras: () => import("./EraRankings"),
  sets: () => import("./SetRankingsHub"),
  cards: () => import("./CardRankingsHub"),
  products: () => import("./RankingsProductLensClient"),
};
const OpeningEconomicsOverall = dynamic(lensModules.overall, { loading: LensSkeleton });
const RankingsOverviewHighlights = dynamic(lensModules.overviewHighlights, { loading: () => null });
const OpeningEconomicsEras = dynamic(lensModules.eraEconomics, { loading: LensSkeleton });
const EraRankings = dynamic(lensModules.eras, { loading: LensSkeleton });
const SetRankingsHub = dynamic(lensModules.sets, { loading: LensSkeleton });
const CardRankingsHub = dynamic(lensModules.cards, { loading: LensSkeleton });
const RankingsProductLensClient = dynamic(lensModules.products, { loading: LensSkeleton });

function LensSkeleton() {
  return (
    <section aria-busy="true" className={`${styles.surface} set-glass-surface min-h-72 p-5`}>
      <div className="h-6 w-56 animate-pulse rounded bg-white/10" />
      <div className="mt-3 h-4 w-80 max-w-full animate-pulse rounded bg-white/[.07]" />
      <div className="mt-6 h-44 animate-pulse rounded-xl bg-white/[.045]" />
    </section>
  );
}

export default function RankingsLazyClient({
  targets,
  openingEconomics,
  rankingsMarketDate = null,
  rankingsOverview = null,
  financialCohort = null,
}) {
  const { canViewRankingsIntelligence, canViewFullMarketProductRankings, canViewCardChaseEfficiency, canViewCardCollectorAppeal, authStatus, requestKey } = useRankingsAccess();
  const [lens, setActiveLens] = useState("overall");
  const [eraLens, setEraLens] = useState("rankings");
  const [setEntryView, setSetEntryView] = useState("ripScore");
  const [selectedEra, setSelectedEra] = useState(null);
  const [eraState, setEraState] = useState({ status: "idle", contract: null, scorecards: null, marketDate: rankingsMarketDate });
  const [setsState, setSetsState] = useState({ status: "idle", targets: [], scorecards: null, marketDate: rankingsMarketDate });
  const publicationIdentity = rankingsMarketDate || "current";
  const sessionCache = useMemo(
    () => createRankingsSessionCache(`${requestKey}:${publicationIdentity}`),
    [requestKey, publicationIdentity],
  );
  const warmGeneration = useRef(0);

  const loadEra = useCallback(async ({ force = false, foreground = false } = {}) => {
    const cached = !force && sessionCache.peek("eras:rankings");
    if (cached) { setEraState(cached); return cached; }
    if (foreground) setEraState((current) => beginLastGoodRefresh(current, isRenderableEraState));
    markRankingsLens("eras", "request-start");
    try {
      const next = await sessionCache.request("eras:rankings", async () => {
        const payload = await readPublicRankingsHeadlines("era", { sessionCache, force });
        const rows = Array.isArray(payload?.rows) ? payload.rows : [];
        const value = {
          status: rows.length ? "ready" : "unavailable",
          contract: { eras: rows.map((row) => ({ eraId: row.entityId, eraName: row.name, canonicalKey: row.canonicalKey, modeledSetCount: row.modeledSetCount })) },
          scorecards: payload,
          marketDate: payload?.marketDate || rankingsMarketDate,
          cacheIdentity: sessionCache.identity,
        };
        if (value.status !== "ready") throw new Error("Era rankings are unavailable");
        return value;
      }, { force });
      setEraState(next);
      markRankingsLens("eras", "response-received");
      return next;
    } catch (error) {
      const failed = { status: "error", error: error.message, contract: null, marketDate: rankingsMarketDate, cacheIdentity: sessionCache.identity };
      if (foreground) setEraState((current) => failLastGoodRefresh(current, error, isRenderableEraState, failed));
      return failed;
    }
  }, [rankingsMarketDate, sessionCache]);

  const loadSets = useCallback(async ({ force = false, foreground = false } = {}) => {
    const cached = !force && sessionCache.peek("sets:rankings");
    if (cached) { setSetsState(cached); return cached; }
    if (foreground) setSetsState((current) => beginLastGoodRefresh(current, isRenderableSetState));
    markRankingsLens("sets", "request-start");
    try {
      const next = await sessionCache.request("sets:rankings", async () => {
        const payload = await readPublicRankingsHeadlines("set", { sessionCache, force });
        const rows = Array.isArray(payload?.rows) ? payload.rows : [];
        const targets = rows.map(scorecardSetTarget);
        const value = { status: targets.length > 0 ? "ready" : "unavailable", targets, scorecards: payload, marketDate: payload?.marketDate || rankingsMarketDate, cacheIdentity: sessionCache.identity };
        if (value.status !== "ready") throw new Error("Set rankings are unavailable");
        return value;
      }, { force });
      setSetsState(next);
      markRankingsLens("sets", "response-received");
      return next;
    } catch (error) {
      const failed = { status: "error", error: error.message, targets: [], marketDate: rankingsMarketDate, cacheIdentity: sessionCache.identity };
      if (foreground) setSetsState((current) => failLastGoodRefresh(current, error, isRenderableSetState, failed));
      return failed;
    }
  }, [rankingsMarketDate, sessionCache]);

  useEffect(() => {
    if (lens === "eras" && eraLens === "rankings") loadEra({ foreground: true });
  }, [lens, eraLens, loadEra]);
  useEffect(() => {
    if (lens === "sets") loadSets({ foreground: true });
  }, [lens, loadSets]);
  useEffect(() => {
    if (lens === "eras" && eraLens === "rankings" && eraState.status === "ready") requestAnimationFrame(() => markRankingsLens("eras", "render-ready"));
    if (lens === "sets" && setsState.status === "ready") requestAnimationFrame(() => markRankingsLens("sets", "render-ready"));
  }, [lens, eraLens, eraState.status, setsState.status]);

  useEffect(() => {
    if (authStatus !== "resolved") return undefined;
    if (typeof navigator !== "undefined" && navigator.connection?.saveData) return undefined;
    const generation = ++warmGeneration.current;
    const idle = (task) => new Promise((resolve) => {
      const run = () => { if (generation !== warmGeneration.current) return resolve(); Promise.resolve(task()).catch(() => null).finally(resolve); };
      if (typeof requestIdleCallback === "function") requestIdleCallback(run, { timeout: 1500 });
      else setTimeout(run, 180);
    });
    (async () => {
      // Era is the first non-default interaction. Its tiny prepared response
      // and rendering chunk warm together in the first safe idle slot so a
      // click never serially pays module + API latency.
      await idle(() => Promise.all([
        lensModules.eras(),
        lensModules.eraEconomics(),
        loadEra(),
        canViewRankingsIntelligence ? readRankingsScorecards("era", { sessionCache }) : null,
      ]));
      await idle(() => Promise.all([loadSets(), canViewRankingsIntelligence ? readRankingsScorecards("set", { sessionCache }) : null]));
      await idle(() => canViewRankingsIntelligence ? readPackEconomics({ sessionCache }) : null);
      await idle(async () => {
        await prewarmDefaultProduct({ sessionCache, canViewFullMarket: canViewFullMarketProductRankings });
        return prewarmDefaultProductEconomics({ sessionCache, canViewFullMarket: canViewFullMarketProductRankings });
      });
    })();
    return () => { warmGeneration.current += 1; };
  }, [authStatus, canViewFullMarketProductRankings, canViewRankingsIntelligence, loadEra, loadSets, sessionCache]);

  useEffect(() => {
    if (!(authStatus === "resolved" || authStatus === "degraded") || !canViewCardCollectorAppeal) return undefined;
    if (typeof navigator !== "undefined" && navigator.connection?.saveData) return undefined;
    let live = true;
    const run = () => {
      if (!live) return;
      markRankingsLens("cards", "prewarm-start");
      Promise.all([
        lensModules.cards(),
        prewarmDefaultCollector({ sessionCache, entitled: canViewCardCollectorAppeal, authStatus }),
      ]).then(() => {
        if (live) markRankingsLens("cards", "prewarm-ready");
        if (live && canViewCardChaseEfficiency) {
          const chase = () => prewarmDefaultChase({ sessionCache, entitled: true, authStatus });
          if (typeof requestIdleCallback === "function") requestIdleCallback(chase, { timeout: 2400 }); else setTimeout(chase, 300);
        }
      });
    };
    const handle = typeof requestIdleCallback === "function" ? requestIdleCallback(run, { timeout: 1800 }) : setTimeout(run, 220);
    return () => {
      live = false;
      if (typeof cancelIdleCallback === "function" && typeof requestIdleCallback === "function") cancelIdleCallback(handle);
      else clearTimeout(handle);
    };
  }, [authStatus, canViewCardChaseEfficiency, canViewCardCollectorAppeal, sessionCache]);

  // Default Financial RIP history: start the chart's own request (same session-cache key) as soon
  // as access, cohort identities and the publication date are known - before the chart mounts - and
  // only for entitled viewers.  The chart then consumes the in-flight/completed entry.  Once the
  // default view is usable, an optional idle prefetch of the whole <=22-Set cohort for the same
  // range makes later Set changes local; it is skipped under save-data.
  const historyMarketDate = rankingsOverview?.overallFinancialRip?.marketDate || rankingsOverview?.openingEconomics?.marketDate || openingEconomics?.marketDate || null;
  useEffect(() => {
    if (lens !== "overall" || !canViewRankingsIntelligence || !(authStatus === "resolved" || authStatus === "degraded")) return undefined;
    if (!Array.isArray(financialCohort?.eras) || !financialCohort.eras.length) return undefined;
    const plan = defaultFinancialHistoryRequest({ financialCohort, marketDate: historyMarketDate });
    if (!plan) return undefined;
    let live = true;
    let idleHandle = null;
    prewarmFinancialHistory(plan, { sessionCache, entitled: canViewRankingsIntelligence, authStatus }).then((payload) => {
      if (!live || !payload) return;
      const prefetch = planCohortPrefetch(plan, { entitled: canViewRankingsIntelligence, saveData: typeof navigator !== "undefined" && Boolean(navigator.connection?.saveData) });
      if (!prefetch) return;
      const run = () => { if (live) readFinancialHistoryCached(prefetch.entities, { sessionCache, startDate: prefetch.startDate, endDate: prefetch.endDate }).catch(() => null); };
      if (typeof requestIdleCallback === "function") idleHandle = requestIdleCallback(run, { timeout: 3000 });
      else idleHandle = setTimeout(run, 400);
    });
    return () => { live = false; if (idleHandle != null && typeof cancelIdleCallback === "function" && typeof requestIdleCallback === "function") cancelIdleCallback(idleHandle); };
  }, [lens, canViewRankingsIntelligence, authStatus, financialCohort, historyMarketDate, sessionCache]);

  const changeLens = (next) => {
    markRankingsLens(next, "selected");
    lensModules[next]?.().then(() => markRankingsLens(next, "module-ready"));
    if (next === "eras") loadEra({ foreground: true });
    if (next === "sets") { setSetEntryView("ripScore"); loadSets({ foreground: true }); }
    setActiveLens(next);
    if (next !== "sets") setSelectedEra(null);
    if (next === "eras") setEraLens("rankings");
  };

  const signalIntent = (next) => {
    lensModules[next]?.().then(() => markRankingsLens(next, "module-ready"));
    if (next === "eras") { loadEra(); if (canViewRankingsIntelligence) readRankingsScorecards("era", { sessionCache }).catch(() => null); }
    if (next === "sets") { loadSets(); if (canViewRankingsIntelligence) Promise.all([readRankingsScorecards("set", { sessionCache }), readPackEconomics({ sessionCache })]).catch(() => null); }
    if (next === "products" && (authStatus === "resolved" || authStatus === "degraded")) prewarmDefaultProduct({ sessionCache, canViewFullMarket: canViewFullMarketProductRankings }).catch(() => null);
    if (next === "cards" && (authStatus === "resolved" || authStatus === "degraded")) prewarmDefaultCollector({ sessionCache, entitled: canViewCardCollectorAppeal, authStatus }).catch(() => null);
  };

  const visibleEraState = eraState.cacheIdentity === sessionCache.identity ? eraState : { status: "idle", contract: null, marketDate: rankingsMarketDate };
  const visibleSetsState = setsState.cacheIdentity === sessionCache.identity ? setsState : { status: "idle", targets: [], marketDate: rankingsMarketDate };
  const setsUnavailable = visibleSetsState.status === "unavailable" || visibleSetsState.status === "error";

  return (
    <>
      <SegmentedControl
        className="mb-3 inline-block"
        ariaLabel="Ranking view"
        variant="rankingsPrimary"
        value={lens}
        onChange={changeLens}
        mobileScroll
        options={[
          { value: "overall", label: "Overview" },
          { value: "eras", label: "Eras", onIntent: () => signalIntent("eras") },
          { value: "sets", label: "Sets", onIntent: () => signalIntent("sets") },
          { value: "products", label: "Products", onIntent: () => signalIntent("products") },
          { value: "cards", label: "Cards", onIntent: () => signalIntent("cards") },
        ]}
      />

      {lens === "eras" ? (
        <nav aria-label="Era analysis" className="mb-3 flex gap-2 overflow-x-auto pb-1" data-analysis-lens-tabs>
          {[{ value: "rankings", label: "Era RIP Score" }, { value: "economics", label: "Pack Economics" }].map((option) => {
            const active = eraLens;
            return (
              <button
                key={option.value}
                type="button"
                aria-pressed={active === option.value}
                onClick={() => setEraLens(option.value)}
                className={`${styles.productFamilyTab} ${active === option.value ? styles.productFamilyTabActive : ""}`}
              >
                {option.label}
              </button>
            );
          })}
        </nav>
      ) : null}

      {lens === "overall" ? (
        <>
          <RankingsOverviewHighlights
            overview={rankingsOverview}
            onOpenTopSet={() => { setSetEntryView("ripScore"); setActiveLens("sets"); }}
            onOpenTopEra={() => { setEraLens("rankings"); setActiveLens("eras"); }}
            onOpenLowestCost={() => { setSetEntryView("packEconomics"); setActiveLens("sets"); }}
          />
          <OpeningEconomicsOverall economics={openingEconomics} overview={rankingsOverview} financialCohort={financialCohort} targets={targets} eras={visibleEraState.contract?.eras || []} sessionCache={sessionCache} />
        </>
      ) : lens === "eras" ? (
        eraLens === "rankings" ? (
          visibleEraState.status === "ready" ? (
            <EraRankings
              key={sessionCache.identity}
              scorecards={visibleEraState.scorecards}
              sessionCache={sessionCache}
              canViewRankingsIntelligence={canViewRankingsIntelligence}
                  onSelectEra={(era) => {
                    setSelectedEra(era?.eraName || null);
                    setSetEntryView("ripScore");
                    setActiveLens("sets");
              }}
            />
          ) : visibleEraState.status === "unavailable" || visibleEraState.status === "error" ? (
            <section className={`${styles.surface} set-glass-surface p-5 text-sm text-[var(--text-secondary)]`}>Era rankings are temporarily unavailable. <button type="button" className="ml-2 underline" onClick={() => loadEra({ force: true, foreground: true })}>Retry</button></section>
          ) : <LensSkeleton />
        ) : (
          <OpeningEconomicsEras
            economics={openingEconomics}
            canViewRankingsIntelligence={canViewRankingsIntelligence}
                onSelectEra={(era) => {
                  setSelectedEra(era?.eraName || null);
                  setSetEntryView("ripScore");
                  setActiveLens("sets");
            }}
          />
        )
      ) : lens === "sets" ? (
        visibleSetsState.status === "loading" || visibleSetsState.status === "idle" ? <LensSkeleton /> : setsUnavailable ? (
          <section className={`${styles.surface} set-glass-surface p-5 text-sm text-[var(--text-secondary)]`}>Set rankings are temporarily unavailable. <button type="button" className="ml-2 underline" onClick={() => loadSets({ force: true, foreground: true })}>Retry</button></section>
        ) : (
              <SetRankingsHub key={`${sessionCache.identity}:${setEntryView}`} initialView={setEntryView} publicScorecards={visibleSetsState.scorecards} sessionCache={sessionCache} canViewRankingsIntelligence={canViewRankingsIntelligence} eraFilter={selectedEra} onClearEraFilter={() => setSelectedEra(null)} />
        )
      ) : lens === "products" ? (
        <RankingsProductLensClient key={sessionCache.identity} sessionCache={sessionCache} />
      ) : (
        <CardRankingsHub key={sessionCache.identity} canViewCollectorAppeal={canViewCardCollectorAppeal} canViewChaseEfficiency={canViewCardChaseEfficiency} authStatus={authStatus} sessionCache={sessionCache} />
      )}
    </>
  );
}
