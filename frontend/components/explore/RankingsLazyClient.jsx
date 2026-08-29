"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import SegmentedControl from "@/components/ui/SegmentedControl";
import { useRankingsAccess } from "@/lib/rankings/useRankingsAccess";
import styles from "./explore.module.css";

const OpeningEconomicsOverall = dynamic(() => import("./OpeningEconomicsOverall"), { loading: LensSkeleton });
const OpeningEconomicsEras = dynamic(() => import("./OpeningEconomicsEras"), { loading: LensSkeleton });
const EraRankings = dynamic(() => import("./EraRankings"), { loading: LensSkeleton });
const SetPackMetrics = dynamic(() => import("./SetPackMetrics"), { loading: LensSkeleton });
const ExploreTableClient = dynamic(() => import("./ExploreTableClient"), { loading: LensSkeleton });
const CardChaseEfficiencyRankings = dynamic(() => import("./CardChaseEfficiencyRankings"), { loading: LensSkeleton });
const RankingsProductLensClient = dynamic(() => import("./RankingsProductLensClient"), { loading: LensSkeleton });

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
  const { canViewRankingsIntelligence, canViewCardChaseEfficiency } = useRankingsAccess();
  const [lens, setActiveLens] = useState("overall");
  const [eraLens, setEraLens] = useState("rankings");
  const [setAnalysisLens, setSetAnalysisLens] = useState("rankings");
  const [selectedEra, setSelectedEra] = useState(null);
  const [eraState, setEraState] = useState({ status: "idle", contract: null, marketDate: rankingsMarketDate });
  const [setsState, setSetsState] = useState({ status: "idle", targets: [], marketDate: rankingsMarketDate });
  const [eraRetry, setEraRetry] = useState(0);
  const [setsRetry, setSetsRetry] = useState(0);

  useEffect(() => {
    if (lens !== "eras" || eraLens !== "rankings") return undefined;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort("timeout"), 12000);
    setEraState({ status: "loading", contract: null, marketDate: rankingsMarketDate });
    fetch("/api/explore/rankings/lens?lens=eras", { cache: "no-store", signal: controller.signal })
      .then((response) => readLens(response, "Unable to load era rankings"))
      .then((payload) => {
        setEraState({
          status: payload?.status === "available" && Array.isArray(payload?.eraSetStrength?.eras) ? "ready" : "unavailable",
          contract: payload?.eraSetStrength || null,
          marketDate: payload?.marketDate || rankingsMarketDate,
        });
      })
      .catch((error) => {
        setEraState({ status: error.name === "AbortError" ? "unavailable" : "error", error: error.message, contract: null, marketDate: rankingsMarketDate });
      });
    return () => { clearTimeout(timeout); controller.abort(); };
  }, [lens, eraLens, rankingsMarketDate, canViewRankingsIntelligence, eraRetry]);

  useEffect(() => {
    if (lens !== "sets") return undefined;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort("timeout"), 12000);
    setSetsState({ status: "loading", targets: [], marketDate: rankingsMarketDate });
    fetch("/api/explore/rankings/lens?lens=sets", { cache: "no-store", signal: controller.signal })
      .then((response) => readLens(response, "Unable to load set rankings"))
      .then((payload) => {
        setSetsState({
          status: payload?.status === "available" && Array.isArray(payload?.targets) && payload.targets.length > 0 ? "ready" : "unavailable",
          targets: Array.isArray(payload?.targets) ? payload.targets : [],
          marketDate: payload?.marketDate || rankingsMarketDate,
        });
      })
      .catch((error) => {
        setSetsState({ status: error.name === "AbortError" ? "unavailable" : "error", error: error.message, targets: [], marketDate: rankingsMarketDate });
      });
    return () => { clearTimeout(timeout); controller.abort(); };
  }, [lens, rankingsMarketDate, canViewRankingsIntelligence, setsRetry]);

  const changeLens = (next) => {
    setActiveLens(next);
    if (next !== "sets") setSelectedEra(null);
    if (next === "eras") setEraLens("rankings");
    if (next === "sets") setSetAnalysisLens("rankings");
  };

  const setTargets = setsState.status === "ready" ? setsState.targets : [];
  const setsUnavailable = setsState.status === "unavailable" || setsState.status === "error";

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
          { value: "eras", label: "Eras" },
          { value: "sets", label: "Sets" },
          { value: "products", label: "Products" },
          { value: "cards", label: "Cards" },
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
          eraState.status === "ready" ? (
            <EraRankings
              contract={eraState.contract}
              marketDate={eraState.marketDate}
              onSelectEra={(era) => {
                setSelectedEra(era?.eraName || null);
                setSetAnalysisLens("rankings");
                setActiveLens("sets");
              }}
            />
          ) : eraState.status === "unavailable" || eraState.status === "error" ? (
            <section className={`${styles.surface} set-glass-surface p-5 text-sm text-[var(--text-secondary)]`}>Era rankings are temporarily unavailable. <button type="button" className="ml-2 underline" onClick={() => setEraRetry((value) => value + 1)}>Retry</button></section>
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
        setsState.status === "loading" || setsState.status === "idle" ? <LensSkeleton /> : setsUnavailable ? (
          <section className={`${styles.surface} set-glass-surface p-5 text-sm text-[var(--text-secondary)]`}>Set rankings are temporarily unavailable. <button type="button" className="ml-2 underline" onClick={() => setSetsRetry((value) => value + 1)}>Retry</button></section>
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
        <RankingsProductLensClient />
      ) : (
        <CardChaseEfficiencyRankings entitled={canViewCardChaseEfficiency} targets={targets} />
      )}
    </>
  );
}
