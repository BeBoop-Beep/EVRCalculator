"use client";

import Image from "next/image";
import { useId, useState } from "react";
import {
  Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import ChartFrame from "@/components/explore/ChartFrame";
import ChartTooltipShell from "@/components/explore/ChartTooltipShell";
import { getMinimalPlotMargin } from "@/components/explore/minimalChartAxis.mjs";
import {
  ACTIVE_DOT_STYLE, AREA_GRADIENT_BOTTOM_OPACITY, AREA_GRADIENT_TOP_OPACITY,
  GRID_STROKE, PRIMARY_GLOW_OPACITY, PRIMARY_LINE_COLOR, REFERENCE_STROKE,
} from "@/components/explore/chartVisualSystem.mjs";
import { money, ratioAsPercent } from "./openingEconomicsSelector.mjs";

function Dash() {
  return <span className="text-[var(--text-secondary)] opacity-60">—</span>;
}

function ordinal(value) {
  const mod100 = value % 100;
  if (mod100 >= 11 && mod100 <= 13) return `${value}TH`;
  return `${value}${value % 10 === 1 ? "ST" : value % 10 === 2 ? "ND" : value % 10 === 3 ? "RD" : "TH"}`;
}

function PercentileTooltip({ active, payload, lens }) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  const above = 100 - point.percentile;
  return <ChartTooltipShell data-opening-economics-tooltip>
    <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{ordinal(point.percentile)} PERCENTILE</p>
    <p className="mt-1 text-sm font-semibold tabular-nums text-[var(--text-primary)]">{lens === "return" ? `${ratioAsPercent(point.value)} retained` : `${money(point.value)} per pack equivalent`}</p>
    <p className="mt-1.5 text-[11px] leading-relaxed text-[var(--text-secondary)]">{point.percentile}% of modeled product-opening outcomes {lens === "return" ? "retain this much purchase value" : "finish at this value"} or less.</p>
    <p className="mt-1 text-[11px] text-[var(--text-secondary)]">{above}% finish above this {lens === "return" ? "level" : "value"}.</p>
  </ChartTooltipShell>;
}

function LandmarkLegend({ lens, scope }) {
  const rows = lens === "return"
    ? [["Recover Cost", 1, ratioAsPercent], ["Typical Retention", scope.typicalRetention, ratioAsPercent], ["Mean Outcome Retention", scope.meanOutcomeRetention, ratioAsPercent]]
    : [["Typical Opening", scope.typicalOpeningPerPack, money], ["Average Model Break-Even", scope.averageModelBreakEvenPerPack, money]];
  return <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-[var(--text-secondary)]" aria-label="Chart landmarks">
    {rows.map(([label, value, formatter], index) => <li key={label} className="inline-flex items-center gap-1.5"><span className="inline-block h-px w-3" style={{ backgroundColor: index === 0 ? PRIMARY_LINE_COLOR : REFERENCE_STROKE }} />{label} <strong className="font-medium tabular-nums text-[var(--text-primary)]">{formatter(value)}</strong></li>)}
  </ul>;
}

