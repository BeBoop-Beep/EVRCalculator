"use client";

import Image from "next/image";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import ChartFrame from "@/components/explore/ChartFrame";
import ChartTooltipShell from "@/components/explore/ChartTooltipShell";
import { getMinimalPlotMargin } from "@/components/explore/minimalChartAxis.mjs";
import { GRID_STROKE, PRIMARY_LINE_COLOR } from "@/components/explore/chartVisualSystem.mjs";
import { money, ratioAsPercent } from "./openingEconomicsSelector.mjs";

function Dash() { return <span className="text-[var(--text-secondary)] opacity-60">—</span>; }

function finiteNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function DistributionTooltip({ active, payload }) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return <ChartTooltipShell data-opening-economics-tooltip>
    <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{point.label} recovery</p>
    <p className="mt-1 text-sm font-semibold tabular-nums text-[var(--text-primary)]">{ratioAsPercent(point.probability)} of openings</p>
    <p className="mt-1.5 text-[11px] leading-relaxed text-[var(--text-secondary)]">Share of modeled openings whose gross card value falls in this purchase-cost recovery range.</p>
  </ChartTooltipShell>;
}

export default function OpeningEconomicsDistribution({ scope, targets = [] }) {
  const buckets = Array.isArray(scope.normalizedReturnBuckets) ? scope.normalizedReturnBuckets
    .map((bucket) => ({ ...bucket, probability: finiteNumber(bucket?.probability) }))
    .filter((bucket) => bucket.key && bucket.label && bucket.probability !== null) : [];
  const metrics = [
    ["Modeled Return on Spend", ratioAsPercent(scope.modeledReturnOnSpend), "Weighted aggregate EV divided by weighted aggregate cost."],
    ["Typical Retention", ratioAsPercent(scope.typicalRetention), "Median of the weighted normalized-return distribution."],
    ["Chance to Recover Cost", ratioAsPercent(scope.chanceToRecoverCost), "Share of modeled outcomes meeting or exceeding purchase cost."],
    ["Entertainment Cost / Pack", money(scope.averageEntertainmentCostPerPack), "Modeled purchase cost not returned as gross card value."],
  ];
  const valueSnapshot = [
    ["Average Cost / Pack", money(scope.averageCostPerPack), "Representative per-pack-equivalent purchase cost across the modeled sealed product cohort."],
    ["Average Model Break-Even / Pack", money(scope.averageModelBreakEvenPerPack), "Long-run modeled gross card value per pack equivalent."],
    ["Typical Opening / Pack", money(scope.typicalOpeningPerPack), "The weighted median modeled opening result."],
  ];
  const identities = targets.map((target) => ({ target, image: target.logo_image_url || target.symbol_image_url }));

  return <section className="set-glass-surface overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 p-4 shadow-[0_18px_44px_rgba(0,0,0,0.24)] sm:p-5" data-opening-economics-distribution>
    <div className="grid grid-cols-2 gap-4 border-b border-[var(--border-subtle)] pb-4 lg:grid-cols-4" data-opening-headline-metrics>
      {metrics.map(([label, value, help]) => <div key={label}><p className="text-[10px] font-medium uppercase tracking-[0.08em] text-[var(--text-secondary)]" title={help}>{label}</p><p className="mt-1 text-2xl font-semibold tabular-nums text-[var(--text-primary)]">{value ?? <Dash />}</p><p className="mt-1 hidden text-[10px] leading-relaxed text-[var(--text-secondary)] sm:block">{help}</p></div>)}
    </div>
    <div className="grid grid-cols-3 gap-3 border-b border-[var(--border-subtle)] py-4" data-opening-value-snapshot>
      {valueSnapshot.map(([label, value, help]) => <div key={label} title={help}><p className="text-[9px] font-medium uppercase tracking-[0.08em] text-[var(--text-secondary)]">{label}</p><p className="mt-1 text-lg font-semibold tabular-nums text-[var(--text-primary)] sm:text-xl">{value ?? <Dash />}</p></div>)}
    </div>
    <div className="mt-5"><h3 className="text-base font-semibold text-[var(--text-primary)]">How openings usually turn out</h3><p className="mt-1 text-xs text-[var(--text-secondary)]">Share of modeled openings by purchase-cost recovery.</p></div>
    {buckets.length === 6 ? <>
      <ChartFrame className="mt-4 h-[17rem] w-full sm:h-[21rem]" data-recovery-buckets="6">
        <ResponsiveContainer width="100%" height="100%"><BarChart data={buckets} margin={getMinimalPlotMargin({ top: 18, bottom: 8, rightExtra: 8 })}>
          <CartesianGrid stroke={GRID_STROKE} strokeOpacity={0.28} strokeDasharray="2 8" vertical={false} />
          <XAxis dataKey="label" interval={0} tickLine={false} axisLine={false} tick={{ fontSize: 10 }} />
          <YAxis domain={[0, "auto"]} tickLine={false} axisLine={false} tickFormatter={ratioAsPercent} width={46} />
          <Tooltip content={<DistributionTooltip />} cursor={{ fill: "rgba(255,255,255,0.035)" }} />
          <Bar dataKey="probability" fill={PRIMARY_LINE_COLOR} radius={[5, 5, 0, 0]} isAnimationActive={false} />
        </BarChart></ResponsiveContainer>
      </ChartFrame>
      <ul className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-6" aria-label="Opening recovery distribution">
        {buckets.map((bucket) => <li key={bucket.key} className="rounded-md border border-[var(--border-subtle)] px-2 py-2 text-center"><span className="block text-[10px] text-[var(--text-secondary)]">{bucket.label}</span><strong className="mt-0.5 block text-xs tabular-nums text-[var(--text-primary)]">{ratioAsPercent(bucket.probability)}</strong></li>)}
      </ul>
    </> : <p className="mt-5 text-sm text-[var(--text-secondary)]">The modeled recovery distribution is unavailable.</p>}
    {identities.length ? <div className="mt-4 border-t border-[var(--border-subtle)] pt-3"><p className="text-[9px] font-medium uppercase tracking-[0.08em] text-[var(--text-secondary)]">Sets represented</p><div className="mt-2 flex h-11 gap-1.5 overflow-hidden opacity-65">{identities.map(({ target, image }) => <span key={target.set_id || target.target_id} title={target.name} className="flex min-w-0 flex-1 items-center justify-center">{image ? <Image src={image} width={48} height={30} alt="" className="h-7 w-full object-contain" /> : <i className="h-2.5 w-2.5 rotate-45 border border-[rgb(var(--ex-teal))]" />}</span>)}</div></div> : null}
  </section>;
}
