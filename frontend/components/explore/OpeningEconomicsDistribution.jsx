"use client";

import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import ChartFrame from "@/components/explore/ChartFrame";
import ChartTooltipShell from "@/components/explore/ChartTooltipShell";
import { getMinimalPlotMargin } from "@/components/explore/minimalChartAxis.mjs";
import { GRID_STROKE, PRIMARY_LINE_COLOR } from "@/components/explore/chartVisualSystem.mjs";
import { money, ratioAsPercent } from "./openingEconomicsSelector.mjs";
import { readSetRipLandscape } from "./setRipLandscapeSelector.mjs";

function Dash() { return <span className="text-[var(--text-secondary)] opacity-60">—</span>; }

function LandscapePoint({ cx, cy, payload }) {
  if (!Number.isFinite(cx) || !Number.isFinite(cy)) return null;
  return <g transform={`translate(${cx},${cy})`} aria-hidden="true"><circle r="11" fill="rgba(7,14,25,0.9)" stroke={PRIMARY_LINE_COLOR} strokeWidth="1.5" />{payload?.logo ? <image href={payload.logo} x="-9" y="-7" width="18" height="14" preserveAspectRatio="xMidYMid meet" /> : <circle r="3" fill={PRIMARY_LINE_COLOR} />}</g>;
}

function LandscapeTooltip({ active, payload }) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return <ChartTooltipShell data-set-rip-landscape-tooltip><p className="text-sm font-semibold text-[var(--text-primary)]">{point.name}</p><p className="mt-1 text-xs tabular-nums text-[var(--text-secondary)]">Rank #{point.rank} · Set RIP {point.score.toFixed(1)} / 10 · {point.tier ? `${point.tier} Tier` : "Tier unavailable"}</p></ChartTooltipShell>;
}

function SetRipLandscape({ targets }) {
  const points = readSetRipLandscape(targets);
  return <div className="mt-5" data-set-rip-landscape><h3 className="text-base font-semibold text-[var(--text-primary)]">How Sets Rank to Open</h3><p className="mt-1 text-xs text-[var(--text-secondary)]">Every modeled set, ordered by Set RIP rank. Higher on the chart means a stronger Set RIP Score across supported opening formats.</p>{points.length ? <><ChartFrame className="mt-4 h-[18rem] w-full sm:h-[22rem]"><ResponsiveContainer width="100%" height="100%"><ScatterChart margin={getMinimalPlotMargin({ top: 18, bottom: 8, rightExtra: 10 })}><CartesianGrid stroke={GRID_STROKE} strokeOpacity={0.28} strokeDasharray="2 8" /><XAxis type="number" dataKey="rank" domain={[1, points.length]} allowDecimals={false} tickLine={false} axisLine={false} name="Set RIP rank" tickFormatter={(rank) => `#${rank}`} /><YAxis type="number" dataKey="score" domain={[0, 10]} ticks={[0, 2, 4, 6, 8, 10]} tickLine={false} axisLine={false} width={30} name="Set RIP Score" /><Tooltip content={<LandscapeTooltip />} cursor={{ stroke: "rgba(255,255,255,0.14)", strokeDasharray: "3 5" }} /><Scatter data={points} shape={<LandscapePoint />} isAnimationActive={false} /></ScatterChart></ResponsiveContainer></ChartFrame><ol className="sr-only" aria-label="Set RIP landscape values">{points.map((point) => <li key={`${point.rank}:${point.name}`}>#{point.rank} {point.name}: Set RIP {point.score.toFixed(1)} out of 10, {point.tier ? `${point.tier} Tier` : "tier unavailable"}</li>)}</ol></> : <p className="mt-5 text-sm text-[var(--text-secondary)]">Set RIP rankings are loading.</p>}</div>;
}

export default function OpeningEconomicsDistribution({ scope, targets = [] }) {
  const metrics = [["Modeled Return on Spend", ratioAsPercent(scope.modeledReturnOnSpend), "Weighted aggregate EV divided by weighted aggregate cost."], ["Typical Retention", ratioAsPercent(scope.typicalRetention), "Median of the weighted normalized-return distribution."], ["Chance to Recover Cost", ratioAsPercent(scope.chanceToRecoverCost), "Share of modeled outcomes meeting or exceeding purchase cost."], ["Entertainment Cost / Pack", money(scope.averageEntertainmentCostPerPack), "Modeled purchase cost not returned as gross card value."]];
  const valueSnapshot = [["Average Cost / Pack", money(scope.averageCostPerPack), "Representative per-pack-equivalent purchase cost across the modeled sealed product cohort."], ["Expected Value / Pack", money(scope.averageModelBreakEvenPerPack), "Long-run modeled gross card value per pack equivalent."], ["Typical Opening / Pack", money(scope.typicalOpeningPerPack), "The weighted median modeled opening result."]];
  return <section className="set-glass-surface overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 p-4 shadow-[0_18px_44px_rgba(0,0,0,0.24)] sm:p-5" data-opening-economics-distribution><div className="grid grid-cols-2 gap-4 border-b border-[var(--border-subtle)] pb-4 lg:grid-cols-4" data-opening-headline-metrics>{metrics.map(([label, value, help]) => <div key={label}><p className="text-[10px] font-medium uppercase tracking-[0.08em] text-[var(--text-secondary)]" title={help}>{label}</p><p className="mt-1 text-2xl font-semibold tabular-nums text-[var(--text-primary)]">{value ?? <Dash />}</p><p className="mt-1 hidden text-[10px] leading-relaxed text-[var(--text-secondary)] sm:block">{help}</p></div>)}</div><div className="grid grid-cols-3 gap-3 border-b border-[var(--border-subtle)] py-4" data-opening-value-snapshot>{valueSnapshot.map(([label, value, help]) => <div key={label} title={help}><p className="text-[9px] font-medium uppercase tracking-[0.08em] text-[var(--text-secondary)]">{label}</p><p className="mt-1 text-lg font-semibold tabular-nums text-[var(--text-primary)] sm:text-xl">{value ?? <Dash />}</p></div>)}</div><SetRipLandscape targets={targets} /></section>;
}