export default function OpeningEconomicsDistribution({ scope, targets = [] }) {
  const [lens, setLens] = useState("return");
  const chartId = useId().replaceAll(":", "");
  const distribution = lens === "return" ? scope.normalizedReturnPercentiles : scope.valuePerPackPercentiles;
  const formatter = lens === "return" ? ratioAsPercent : money;
  const points = Array.from({ length: 99 }, (_, index) => {
    const percentile = index + 1;
    const key = `p${String(percentile).padStart(2, "0")}`;
    return { percentile, value: Number(distribution?.[key]) };
  }).filter((point) => Number.isFinite(point.value) && point.value > 0);
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
  const gradientId = `opening-economics-area-${chartId}`;
  const glowId = `opening-economics-glow-${chartId}`;
  const evAboveP75 = Number(scope.averageModelBreakEvenPerPack) > Number(scope.valuePerPackPercentiles?.p75);

  return <section className="set-glass-surface overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 p-4 shadow-[0_18px_44px_rgba(0,0,0,0.24)] sm:p-5" data-opening-economics-distribution>
    <div className="grid grid-cols-2 gap-4 border-b border-[var(--border-subtle)] pb-4 lg:grid-cols-4" data-opening-headline-metrics>
      {metrics.map(([label, value, help]) => <div key={label}><p className="text-[10px] font-medium uppercase tracking-[0.08em] text-[var(--text-secondary)]" title={help}>{label}</p><p className="mt-1 text-2xl font-semibold tabular-nums text-[var(--text-primary)]">{value ?? <Dash />}</p><p className="mt-1 hidden text-[10px] leading-relaxed text-[var(--text-secondary)] sm:block">{help}</p></div>)}
    </div>

    <div className="grid grid-cols-3 gap-3 border-b border-[var(--border-subtle)] py-4" data-opening-value-snapshot>
      {valueSnapshot.map(([label, value, help]) => <div key={label} title={help}><p className="text-[9px] font-medium uppercase tracking-[0.08em] text-[var(--text-secondary)]">{label}</p><p className="mt-1 text-lg font-semibold tabular-nums text-[var(--text-primary)] sm:text-xl">{value ?? <Dash />}</p></div>)}
    </div>

    <div className="mt-5 flex flex-wrap items-end justify-between gap-3">
      <div><h3 className="text-base font-semibold text-[var(--text-primary)]">Opening Distribution</h3><p className="mt-1 text-xs text-[var(--text-secondary)]">Measured P01–P99 percentile curve across the weighted modeled product cohort.</p></div>
      <div className="flex rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/40 p-1"><button type="button" onClick={() => setLens("return")} aria-pressed={lens === "return"} className="rounded-md px-3 py-1.5 text-xs aria-pressed:bg-[rgba(45,212,191,0.14)] aria-pressed:text-[var(--text-primary)]">Return %</button><button type="button" onClick={() => setLens("value")} aria-pressed={lens === "value"} className="rounded-md px-3 py-1.5 text-xs aria-pressed:bg-[rgba(45,212,191,0.14)] aria-pressed:text-[var(--text-primary)]">Value / Pack</button></div>
    </div>

    <div className="mt-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/30 px-3 py-2.5" data-opening-how-to-read>
      <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">How to read this</p>
      <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">{lens === "return" ? "Move left to right from more common lower outcomes toward rarer higher outcomes. Each point shows the share of purchase cost retained at that percentile. The 100% line is full cost recovery." : "Each point shows modeled card value per pack equivalent at that percentile. The logarithmic value axis keeps the long right tail readable."}</p>
      <p className="mt-1 text-xs font-medium text-[var(--text-primary)]">{lens === "return" ? `Half of modeled openings retain ${ratioAsPercent(scope.typicalRetention)} of cost or less, and about ${ratioAsPercent(scope.chanceToRecoverCost)} recover their full purchase price.` : `The typical result is ${money(scope.typicalOpeningPerPack)} per pack equivalent compared with ${money(scope.averageModelBreakEvenPerPack)} in long-run modeled value.`}</p>
      {lens === "value" && evAboveP75 ? <p className="mt-1 text-xs text-[var(--text-secondary)]" data-ev-above-p75>The long-run modeled average sits above the 75th percentile. Higher-end outcomes pull the average above what most modeled openings experience.</p> : null}
    </div>

    {points.length === 99 ? <ChartFrame className="mt-4 h-[17rem] w-full sm:h-[21rem]" data-percentile-points="99">
      <ResponsiveContainer width="100%" height="100%"><ComposedChart data={points} margin={getMinimalPlotMargin({ top: 12, bottom: 8, rightExtra: 8 })}>
        <defs><linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={PRIMARY_LINE_COLOR} stopOpacity={AREA_GRADIENT_TOP_OPACITY} /><stop offset="100%" stopColor={PRIMARY_LINE_COLOR} stopOpacity={AREA_GRADIENT_BOTTOM_OPACITY} /></linearGradient><filter id={glowId} x="-10%" y="-16%" width="120%" height="132%"><feGaussianBlur stdDeviation="1.6" /></filter></defs>
        <CartesianGrid stroke={GRID_STROKE} strokeOpacity={0.28} strokeDasharray="2 8" vertical={false} />
        <XAxis dataKey="percentile" type="number" domain={[1, 99]} ticks={[1, 25, 50, 75, 99]} tickLine={false} axisLine={false} tickFormatter={(value) => `P${String(value).padStart(2, "0")}`} />
        <YAxis scale={lens === "value" ? "log" : "auto"} domain={lens === "value" ? ["auto", "auto"] : [0, "auto"]} tickLine={false} axisLine={false} tickFormatter={formatter} width={58} />
        <Tooltip content={<PercentileTooltip lens={lens} />} cursor={{ stroke: "rgba(255,255,255,0.16)", strokeWidth: 1 }} />
        {lens === "return" ? <><ReferenceLine y={1} stroke={PRIMARY_LINE_COLOR} strokeDasharray="6 6" /><ReferenceLine y={Number(scope.typicalRetention)} stroke={REFERENCE_STROKE} strokeDasharray="4 5" /><ReferenceLine y={Number(scope.meanOutcomeRetention)} stroke={REFERENCE_STROKE} strokeDasharray="2 6" /></> : <><ReferenceLine y={Number(scope.typicalOpeningPerPack)} stroke={REFERENCE_STROKE} strokeDasharray="4 5" /><ReferenceLine y={Number(scope.averageModelBreakEvenPerPack)} stroke={REFERENCE_STROKE} strokeDasharray="2 6" /></>}
        <Area type="linear" dataKey="value" stroke="none" fill={`url(#${gradientId})`} isAnimationActive={false} tooltipType="none" />
        <Line type="linear" dataKey="value" stroke={PRIMARY_LINE_COLOR} strokeWidth={7} strokeOpacity={PRIMARY_GLOW_OPACITY} filter={`url(#${glowId})`} dot={false} activeDot={false} isAnimationActive={false} tooltipType="none" />
        <Line type="linear" dataKey="value" stroke={PRIMARY_LINE_COLOR} strokeWidth={2.5} dot={false} activeDot={ACTIVE_DOT_STYLE} isAnimationActive={false} />
      </ComposedChart></ResponsiveContainer>
    </ChartFrame> : <p className="mt-5 text-sm text-[var(--text-secondary)]">The canonical P01–P99 percentile curve is unavailable.</p>}
    <LandmarkLegend lens={lens} scope={scope} />

    {identities.length ? <div className="mt-4 border-t border-[var(--border-subtle)] pt-3"><p className="text-[9px] font-medium uppercase tracking-[0.08em] text-[var(--text-secondary)]">Sets represented</p><div className="mt-2 flex h-11 gap-1.5 overflow-hidden opacity-65">{identities.map(({ target, image }) => <span key={target.set_id || target.target_id} title={target.name} className="flex min-w-0 flex-1 items-center justify-center">{image ? <Image src={image} width={48} height={30} alt="" className="h-7 w-full object-contain" /> : <i className="h-2.5 w-2.5 rotate-45 border border-[rgb(var(--ex-teal))]" />}</span>)}</div></div> : null}
  </section>;
}
