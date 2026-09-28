"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import SegmentedControl from "@/components/ui/SegmentedControl";
import { useRankingsAccess } from "@/lib/rankings/useRankingsAccess";
import { createRankingsSessionCache } from "@/lib/rankings/rankingsSessionCache.mjs";
import { markRankingsLens } from "@/lib/rankings/rankingsLensPerf.mjs";
import { readCurrentBenchmark } from "@/lib/rankings/ripBenchmarkClient.mjs";
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

async function readLens(response, fallbackMessage) {
  const payload = await response.json();
  if (!response.ok && response.status !== 503) throw new Error(payload?.message || fallbackMessage);
  return payload;
}

export default function RankingsLazyClient({
  targets,
  openingEconomics,
  rankingsMarketDate = null,
}) {
  const { canViewRankingsIntelligence, canViewCardChaseEfficiency, canViewCardCollectorAppeal, authStatus, requestKey } = useRankingsAccess();
  const [lens, setActiveLens] = useState("overall");
  const [eraLens, setEraLens] = useState("rankings");
  const [setEntryView, setSetEntryView] = useState("ripScore");
  const [selectedEra, setSelectedEra] = useState(null);
  const [eraState, setEraState] = useState({ status: "idle", contract: null, benchmark: null, marketDate: rankingsMarketDate });
  const [setsState, setSetsState] = useState({ status: "idle", targets: [], benchmark: null, marketDate: rankingsMarketDate });
  const publicationIdentity = rankingsMarketDate || "current";
  const sessionCache = useMemo(
    () => createRankingsSessionCache(`${requestKey}:${publicationIdentity}`),
    [requestKey, publicationIdentity],
  );
  const warmGeneration = useRef(0);

  const loadEra = useCallback(async ({ force = false, foreground = false } = {}) => {
    const cached = !force && sessionCache.peek("eras:rankings");
    if (cached) { setEraState(cached); return cached; }
    if (foreground) setEraState((current) => ({ ...current, status: "loading" }));
    markRankingsLens("eras", "request-start");
    try {
      const next = await sessionCache.request("eras:rankings", async () => {
        const payload = await fetch("/api/explore/rankings/lens?lens=eras", { cache: "no-store" })
          .then((response) => readLens(response, "Unable to load era rankings"));
        const entities = (payload?.eraSetStrength?.eras || []).map((era) => ({ entity_type: "era", entity_id: era.eraId })).filter((entity) => entity.entity_id);
        let benchmark = null;
        try { benchmark = await readCurrentBenchmark(entities, { sessionCache }); }
        catch (error) { if (error.status === 401 || error.status === 403) return { status: "locked", contract: payload?.eraSetStrength || null, benchmark: null, marketDate: payload?.marketDate || rankingsMarketDate, cacheIdentity: sessionCache.identity }; throw error; }
        const value = {
          status: payload?.status === "locked" ? "locked" : payload?.status === "available" && Array.isArray(payload?.eraSetStrength?.eras) ? "ready" : "unavailable",
          contract: payload?.eraSetStrength || null,
          benchmark,
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
      if (foreground) setEraState((current) => ({ ...current, status: "error", error: error.message, cacheIdentity: sessionCache.identity }));
      return failed;
    }
  }, [rankingsMarketDate, sessionCache]);

  const loadSets = useCallback(async ({ force = false, foreground = false } = {}) => {
    const cached = !force && sessionCache.peek("sets:rankings");
    if (cached) { setSetsState(cached); return cached; }
    if (foreground) setSetsState((current) => ({ ...current, status: "loading" }));
    markRankingsLens("sets", "request-start");
    try {
      const next = await sessionCache.request("sets:rankings", async () => {
        const payload = await fetch("/api/explore/rankings/lens?lens=sets", { cache: "no-store" })
          .then((response) => readLens(response, "Unable to load set rankings"));
        const targets = Array.isArray(payload?.targets) ? payload.targets : [];
        const entities = targets.map((target) => ({ entity_type: "set", entity_id: target?.target_id || target?.setId || target?.id })).filter((entity) => entity.entity_id);
        let benchmark = null;
        try { benchmark = await readCurrentBenchmark(entities, { sessionCache }); }
        catch (error) { if (error.status === 401 || error.status === 403) return { status: "locked", targets, benchmark: null, marketDate: payload?.marketDate || rankingsMarketDate, cacheIdentity: sessionCache.identity }; throw error; }
        const value = { status: payload?.status === "available" && targets.length > 0 ? "ready" : "unavailable", targets, benchmark, marketDate: payload?.marketDate || rankingsMarketDate, cacheIdentity: sessionCache.identity };
        if (value.status !== "ready") throw new Error("Set rankings are unavailable");
        return value;
      }, { force });
      setSetsState(next);
      markRankingsLens("sets", "response-received");
      return next;
    } catch (error) {
      const failed = { status: "error", error: error.message, targets: [], marketDate: rankingsMarketDate, cacheIdentity: sessionCache.identity };
      if (foreground) setSetsState((current) => ({ ...current, status: "error", error: error.message, cacheIdentity: sessionCache.identity }));
      return failed;
    }
  }, [rankingsMarketDate, sessionCache]);

  const warmProducts = useCallback(() => sessionCache.request("products:full_market", async () => {
    const [payload, overallPayload, model] = await Promise.all([
      fetch("/api/explore/rankings/lens?lens=products", { cache: "no-store" }).then((response) => readLens(response, "Unable to load product rankings")),
      fetch("/api/explore/product-rankings/overall?budget=full_market", { cache: "no-store" }).then((response) => readLens(response, "Unable to load Full Market product rankings")),
      import("./rankingsProductLensModel.mjs"),
    ]);
    if (payload?.status !== "available") throw new Error("Product rankings are unavailable");
    return { state: { status: "ready", productFamilyRankings: payload.productFamilyRankings || null }, overallResult: model.normalizeOverallProductResult(overallPayload) };
  }), [sessionCache]);

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
      ]));
      await idle(() => loadSets());
    })();
    return () => { warmGeneration.current += 1; };
  }, [authStatus, canViewRankingsIntelligence, loadEra, loadSets]);

  const changeLens = (next) => {
    markRankingsLens(next, "selected");
    lensModules[next]?.().then(() => markRankingsLens(next, "module-ready"));
    if (next === "eras") loadEra({ foreground: true });
    if (next === "sets") { setSetEntryView("ripScore"); loadSets({ foreground: true }); }
    if (next === "products") warmProducts().catch(() => null);
    setActiveLens(next);
    if (next !== "sets") setSelectedEra(null);
    if (next === "eras") setEraLens("rankings");
  };

  const signalIntent = (next) => {
    lensModules[next]?.().then(() => markRankingsLens(next, "module-ready"));
    if (next === "eras") loadEra();
    if (next === "sets") loadSets();
    if (next === "products") warmProducts().catch(() => null);
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
            openingEconomics={openingEconomics}
            onOpenTopSet={() => { setSetEntryView("ripScore"); setActiveLens("sets"); }}
            onOpenTopEra={() => { setEraLens("rankings"); setActiveLens("eras"); }}
            onOpenLowestCost={() => { setSetEntryView("packEconomics"); setActiveLens("sets"); }}
          />
          <OpeningEconomicsOverall economics={openingEconomics} targets={setTargets} eras={visibleEraState.contract?.eras || []} benchmark={visibleSetsState.benchmark} />
        </>
      ) : lens === "eras" ? (
        eraLens === "rankings" ? (
          visibleEraState.status === "ready" ? (
            <EraRankings
              contract={visibleEraState.contract}
              benchmark={visibleEraState.benchmark}
              marketDate={visibleEraState.benchmark?.freshness?.benchmarkMarketDate || visibleEraState.marketDate}
                  onSelectEra={(era) => {
                    setSelectedEra(era?.eraName || null);
                    setSetEntryView("ripScore");
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
                  setSetEntryView("ripScore");
                  setActiveLens("sets");
            }}
          />
        )
      ) : lens === "sets" ? (
        visibleSetsState.status === "loading" || visibleSetsState.status === "idle" ? <LensSkeleton /> : visibleSetsState.status === "locked" ? (
          <section className={`${styles.surface} set-glass-surface p-5 text-sm text-[var(--text-secondary)]`}>Benchmark Set Rankings are available with Index Plus or Premium.</section>
        ) : setsUnavailable ? (
          <section className={`${styles.surface} set-glass-surface p-5 text-sm text-[var(--text-secondary)]`}>Set rankings are temporarily unavailable. <button type="button" className="ml-2 underline" onClick={() => loadSets({ force: true, foreground: true })}>Retry</button></section>
        ) : (
              <SetRankingsHub key={`${sessionCache.identity}:${setEntryView}`} initialView={setEntryView} targets={setTargets} benchmark={visibleSetsState.benchmark} openingEconomics={openingEconomics} canViewRankingsIntelligence={canViewRankingsIntelligence} eraFilter={selectedEra} onClearEraFilter={() => setSelectedEra(null)} marketDate={visibleSetsState.benchmark?.freshness?.benchmarkMarketDate || visibleSetsState.marketDate} />
        )
      ) : lens === "products" ? (
        <RankingsProductLensClient key={sessionCache.identity} sessionCache={sessionCache} />
      ) : (
        <CardRankingsHub key={sessionCache.identity} canViewCollectorAppeal={canViewCardCollectorAppeal} canViewChaseEfficiency={canViewCardChaseEfficiency} authStatus={authStatus} targets={targets} sessionCache={sessionCache} />
      )}
    </>
  );
}
