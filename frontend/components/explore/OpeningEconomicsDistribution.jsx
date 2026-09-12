"use client";

import Image from "next/image";
import { Area, Bar, BarChart, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
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

function PercentileTooltip({ active, payload }) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return <ChartTooltipShell data-opening-economics-percentile-tooltip><p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">P{String(point.percentile).padStart(2, "0")}</p><p className="mt-1 text-sm font-semibold tabular-nums text-[var(--text-primary)]">{ratioAsPercent(point.value)} recovery</p><p className="mt-1.5 text-[11px] leading-relaxed text-[var(--text-secondary)]">{point.percentile}% of modeled opening outcomes recover this share of purchase cost or less.</p></ChartTooltipShell>;
}

export function readExactRecoveryBuckets(scope) {
  const required = [["0_10", 0, 0.1], ["10_25", 0.1, 0.25], ["25_50", 0.25, 0.5], ["50_75", 0.5, 0.75], ["75_100", 0.75, 1], ["100_plus", 1, null]];
  const rows = Array.isArray(scope?.normalizedReturnBuckets) ? scope.normalizedReturnBuckets.map((bucket) => ({ ...bucket, probability: finiteNumber(bucket?.probability) })) : [];
  const valid = rows.length === required.length && rows.every((row, index) => row.key === required[index][0] && row.label && finiteNumber(row.lowerBound) === required[index][1] && finiteNumber(row.upperBound) === required[index][2] && row.probability !== null && row.probability >= 0 && row.probability <= 1);
  return valid && Math.abs(rows.reduce((sum, row) => sum + row.probability, 0) - 1) <= 1e-9 ? rows : [];
}

export function readLegacyReturnPercentiles(scope) {
  const distribution = scope?.normalizedReturnPercentiles;
  const points = Array.from({ length: 99 }, (_, index) => { const percentile = index + 1; const key = `p${String(percentile).padStart(2, "0")}`; return { percentile, value: finiteNumber(distribution?.[key]) }; });
  return points.every((point) => point.value !== null && point.value >= 0) ? points : [];
}

export default function OpeningEconomicsDistribution({ scope, targets = [] }) {
  const buckets = readExactRecoveryBuckets(scope);
  const percentilePoints = buckets.length ? [] : readLegacyReturnPercentiles(scope);
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
    <div className="mt-5"><h3 className="text-base font-semibold text-[var(--text-primary)]">{buckets.length ? "How openings usually turn out" : percentilePoints.length ? "Opening outcome range" : "How openings usually turn out"}</h3><p className="mt-1 text-xs text-[var(--text-secondary)]">{buckets.length ? "Share of modeled openings by purchase-cost recovery." : percentilePoints.length ? "Modeled purchase-cost recovery across the opening distribution." : "Share of modeled openings by purchase-cost recovery."}</p></div>
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
    </> : percentilePoints.length === 99 ? <>
      <ChartFrame className="mt-4 h-[17rem] w-full sm:h-[21rem]" data-legacy-percentile-points="99"><ResponsiveContainer width="100%" height="100%"><ComposedChart data={percentilePoints} margin={getMinimalPlotMargin({ top: 12, bottom: 8, rightExtra: 8 })}><CartesianGrid stroke={GRID_STROKE} strokeOpacity={0.28} strokeDasharray="2 8" vertical={false} /><XAxis dataKey="percentile" type="number" domain={[1, 99]} ticks={[1, 25, 50, 75, 99]} tickLine={false} axisLine={false} tickFormatter={(value) => `P${String(value).padStart(2, "0")}`} /><YAxis domain={[0, "auto"]} tickLine={false} axisLine={false} tickFormatter={ratioAsPercent} width={52} /><Tooltip content={<PercentileTooltip />} cursor={{ stroke: "rgba(255,255,255,0.16)", strokeWidth: 1 }} /><ReferenceLine y={1} stroke={PRIMARY_LINE_COLOR} strokeDasharray="6 6" /><Area type="linear" dataKey="value" stroke="none" fill={PRIMARY_LINE_COLOR} fillOpacity={0.12} isAnimationActive={false} /><Line type="linear" dataKey="value" stroke={PRIMARY_LINE_COLOR} strokeWidth={2.5} dot={false} isAnimationActive={false} /></ComposedChart></ResponsiveContainer></ChartFrame>
      <p className="mt-3 text-xs leading-relaxed text-[var(--text-secondary)]">Move left to right from more common lower outcomes toward rarer higher outcomes. Each point is a published percentile position; it is not a frequency bucket.</p>
    </> : <p className="mt-5 text-sm text-[var(--text-secondary)]">The modeled recovery distribution is unavailable.</p>}
    {identities.length ? <div className="mt-4 border-t border-[var(--border-subtle)] pt-3"><p className="text-[9px] font-medium uppercase tracking-[0.08em] text-[var(--text-secondary)]">Sets represented</p><div className="mt-2 flex h-11 gap-1.5 overflow-hidden opacity-65">{identities.map(({ target, image }) => <span key={target.set_id || target.target_id} title={target.name} className="flex min-w-0 flex-1 items-center justify-center">{image ? <Image src={image} width={48} height={30} alt="" className="h-7 w-full object-contain" /> : <i className="h-2.5 w-2.5 rotate-45 border border-[rgb(var(--ex-teal))]" />}</span>)}</div></div> : null}
  </section>;
}
