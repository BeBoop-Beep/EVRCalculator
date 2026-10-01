"use client";

import React, { useMemo, useState } from "react";
import { activityChartDto } from "../../lib/explore/marketActivityChartAdapter.mjs";
import { formatExplorerMarketLabel } from "../../lib/explore/marketExplorerLabels.mjs";

const WIDTH = 1000; const HEIGHT = 360; const LEFT = 58; const RIGHT = 62; const TOP = 18; const BOTTOM = 42;
const dateMs = (date) => Date.parse(`${date}T00:00:00Z`);
const shortDate = (date) => new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" }).format(new Date(`${date}T00:00:00Z`));
const valueText = (value, missing = "Not observed") => value === null || value === undefined ? missing : String(value);

export function activityCalendarX(date, startDate, endDate) {
  const span = dateMs(endDate) - dateMs(startDate);
  return span > 0 ? LEFT + ((dateMs(date) - dateMs(startDate)) / span) * (WIDTH - LEFT - RIGHT) : LEFT;
}

export default function MarketActivityChart({ state, model, focusedSeries, timeframe, fixtureMode = false }) {
  const [inspectedDate, setInspectedDate] = useState(null);
  const dto = useMemo(() => state?.data ? activityChartDto(state.data) : null, [state?.data]);
  const startDate = dto?.canonicalRange?.startDate || model?.startDate;
  const endDate = dto?.canonicalRange?.endDate || model?.endDate;
  const sales = dto?.sales?.points || []; const supply = dto?.supply?.points || [];
  const counts = [...sales.map((p) => p.observedSoldCount), ...supply.flatMap((p) => [p.listedQuantity, p.listingOfferCount])].filter(Number.isFinite);
  const countMax = Math.max(1, ...counts); const countY = (value) => TOP + (1 - value / countMax) * (HEIGHT - TOP - BOTTOM);
  const indexValues = (model?.series || []).flatMap((series) => series.values || []).filter(Number.isFinite);
  const indexMin = Math.min(...indexValues, 100); const indexMax = Math.max(...indexValues, 100); const indexSpan = indexMax - indexMin || 1;
  const indexY = (value) => TOP + (1 - (value - indexMin) / indexSpan) * (HEIGHT - TOP - BOTTOM);
  const activeSales = sales.find((point) => point.date === inspectedDate) || null;
  const activeSupply = supply.find((point) => point.date === inspectedDate) || null;
  const focusedContext = (model?.series || []).find((series) => series.key === focusedSeries?.key);
  const dateIndex = inspectedDate ? model?.dates?.indexOf(inspectedDate) : -1;
  const activeIndex = dateIndex >= 0 ? focusedContext?.values?.[dateIndex] ?? null : null;
  const inspect = (event) => { if (!startDate || !endDate) return; const bounds = event.currentTarget.getBoundingClientRect(); const ratio = Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width)); const target = dateMs(startDate) + ratio * (dateMs(endDate) - dateMs(startDate)); const dates = [...new Set([...sales, ...supply].map((point) => point.date))]; if (!dates.length) return; setInspectedDate(dates.reduce((best, date) => Math.abs(dateMs(date) - target) < Math.abs(dateMs(best) - target) ? date : best)); };
  const status = state?.status || "idle";

  return <div data-market-activity-chart data-activity-status={status} className="flex h-full min-h-0 flex-col" role="img" tabIndex={0} aria-label={`Market Activity for ${formatExplorerMarketLabel(focusedSeries)}, ${timeframe}. Observed sold records and sparse listing evidence. Background Market Index lines are context only.`} onPointerMove={inspect} onFocus={() => setInspectedDate([...sales, ...supply].map((point) => point.date).sort().at(-1) || null)} onKeyDown={(event) => { const dates = [...new Set([...sales, ...supply].map((point) => point.date))].sort(); if (!dates.length || !["ArrowLeft", "ArrowRight"].includes(event.key)) return; event.preventDefault(); const current = Math.max(0, dates.indexOf(inspectedDate)); setInspectedDate(dates[Math.max(0, Math.min(dates.length - 1, current + (event.key === "ArrowRight" ? 1 : -1)))]); }}>
    <div className="flex items-center justify-between px-1 pb-1 text-[10px] text-[var(--text-secondary)]"><span>Activity count</span><span>{fixtureMode ? "Fixture evidence" : "Observed evidence"}{dto?.coverage?.observedConstituents != null ? ` · ${dto.coverage.observedConstituents} observed constituents` : ""}</span><span>Market Index</span></div>
    <div className="relative min-h-[4rem] flex-1">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} preserveAspectRatio="none" className="h-full w-full overflow-visible" aria-hidden="true">
        {[0, .25, .5, .75, 1].map((ratio) => <line key={ratio} x1={LEFT} x2={WIDTH - RIGHT} y1={TOP + ratio * (HEIGHT - TOP - BOTTOM)} y2={TOP + ratio * (HEIGHT - TOP - BOTTOM)} stroke="rgba(148,163,184,.13)" vectorEffect="non-scaling-stroke" />)}
        {(model?.series || []).map((series) => { const points = (series.values || []).map((value, index) => Number.isFinite(value) ? `${activityCalendarX(model.dates[index], startDate, endDate)},${indexY(value)}` : null).filter(Boolean).join(" "); const focused = series.key === focusedSeries?.key; return points ? <polyline key={series.key} data-activity-index-context={series.key} data-activity-index-focus={focused ? "focused" : "background"} points={points} fill="none" stroke={series.color} strokeOpacity={focused ? .42 : .13} strokeWidth={focused ? 2 : 1.25} vectorEffect="non-scaling-stroke" /> : null; })}
        {sales.map((point) => { const value = point.observedSoldCount; if (!Number.isFinite(value)) return null; const x = activityCalendarX(point.date, startDate, endDate); const y = countY(value); return <rect key={point.date} data-activity-sales-bar={point.date} data-activity-sales-value={value} x={x - 5} y={value === 0 ? HEIGHT - BOTTOM - 2 : y} width="10" height={value === 0 ? 2 : HEIGHT - BOTTOM - y} rx="2" fill="rgb(34,211,238)" opacity=".88" />; })}
        {supply.map((point) => { const value = Number.isFinite(point.listedQuantity) ? point.listedQuantity : point.listingOfferCount; if (!Number.isFinite(value)) return null; const x = activityCalendarX(point.date, startDate, endDate); const y = countY(value); return <circle key={point.date} data-activity-supply-marker={point.date} data-activity-listed-copies={point.listedQuantity ?? undefined} data-activity-listing-offers={point.listingOfferCount ?? undefined} cx={x} cy={y} r="7" fill={point.listedQuantity == null ? "transparent" : "rgb(167,139,250)"} stroke="rgb(196,181,253)" strokeWidth="3" vectorEffect="non-scaling-stroke" />; })}
      </svg>
      {status === "loading" ? <p role="status" className="absolute inset-0 flex items-center justify-center text-xs text-cyan-100">Loading Market Activity…</p> : null}
      {status === "error" ? <div className="absolute inset-0 flex items-center justify-center gap-2"><p role="alert" className="text-xs text-rose-200">Market Activity temporarily unavailable.</p>{state.error?.retryable !== false ? <button type="button" data-market-activity-retry onClick={state.retry} className="rounded border px-2 py-1 text-xs">Retry</button> : null}</div> : null}
      {status === "ready" && state.data?.availability?.state === "UNAVAILABLE" ? <p role="status" className="absolute inset-0 flex items-center justify-center text-xs text-amber-200">Market Activity is no longer available for this published scope.</p> : null}
      {inspectedDate && status === "ready" ? <div data-market-activity-tooltip className="pointer-events-none absolute left-1/2 top-2 z-20 w-64 -translate-x-1/2 rounded-lg border border-[var(--border-subtle)] bg-slate-950/95 p-2 text-[10px] shadow-2xl"><strong className="block text-xs text-white">{formatExplorerMarketLabel(focusedSeries)}</strong><span className="text-[var(--text-secondary)]">{shortDate(inspectedDate)}</span><dl className="mt-1 grid grid-cols-2 gap-x-2"><dt>Observed sales</dt><dd className="text-right">{valueText(activeSales?.observedSoldCount)}</dd><dt>Listings observed</dt><dd className="text-right">{valueText(activeSupply?.listingOfferCount)}</dd><dt>Listed copies</dt><dd className="text-right">{valueText(activeSupply?.listedQuantity)}</dd><dt>Market Index</dt><dd className="text-right">{Number.isFinite(activeIndex) ? activeIndex.toFixed(2) : "—"}</dd></dl>{activeSupply ? <p className="mt-1 text-[var(--text-secondary)]">{activeSupply.observedAt ? `Observed ${activeSupply.observedAt}` : `Historical listing observation · ${shortDate(activeSupply.date)}`}</p> : null}</div> : null}
    </div>
    <div className="flex justify-between px-1 pt-1 text-[10px] text-[var(--text-secondary)]"><span>{startDate ? shortDate(startDate) : "—"}</span><span>Observed sold records · eBay evidence · Listed copies · TCGplayer snapshots</span><span>{endDate ? shortDate(endDate) : "—"}</span></div>
  </div>;
}
