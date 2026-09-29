"use client";
import FinancialRipHistoryChart from "./FinancialRipHistoryChart";
import { money, ratioAsPercent } from "./openingEconomicsSelector.mjs";
const Dash = () => <span className="text-[var(--text-secondary)] opacity-60">—</span>;
export default function OpeningEconomicsDistribution({ scope, overview, financialCohort, targets = [], openingSets = [], eras = [], marketDate = null }) {
  const published = overview?.openingEconomics || {};
  const metrics = [
    ["Overall Expected Value / Pack", money(published.overallExpectedValuePerPack ?? scope.averageModelBreakEvenPerPack)],
    ["Average Pack Cost / Pack", money(published.averagePackCostPerPack ?? scope.averageCostPerPack)],
    ["Chance to Recover Cost", ratioAsPercent(published.chanceToRecoverCost ?? scope.chanceToRecoverCost)],
    ["Entertainment Cost / Pack", money(published.entertainmentCostPerPack ?? scope.averageEntertainmentCostPerPack)],
  ];
  return <section className="set-glass-surface overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 p-4 sm:p-5" data-opening-economics-distribution>
    <div className="grid grid-cols-2 gap-4 border-b border-[var(--border-subtle)] pb-4 lg:grid-cols-4">
      {metrics.map(([label, value]) => <div key={label}><p className="text-[10px] font-medium uppercase tracking-[0.08em] text-[var(--text-secondary)]">{label}</p><p className="mt-1 text-2xl font-semibold tabular-nums">{value ?? <Dash />}</p></div>)}
    </div>
    <FinancialRipHistoryChart targets={targets} financialCohort={financialCohort} openingSets={openingSets} eras={eras} marketDate={overview?.overallFinancialRip?.marketDate || marketDate} />
  </section>;
}
