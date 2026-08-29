"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import SegmentedControl from "@/components/ui/SegmentedControl";
import { useRankingsAccess } from "@/lib/rankings/useRankingsAccess";
import { canonicalCardQueryKey, createRankingsSessionCache } from "@/lib/rankings/rankingsSessionCache.mjs";
import { markRankingsLens } from "@/lib/rankings/rankingsLensPerf.mjs";
import styles from "./explore.module.css";

const lensModules = {
  overall: () => import("./OpeningEconomicsOverall"),
  eraEconomics: () => import("./OpeningEconomicsEras"),
  eras: () => import("./EraRankings"),
  setEconomics: () => import("./SetPackMetrics"),
  sets: () => import("./ExploreTableClient"),
  cards: () => import("./CardChaseEfficiencyRankings"),
  products: () => import("./RankingsProductLensClient"),
};
const OpeningEconomicsOverall = dynamic(lensModules.overall, { loading: LensSkeleton });
const OpeningEconomicsEras = dynamic(lensModules.eraEconomics, { loading: LensSkeleton });
const EraRankings = dynamic(lensModules.eras, { loading: LensSkeleton });
const SetPackMetrics = dynamic(lensModules.setEconomics, { loading: LensSkeleton });
const ExploreTableClient = dynamic(lensModules.sets, { loading: LensSkeleton });
const CardChaseEfficiencyRankings = dynamic(lensModules.cards, { loading: LensSkeleton });
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

async function readLens(response, fallbackMessage) {
  const payload = await response.json();
  if (!response.ok && response.status !== 503) throw new Error(payload?.message || fallbackMessage);
  return payload;
}

