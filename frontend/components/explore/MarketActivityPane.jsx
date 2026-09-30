"use client";

import { useEffect, useMemo, useState } from "react";
import { activityDateGeometry, activityPointAtDate, capabilityIsCurrent } from "@/lib/explore/marketActivityState.mjs";

const labelState = (value) => String(value || "unknown").replaceAll("_", " ").toLowerCase();
const formatDate = (value) => value ? new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`)) : "Move across the price chart to inspect a date";

export default function MarketActivityPane({ state, inspectedDate, canonicalDates = [] }) {
  const [view, setView] = useState("sales");
  const [evaluationTime, setEvaluationTime] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setEvaluationTime(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);
  const payload = state.data;
  const sparsePoints = useMemo(() => view === "sales"
    ? payload?.series?.sales?.counts?.points || []
    : payload?.series?.supply?.listings?.points || [], [payload, view]);
  const points = useMemo(() => {
    if (view !== "sales" || !payload?.series?.sales?.provenSpan) return sparsePoints;
    const existing = new Set(sparsePoints.map((point) => point.date));
    const { startDate, endDate } = payload.series.sales.provenSpan;
    return [...sparsePoints, ...canonicalDates.filter((date) => date >= startDate && date <= endDate && !existing.has(date))
      .map((date) => ({ date, observedCount: 0, proofState: "PROVEN", explicitZero: true }))];
  }, [canonicalDates, payload?.series?.sales?.provenSpan, sparsePoints, view]);
  const positionedPoints = useMemo(() => activityDateGeometry(points, canonicalDates), [points, canonicalDates]);
  const maximum = Math.max(1, ...points.map((point) => point.observedCount ?? point.value ?? 0));
  const inspected = useMemo(() => activityPointAtDate(payload, view, inspectedDate), [payload, view, inspectedDate]);
  const currentAsks = capabilityIsCurrent(payload?.capabilities?.currentAsks, evaluationTime);

  return (
    <section data-market-activity-pane aria-labelledby="market-activity-heading" className="mx-2 mb-1 rounded-lg border border-sky-400/25 bg-slate-950/45 px-3 py-2 sm:mx-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 id="market-activity-heading" className="text-xs font-semibold text-sky-100">Activity for current constituents</h3>
          <p className="mt-0.5 text-[10px] uppercase tracking-wide text-amber-200">Fixture-backed / not live API</p>
        </div>
        <div role="tablist" aria-label="Market Activity view" className="flex rounded-md border border-slate-600/60 p-0.5">
          {[['sales', 'Sales'], ['supply', 'Offered Supply']].map(([id, label]) => <button key={id} type="button" role="tab" aria-selected={view === id} onClick={() => setView(id)} className={`min-h-8 rounded px-2 text-[11px] font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300 ${view === id ? 'bg-sky-400/20 text-sky-100' : 'text-slate-300'}`}>{label}</button>)}
        </div>
      </div>
      <div aria-live="polite" className="mt-2">
        {state.status === "loading" ? <p role="status" className="text-xs text-slate-300">Loading Market Activity fixture…</p> : null}
        {state.status === "error" ? <p role="alert" className="text-xs text-rose-300">Activity could not be loaded. The price chart remains available.</p> : null}
        {state.status === "ready" && payload?.availability?.state === "UNAVAILABLE" ? <p role="status" className="text-xs text-amber-200">Activity unavailable: {payload.availability.reasons.map(labelState).join(", ")}.</p> : null}
        {state.status === "ready" && payload?.series ? <>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[10px] text-slate-300 sm:grid-cols-4">
            <span>Roster as of <strong className="text-slate-100">{payload.roster?.rosterAsOf}</strong></span>
            <span>Roster <strong className="text-slate-100">{payload.roster?.rosterDenominator}</strong></span>
            <span>Proven / partial / unproven <strong className="text-slate-100">{payload.coverage?.windowProven ?? 0} / {payload.coverage?.windowPartial ?? 0} / {payload.coverage?.windowUnproven ?? 0}</strong></span>
            <span>Not collected <strong className="text-slate-100">{payload.coverage?.notCollected ?? 0}</strong></span>
            <span>Observed sales ≥ <strong className="text-slate-100">{payload.totals?.observedSaleCountLowerBound ?? 'unknown'}</strong></span>
            <span>Proven sales <strong className="text-slate-100">{payload.totals?.provenSaleCount ?? 'not established'}</strong></span>
            <span>Activity <strong className="text-slate-100">{payload.series.activityRange.startDate}–{payload.series.activityRange.endDate}</strong></span>
            <span>Price chart <strong className="text-slate-100">{payload.series.canonicalRange ? `${payload.series.canonicalRange.startDate}–${payload.series.canonicalRange.endDate}` : 'selected interval'}</strong></span>
          </div>
          <div data-market-activity-series={view} className="relative mt-2 h-12 border-b border-slate-600/50" aria-label={`${view === 'sales' ? 'Observed sale records' : 'Captured offered supply'}; sparse dated series aligned to the canonical chart dates`}>
            {positionedPoints.length ? positionedPoints.map((point) => {
              const value = point.observedCount ?? point.value ?? 0;
              const selected = inspectedDate === point.date;
              return <span key={point.date} title={`${point.date}: ${value}`} data-activity-date={point.date} data-activity-canonical-index={point.canonicalIndex} data-activity-x-percent={point.xPercent.toFixed(4)} data-proof-state={point.proofState || point.depth || point.stateAtCollection || 'OBSERVED'} className={`absolute bottom-0 w-1.5 -translate-x-1/2 rounded-t ${point.explicitZero ? 'border-t-2 border-sky-300 bg-transparent' : selected ? 'bg-sky-200 ring-2 ring-white' : point.proofState === 'PROVEN' || value === 0 ? 'bg-sky-400' : 'bg-amber-400/75'}`} style={{ left: `${point.xPercent}%`, height: value === 0 ? 2 : `${Math.max(12, (value / maximum) * 100)}%` }} />;
            }) : <span className="absolute inset-0 flex items-center text-[10px] text-slate-400">No dated {view === 'sales' ? 'sale observations' : 'provider-confirmed supply snapshots'} in the visible canonical date range.</span>}
          </div>
          <div data-market-activity-inspection className="mt-1.5 flex flex-wrap justify-between gap-2 text-[10px] text-slate-300">
            <span><strong className="text-slate-100">{formatDate(inspectedDate)}</strong> · {inspected.state === 'UNKNOWN' ? 'Activity unknown — missing is not zero' : inspected.state === 'PROVEN_ZERO' ? 'Proven zero' : `${inspected.point?.observedCount ?? inspected.point?.value} ${view === 'sales' ? 'observed sale record(s)' : 'captured listing(s)'}`}</span>
            <span>{view === 'sales' ? 'PkmnPrices eBay sold evidence · Unknown raw condition' : `Provider-confirmed asks · ${currentAsks ? 'current capability' : 'not current / expired'}`}</span>
          </div>
          <p className="sr-only">Membership is current-roster retrospective, not point-in-time historical membership. Missing dates are unknown unless inside a proven sales span. Offered supply is bounded captured depth, not total listings.</p>
        </> : null}
      </div>
    </section>
  );
}

