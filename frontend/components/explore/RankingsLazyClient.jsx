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

export default function RankingsLazyClient({
  targets,
  openingEconomics,
  loadError,
  rankingsMarketDate = null,
}) {
  const { canViewRankingsIntelligence, canViewCardChaseEfficiency } = useRankingsAccess();
  const [lens, setLens] = useState("overall");
  const [eraLens, setEraLens] = useState("rankings");
  const [setLens, setSetLens] = useState("rankings");
  const [selectedEra, setSelectedEra] = useState(null);
  const [eraState, setEraState] = useState({ status: "idle", contract: null, marketDate: rankingsMarketDate });

  useEffect(() => {
    if (lens !== "eras" || eraLens !== "rankings" || eraState.status !== "idle") return undefined;
    const controller = new AbortController();
    setEraState((current) => ({ ...current, status: "loading" }));
    fetch("/api/explore/rankings/lens?lens=eras", { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok && response.status !== 503) throw new Error(payload?.message || "Unable to load era rankings");
        return payload;
      })
      .then((payload) => {
        setEraState({
          status: payload?.status === "available" ? "ready" : "unavailable",
          contract: payload?.eraSetStrength || null,
          marketDate: payload?.marketDate || rankingsMarketDate,
        });
      })
      .catch((error) => {
        if (error.name !== "AbortError") setEraState({ status: "error", error: error.message, contract: null, marketDate: rankingsMarketDate });
      });
    return () => controller.abort();
  }, [lens, eraLens, eraState.status, rankingsMarketDate]);

  const changeLens = (next) => {
    setLens(next);
    if (next !== "sets") setSelectedEra(null);
    if (next === "eras") setEraLens("rankings");
    if (next === "sets") setSetLens("rankings");
  };

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
            const active = lens === "eras" ? eraLens : setLens;
            return (
              <button
                key={option.value}
                type="button"
                aria-pressed={active === option.value}
                onClick={() => lens === "eras" ? setEraLens(option.value) : setSetLens(option.value)}
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
                setSetLens("rankings");
                setLens("sets");
              }}
            />
          ) : eraState.status === "unavailable" || eraState.status === "error" ? (
            <section className={`${styles.surface} set-glass-surface p-5 text-sm text-[var(--text-secondary)]`}>Era rankings are temporarily unavailable.</section>
          ) : <LensSkeleton />
        ) : (
          <OpeningEconomicsEras
            economics={openingEconomics}
            canViewRankingsIntelligence={canViewRankingsIntelligence}
            onSelectEra={(era) => {
              setSelectedEra(era?.eraName || null);
              setSetLens("economics");
              setLens("sets");
            }}
          />
        )
      ) : lens === "sets" ? (
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
          {setLens === "economics" ? (
            <SetPackMetrics sets={openingEconomics?.sets} targets={targets} eraFilter={selectedEra} marketDate={openingEconomics?.marketDate} canViewRankingsIntelligence={canViewRankingsIntelligence} />
          ) : (
            <ExploreTableClient targets={targets} loadError={loadError} canViewProductRipIntelligence={canViewRankingsIntelligence} eraFilter={selectedEra} />
          )}
        </>
      ) : lens === "products" ? (
        <RankingsProductLensClient />
      ) : (
        <CardChaseEfficiencyRankings entitled={canViewCardChaseEfficiency} targets={targets} />
      )}
    </>
  );
}