export default function RankingsLazyClient({
  targets,
  openingEconomics,
  loadError,
  rankingsMarketDate = null,
}) {
  const { canViewRankingsIntelligence, canViewCardChaseEfficiency, authStatus, requestKey } = useRankingsAccess();
  const [lens, setActiveLens] = useState("overall");
  const [eraLens, setEraLens] = useState("rankings");
  const [setAnalysisLens, setSetAnalysisLens] = useState("rankings");
  const [selectedEra, setSelectedEra] = useState(null);
  const [eraState, setEraState] = useState({ status: "idle", contract: null, marketDate: rankingsMarketDate });
  const [setsState, setSetsState] = useState({ status: "idle", targets: [], marketDate: rankingsMarketDate });
  const publicationIdentity = rankingsMarketDate || "current";
  const sessionCache = useMemo(
    () => createRankingsSessionCache(`${requestKey}:${publicationIdentity}`),
    [requestKey, publicationIdentity],
  );
  const warmGeneration = useRef(0);

  const loadEra = useCallback(async ({ force = false, foreground = false } = {}) => {
    if (authStatus !== "resolved" || !canViewRankingsIntelligence) {
      const locked = { status: "locked", contract: null, marketDate: rankingsMarketDate, cacheIdentity: sessionCache.identity };
      if (foreground) setEraState(locked);
      return locked;
    }
    const cached = !force && sessionCache.peek("eras:rankings");
    if (cached) { setEraState(cached); return cached; }
    if (foreground) setEraState((current) => ({ ...current, status: "loading" }));
    markRankingsLens("eras", "request-start");
    try {
      const next = await sessionCache.request("eras:rankings", async () => {
        const payload = await fetch("/api/explore/rankings/lens?lens=eras", { cache: "no-store" })
          .then((response) => readLens(response, "Unable to load era rankings"));
        const value = {
          status: payload?.status === "locked" ? "locked" : payload?.status === "available" && Array.isArray(payload?.eraSetStrength?.eras) ? "ready" : "unavailable",
          contract: payload?.eraSetStrength || null,
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
      if (foreground) setEraState(failed);
      return failed;
    }
  }, [authStatus, canViewRankingsIntelligence, rankingsMarketDate, sessionCache]);

  const loadSets = useCallback(async ({ force = false, foreground = false } = {}) => {
    const cached = !force && sessionCache.peek("sets:rankings");
    if (cached) { setSetsState(cached); return cached; }
    if (foreground) setSetsState((current) => ({ ...current, status: "loading" }));
    markRankingsLens("sets", "request-start");
    try {
      const next = await sessionCache.request("sets:rankings", async () => {
        const payload = await fetch("/api/explore/rankings/lens?lens=sets", { cache: "no-store" })
          .then((response) => readLens(response, "Unable to load set rankings"));
        const value = { status: payload?.status === "available" && Array.isArray(payload?.targets) && payload.targets.length > 0 ? "ready" : "unavailable", targets: Array.isArray(payload?.targets) ? payload.targets : [], marketDate: payload?.marketDate || rankingsMarketDate, cacheIdentity: sessionCache.identity };
        if (value.status !== "ready") throw new Error("Set rankings are unavailable");
        return value;
      }, { force });
      setSetsState(next);
      markRankingsLens("sets", "response-received");
      return next;
    } catch (error) {
      const failed = { status: "error", error: error.message, targets: [], marketDate: rankingsMarketDate, cacheIdentity: sessionCache.identity };
      if (foreground) setSetsState(failed);
      return failed;
    }
  }, [rankingsMarketDate, sessionCache]);

  const warmProducts = useCallback(() => sessionCache.request("products:full_market", async () => {
    const [payload, model] = await Promise.all([
      fetch("/api/explore/rankings/lens?lens=products", { cache: "no-store" }).then((response) => readLens(response, "Unable to load product rankings")),
      import("./rankingsProductLensModel.mjs"),
    ]);
    if (payload?.status !== "available") throw new Error("Product rankings are unavailable");
    return { state: { status: "ready", productFamilyRankings: payload.productFamilyRankings || null, overallProductRankings: payload.overallProductRankings || null }, overallResult: model.normalizeOverallProductResult(payload.overallProductRankings) };
  }), [sessionCache]);

  const warmCards = useCallback(() => {
    if (!canViewCardChaseEfficiency) return Promise.resolve(null);
    const params = new URLSearchParams({ page: "1", page_size: "50", sort: "chase_efficiency", direction: "desc" });
    const key = canonicalCardQueryKey(params);
    return sessionCache.request(key, () => fetch(`/api/explore/card-chase-efficiency?${params}`, { cache: "no-store" }).then((response) => readLens(response, "Unable to load card rankings")));
  }, [canViewCardChaseEfficiency, sessionCache]);

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
      await idle(() => Promise.all([lensModules.eraEconomics(), lensModules.setEconomics()]));
      await idle(() => canViewRankingsIntelligence ? loadEra() : null);
      await idle(() => loadSets());
      await idle(() => warmProducts());
      await idle(() => canViewCardChaseEfficiency ? Promise.all([lensModules.cards(), warmCards()]) : null);
    })();
    return () => { warmGeneration.current += 1; };
  }, [authStatus, canViewRankingsIntelligence, canViewCardChaseEfficiency, loadEra, loadSets, warmCards, warmProducts]);

  const changeLens = (next) => {
    markRankingsLens(next, "selected");
    lensModules[next]?.().then(() => markRankingsLens(next, "module-ready"));
    if (next === "eras") loadEra({ foreground: true });
    if (next === "sets") loadSets({ foreground: true });
    if (next === "products") warmProducts().catch(() => null);
    if (next === "cards") warmCards().catch(() => null);
    setActiveLens(next);
    if (next !== "sets") setSelectedEra(null);
    if (next === "eras") setEraLens("rankings");
    if (next === "sets") setSetAnalysisLens("rankings");
  };

  const signalIntent = (next) => {
    lensModules[next]?.().then(() => markRankingsLens(next, "module-ready"));
    if (next === "eras") loadEra();
    if (next === "sets") loadSets();
    if (next === "products") warmProducts().catch(() => null);
    if (next === "cards" && canViewCardChaseEfficiency) warmCards().catch(() => null);
  };

  const visibleEraState = eraState.cacheIdentity === sessionCache.identity ? eraState : { status: "idle", contract: null, marketDate: rankingsMarketDate };
  const visibleSetsState = setsState.cacheIdentity === sessionCache.identity ? setsState : { status: "idle", targets: [], marketDate: rankingsMarketDate };
  const setTargets = visibleSetsState.status === "ready" ? visibleSetsState.targets : [];
  const setsUnavailable = visibleSetsState.status === "unavailable" || visibleSetsState.status === "error";

  return (
    <>
      <SegmentedControl
        className="mb-3 inline-block"
        ariaLabel="Ranking view"
        variant="primary"
        value={lens}
        onChange={changeLens}
        mobileScroll
        options={[
          { value: "overall", label: "Overall" },
          { value: "eras", label: "Eras", onIntent: () => signalIntent("eras") },
          { value: "sets", label: "Sets", onIntent: () => signalIntent("sets") },
          { value: "products", label: "Products", onIntent: () => signalIntent("products") },
          { value: "cards", label: "Cards", onIntent: () => signalIntent("cards") },
        ]}
      />

      {(lens === "eras" || lens === "sets") ? (
        <nav aria-label={`${lens === "eras" ? "Era" : "Set"} analysis`} className="mb-3 flex gap-2 overflow-x-auto pb-1" data-analysis-lens-tabs>
          {[{ value: "rankings", label: "Rankings" }, { value: "economics", label: "Pack Economics" }].map((option) => {
            const active = lens === "eras" ? eraLens : setAnalysisLens;
            return (
              <button
                key={option.value}
                type="button"
                aria-pressed={active === option.value}
                onClick={() => lens === "eras" ? setEraLens(option.value) : setSetAnalysisLens(option.value)}
                className={`${styles.productFamilyTab} ${active === option.value ? styles.productFamilyTabActive : ""}`}
              >
                {option.label}
              </button>
            );
          })}
        </nav>
      ) : null}

      {lens === "overall" ? (
        <OpeningEconomicsOverall economics={openingEconomics} targets={targets} />
      ) : lens === "eras" ? (
        eraLens === "rankings" ? (
          visibleEraState.status === "ready" ? (
            <EraRankings
              contract={visibleEraState.contract}
              marketDate={visibleEraState.marketDate}
              onSelectEra={(era) => {
                setSelectedEra(era?.eraName || null);
                setSetAnalysisLens("rankings");
                setActiveLens("sets");
              }}
            />
          ) : visibleEraState.status === "locked" ? (
            <section className={`${styles.surface} set-glass-surface p-5 text-sm text-[var(--text-secondary)]`}>Era Rankings are available with Index Plus or Premium.</section>
          ) : visibleEraState.status === "unavailable" || visibleEraState.status === "error" ? (
            <section className={`${styles.surface} set-glass-surface p-5 text-sm text-[var(--text-secondary)]`}>Era rankings are temporarily unavailable. <button type="button" className="ml-2 underline" onClick={() => loadEra({ force: true, foreground: true })}>Retry</button></section>
          ) : <LensSkeleton />
        ) : (
          <OpeningEconomicsEras
            economics={openingEconomics}
            canViewRankingsIntelligence={canViewRankingsIntelligence}
            onSelectEra={(era) => {
              setSelectedEra(era?.eraName || null);
              setSetAnalysisLens("economics");
              setActiveLens("sets");
            }}
          />
        )
      ) : lens === "sets" ? (
        visibleSetsState.status === "loading" || visibleSetsState.status === "idle" ? <LensSkeleton /> : setsUnavailable ? (
          <section className={`${styles.surface} set-glass-surface p-5 text-sm text-[var(--text-secondary)]`}>Set rankings are temporarily unavailable. <button type="button" className="ml-2 underline" onClick={() => loadSets({ force: true, foreground: true })}>Retry</button></section>
        ) : (
          <>
            {selectedEra ? (
              <div className="mb-3 flex flex-wrap items-center gap-2" data-era-filter-chip>
                <span className="text-xs text-[var(--text-secondary)]">Showing sets from</span>
                <span className="inline-flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2.5 py-1 text-xs font-medium text-[var(--text-primary)]">
                  {selectedEra}
                  <button type="button" onClick={() => setSelectedEra(null)} aria-label={`Clear the ${selectedEra} filter and show all sets`} className="text-[var(--text-secondary)] hover:text-[var(--text-primary)]">×</button>
                </span>
              </div>
            ) : null}
            {setAnalysisLens === "economics" ? (
              <SetPackMetrics sets={openingEconomics?.sets} targets={setTargets} eraFilter={selectedEra} marketDate={openingEconomics?.marketDate} canViewRankingsIntelligence={canViewRankingsIntelligence} />
            ) : (
              <ExploreTableClient targets={setTargets} loadError={loadError || setsUnavailable} canViewProductRipIntelligence={canViewRankingsIntelligence} eraFilter={selectedEra} />
            )}
          </>
        )
      ) : lens === "products" ? (
        <RankingsProductLensClient key={sessionCache.identity} sessionCache={sessionCache} />
      ) : (
        <CardChaseEfficiencyRankings key={sessionCache.identity} entitled={canViewCardChaseEfficiency} targets={targets} sessionCache={sessionCache} />
      )}
    </>
  );
}
