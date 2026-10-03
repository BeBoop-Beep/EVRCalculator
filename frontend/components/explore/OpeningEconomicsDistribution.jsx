"use client";
import FinancialRipHistoryChart from "./FinancialRipHistoryChart";
import InfoPopover from "@/components/ui/InfoPopover";
import { money, ratioAsPercent } from "./openingEconomicsSelector.mjs";
const Dash = () => <span className="text-[var(--text-secondary)] opacity-60">—</span>;
export default function OpeningEconomicsDistribution({ scope, overview, financialCohort, targets = [], openingSets = [], eras = [], marketDate = null, sessionCache = null }) {
  const published = overview?.openingEconomics || {};
  const metrics = [
    ["Overall Expected Value / Pack", money(published.overallExpectedValuePerPack ?? scope.averageModelBreakEvenPerPack)],
    ["Average Pack Cost / Pack", money(published.averagePackCostPerPack ?? scope.averageCostPerPack)],
    ["Modeled Return", ratioAsPercent(published.modeledReturnOnSpend), "Expected modeled card value divided by the average modeled pack-equivalent purchase cost."],
    ["Chance to Recover Cost", ratioAsPercent(published.chanceToRecoverCost ?? scope.chanceToRecoverCost)],
    ["Entertainment Cost / Pack", money(published.entertainmentCostPerPack ?? scope.averageEntertainmentCostPerPack)],
  ];
  const financial = overview?.overallFinancialRip?.displayValue;
  return <section data-opening-economics-distribution>
    <div className="set-glass-surface overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 p-4 sm:p-5" data-opening-summary-context>
      <div className="border-b border-[var(--border-subtle)] pb-4">
        <p className="inline-flex items-center gap-1 text-[10px] font-medium uppercase tracking-[0.08em] text-[var(--text-secondary)]">Overall Financial RIP <InfoPopover text="Absolute Pokémon-wide Financial RIP reference for the certified publication." /></p>
        <p className="mt-1 text-3xl font-semibold tabular-nums">{Number.isFinite(Number(financial)) ? Number(financial).toFixed(2) : <Dash />}</p>
        <p className="mt-1 text-xs text-[var(--text-secondary)]">Pokémon Overall benchmark reference</p>
      </div>
      <div className="grid grid-cols-2 gap-4 py-4 lg:grid-cols-5">
      {metrics.map(([label, value, tooltip]) => <div key={label}><p className="inline-flex items-center gap-1 text-[10px] font-medium uppercase tracking-[0.08em] text-[var(--text-secondary)]">{label}{tooltip ? <InfoPopover text={tooltip} /> : null}</p><p className="mt-1 text-2xl font-semibold tabular-nums">{value ?? <Dash />}</p></div>)}
      </div>
      <div className="flex flex-wrap gap-x-2 gap-y-1 border-t border-[var(--border-subtle)] pt-3 text-xs text-[var(--text-secondary)]" data-opening-summary-metadata>
        <span>{scope.setCount} modeled sets</span><span aria-hidden="true">·</span><span>{scope.productFamilyCount} represented product families</span><span aria-hidden="true">·</span><span>{scope.productSkuCount} modeled products</span>{marketDate ? <><span aria-hidden="true">·</span><span>Opening data as of {marketDate}</span></> : null}
      </div>
    </div>
    <div className="set-glass-surface mt-4 overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 p-4 sm:p-5">
      <FinancialRipHistoryChart key={sessionCache?.identity || "no-session"} sessionCache={sessionCache} targets={targets} financialCohort={financialCohort} openingSets={openingSets} eras={eras} marketDate={overview?.overallFinancialRip?.marketDate || marketDate} />
    </div>
  </section>;
}
