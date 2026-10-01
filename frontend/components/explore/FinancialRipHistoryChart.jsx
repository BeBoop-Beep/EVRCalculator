"use client";

import { RANKINGS_SELECTED_BORDERED_SURFACE } from "@/lib/explore/rankingsSelectedState.mjs";
import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import ChartFrame from "./ChartFrame";
import MultiSelectFilter from "@/components/ui/MultiSelectFilter";
import { readFinancialRipHistory } from "@/lib/rankings/ripBenchmarkClient.mjs";
import { useRankingsAccess } from "@/lib/rankings/useRankingsAccess";
import { INDEX_PLAN_PLUS } from "@/lib/access/indexPlanAccess.mjs";
import { PlanBadge, PlanUpgradeLink } from "@/components/membership/PlanLock";
import {
  FINANCIAL_RIP_WINDOWS,
  buildFinancialRipChartModel,
  eraFinancialRipCandidates,
  financialRipRequestEntities,
  financialRipWindowRange,
  financialRipYAxisDomain,
  formatFinancialRip,
  formatFinancialRipDelta,
  formatFinancialRipTooltipDelta,
  financialRipTooltipRows,
  setFinancialRipCandidates,
  setIdsForEra,
  shouldFetchFinancialRipHistory,
} from "./financialRipHistoryModel.mjs";

const labelDate = (date) => new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }).format(new Date(`${date}T00:00:00Z`));

function ModeControls({ mode, onChange, disabled = false }) {
  return <div role="radiogroup" aria-label="Financial RIP entity type" className="inline-flex rounded-lg border border-[var(--border-subtle)] bg-black/10 p-1">
    {[{ key: "sets", label: "Sets" }, { key: "eras", label: "Eras" }].map((item) => <button key={item.key} type="button" role="radio" aria-checked={mode === item.key} disabled={disabled} onClick={() => onChange(item.key)} className={`min-h-9 rounded-md px-3 text-xs font-semibold transition-colors ${mode === item.key ? RANKINGS_SELECTED_BORDERED_SURFACE : "text-[var(--text-secondary)]"}`}>{item.label}</button>)}
  </div>;
}

function WindowControls({ value, onChange, disabled = false }) {
  return <div role="radiogroup" aria-label="Financial RIP history time range" className="flex min-w-max gap-1">
    {FINANCIAL_RIP_WINDOWS.map((item) => <button key={item.key} type="button" role="radio" aria-checked={value === item.key} aria-label={item.ariaLabel} disabled={disabled} onClick={() => onChange(item.key)} className={`min-h-9 min-w-11 rounded-md border px-2 text-[10px] font-semibold tracking-wide ${value === item.key ? RANKINGS_SELECTED_BORDERED_SURFACE : "border-[var(--border-subtle)] text-[var(--text-secondary)]"}`}>{item.label}</button>)}
  </div>;
}

function LockedPreview() {
  return <div data-financial-rip-history-locked className="relative mt-4 min-h-[20rem] overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[linear-gradient(180deg,rgba(30,41,59,.34),rgba(15,23,42,.2))]">
    <svg aria-hidden="true" viewBox="0 0 800 320" preserveAspectRatio="none" className="absolute inset-0 h-full w-full opacity-25 blur-[3px]">
      <path d="M0 220 C100 170 150 230 250 160 S420 120 510 170 S660 90 800 115" fill="none" stroke="#38bdf8" strokeWidth="5" />
      <path d="M0 180 C120 205 205 135 300 175 S470 205 570 145 S700 175 800 130" fill="none" stroke="#c084fc" strokeWidth="5" />
      <path d="M0 195 C180 188 300 202 450 176 S650 190 800 158" fill="none" stroke="#e2e8f0" strokeWidth="6" strokeDasharray="15 12" />
    </svg>
    <div className="absolute inset-0 bg-white/[.035] backdrop-blur-md" />
    <div className="relative z-10 flex min-h-[20rem] flex-col items-center justify-center px-5 text-center">
      <PlanBadge plan={INDEX_PLAN_PLUS} />
      <p className="mt-4 max-w-md text-lg font-semibold text-[var(--text-primary)]">Track Financial RIP across Sets and Eras over time</p>
      <p className="mt-2 max-w-md text-sm text-[var(--text-secondary)]">Compare exact certified publications with the moving Overall Financial RIP reference.</p>
      <PlanUpgradeLink requiredPlan={INDEX_PLAN_PLUS} source="rankings" className="mt-5" />
    </div>
  </div>;
}

function EntitySelector({ candidates, selectedIds, onChange, mode, eraPresets = [], presetEraId, onPresetChange }) {
  const options = candidates.map((item) => ({ id: item.entity_id, label: item.name }));
  return <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-start">
    {mode === "sets" ? <MultiSelectFilter label="Era preset" name="financial-era-preset" options={eraPresets.map((era) => ({ id: era.entity_id, label: era.name }))} selectedIds={presetEraId ? [presetEraId] : []} onChange={(ids) => onPresetChange(ids.at(-1) || null)} allLabel="Manual Sets" summaryNoun="Era" searchPlaceholder="Search Eras…" showChips={false} /> : null}
    <MultiSelectFilter label={mode === "sets" ? "Sets" : "Eras"} name={`financial-${mode}`} options={options} selectedIds={selectedIds} onChange={onChange} allLabel={`Choose ${mode === "sets" ? "Sets" : "Eras"}`} summaryNoun={mode === "sets" ? "Sets" : "Eras"} searchPlaceholder={`Search ${mode === "sets" ? "Sets…" : "Eras…"}`} showChips={false} />
  </div>;
}

function ChartTooltip({ active, payload, series }) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  const rows = financialRipTooltipRows(point, series);
  return <div className="max-h-80 min-w-56 overflow-auto rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-3 text-xs shadow-2xl">
    <p className="font-semibold text-[var(--text-primary)]">{labelDate(point.date)}</p>
    <div className="mt-2 flex items-center justify-between gap-4 border-t border-[var(--border-subtle)] pt-2"><span className="text-[var(--text-secondary)]">Overall</span><strong className="tabular-nums">{formatFinancialRip(point.overallFinancialRip)}</strong></div>
    <div className="mt-2 space-y-1.5">{rows.map((row) => <div key={row.entity_id} className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2"><span className="h-2 w-2 rounded-full" style={{ backgroundColor: row.color }} /><span className="truncate font-medium">{row.name}</span><span className="tabular-nums text-[var(--text-secondary)]">{formatFinancialRipTooltipDelta(row.deltaVsOverall)}</span></div>)}</div>
  </div>;
}

const MAX_FINANCIAL_RIP_SET_SELECTION = 5;

export default function FinancialRipHistoryChart({ targets = [], financialCohort = null, openingSets = [], eras = [], marketDate = null }) {
  const { canViewRankingsIntelligence: entitled, authStatus } = useRankingsAccess();
  const [mode, setMode] = useState("sets");
  const [windowKey, setWindowKey] = useState("30D");
  const [setSelection, setSetSelection] = useState([]);
  const [eraSelection, setEraSelection] = useState([]);
  const [presetEraId, setPresetEraId] = useState(null);
  const [request, setRequest] = useState({ status: "idle", view: null, key: null, pendingKey: null, error: null });
  const [retryNonce, setRetryNonce] = useState(0);
  const cohortEras = useMemo(() => Array.isArray(financialCohort?.eras) ? financialCohort.eras : [], [financialCohort]);
  const setCandidates = useMemo(() => cohortEras.length ? cohortEras.flatMap((era) => (era.sets || []).map((set) => ({ entity_type: "set", entity_id: String(set.setId), name: set.setName, canonicalKey: set.canonicalKey, eraId: String(era.eraId), eraName: era.eraName }))) : setFinancialRipCandidates(targets, openingSets), [cohortEras, targets, openingSets]);
  const eraCandidates = useMemo(() => cohortEras.length ? cohortEras.map((era) => ({ entity_type: "era", entity_id: String(era.eraId), name: era.eraName })) : eraFinancialRipCandidates(openingSets, eras), [cohortEras, openingSets, eras]);
  useEffect(() => { setSetSelection((current) => current.length ? (presetEraId ? current : current.slice(0, MAX_FINANCIAL_RIP_SET_SELECTION)).filter((id) => setCandidates.some((item) => item.entity_id === id)) : setCandidates.slice(0, 3).map((item) => item.entity_id)); }, [presetEraId, setCandidates]);
  useEffect(() => { setEraSelection((current) => current.length ? current.filter((id) => eraCandidates.some((item) => item.entity_id === id)) : eraCandidates.map((item) => item.entity_id)); }, [eraCandidates]);
  const candidates = mode === "sets" ? setCandidates : eraCandidates;
  const selectedIds = mode === "sets" ? setSelection : eraSelection;
  const selected = useMemo(() => candidates.filter((item) => selectedIds.includes(item.entity_id)), [candidates, selectedIds]);
  const requestEntities = useMemo(() => financialRipRequestEntities(selected, request.view?.selected), [request.view?.selected, selected]);
  const knownFrom = request.view?.payload?.historyAvailableFrom || null;
  const knownThrough = request.view?.payload?.historyAvailableThrough || marketDate;
  const range = useMemo(() => financialRipWindowRange(windowKey, knownThrough, knownFrom), [windowKey, knownThrough, knownFrom]);
  const fetchRange = useMemo(() => financialRipWindowRange(windowKey, marketDate, windowKey === "ALL" ? null : knownFrom), [windowKey, marketDate, knownFrom]);
  const selectionKey = selected.map((item) => item.entity_id).sort().join(",");
  const requestKey = `${mode}:${selectionKey}:${fetchRange.startDate}:${fetchRange.endDate}:${retryNonce}`;

  useEffect(() => {
    if (!shouldFetchFinancialRipHistory({ entitled, authStatus, selectedCount: requestEntities.length, startDate: fetchRange.startDate, endDate: fetchRange.endDate })) return undefined;
    const loadedIds = new Set((request.view?.selected || []).map((item) => item.entity_id));
    if (request.view?.mode === mode && request.view?.windowKey === windowKey && selected.every((item) => loadedIds.has(item.entity_id))) return undefined;
    let active = true;
    setRequest((current) => ({ ...current, status: "loading", pendingKey: requestKey, error: null }));
    readFinancialRipHistory(requestEntities, { startDate: fetchRange.startDate, endDate: fetchRange.endDate })
      .then((payload) => {
        if (!active) return;
        const displayRange = financialRipWindowRange(
          windowKey,
          payload?.historyAvailableThrough || marketDate,
          payload?.historyAvailableFrom || null,
        );
        setRequest({
          status: "ready",
          view: {
            payload,
            selected: selected.map((item) => ({ ...item })),
            range: displayRange,
            mode,
            windowKey,
          },
          key: requestKey,
          pendingKey: null,
          error: null,
        });
      })
      .catch((error) => {
        if (active) setRequest((current) => ({
          ...current,
          status: "error",
          pendingKey: null,
          error: error?.message || "Financial RIP history is temporarily unavailable.",
        }));
      });
    return () => { active = false; };
  }, [authStatus, entitled, fetchRange.endDate, fetchRange.startDate, marketDate, mode, request.view, requestEntities, requestKey, selected, windowKey]);

  const display = request.view?.mode === mode ? request.view : null;
  const chart = useMemo(
    () => buildFinancialRipChartModel(display?.payload?.rows || [], selected, display?.range || range),
    [display, range, selected],
  );
  const names = useMemo(
    () => Object.fromEntries((display?.selected || []).map((item) => [item.entity_id, item.name])),
    [display],
  );
  const yDomain = useMemo(() => financialRipYAxisDomain(chart.points, chart.series), [chart]);
  const accessPending = authStatus !== "resolved" && authStatus !== "degraded";
  const changeSelection = (ids) => { if (mode === "sets") { setPresetEraId(null); setSetSelection(ids.slice(0, MAX_FINANCIAL_RIP_SET_SELECTION)); } else setEraSelection(ids); };
  const selectEraSets = (eraId) => { setPresetEraId(eraId); const ids = setIdsForEra(setCandidates, eraId); if (ids.length) setSetSelection(ids); };
  const removeSeries = (id) => { if (mode === "sets") setSetSelection((current) => current.filter((item) => item !== id)); else setEraSelection((current) => current.filter((item) => item !== id)); };

  return <section className="mt-5 border-t border-[var(--border-subtle)] pt-5" data-financial-rip-history-chart>
    <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
      <div>
        <h3 className="text-lg font-semibold text-[var(--text-primary)]">Financial RIP Over Time</h3>
        <p className="mt-1 max-w-2xl text-xs leading-relaxed text-[var(--text-secondary)]">Compare absolute Financial RIP scores with the Pokémon-wide Overall Financial RIP reference.</p>
      </div>
      <div className="flex max-w-full flex-col gap-2 overflow-x-auto sm:flex-row sm:items-center">
        <ModeControls mode={mode} onChange={setMode} disabled={!entitled || accessPending} />
        <WindowControls value={windowKey} onChange={setWindowKey} disabled={!entitled || accessPending} />
      </div>
    </div>

    {accessPending ? (
      <div className="mt-4 flex h-[20rem] items-center justify-center rounded-xl border border-[var(--border-subtle)] text-sm text-[var(--text-secondary)] sm:h-[24rem] desk:h-[28rem]" aria-busy="true">Loading access…</div>
    ) : !entitled ? <LockedPreview /> : <>
      <EntitySelector candidates={candidates} selectedIds={selectedIds} onChange={changeSelection} mode={mode} eraPresets={eraCandidates} presetEraId={presetEraId} onPresetChange={(eraId) => eraId ? selectEraSets(eraId) : setPresetEraId(null)} />

      <>
        <div className="mt-3 max-w-full overflow-x-auto" aria-label="Visible Financial RIP series"><div className="flex min-w-max items-center gap-2 desk:min-w-0 desk:flex-wrap">
          {display ? <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border-subtle)] px-2.5 py-1 text-[10px]"><span className="h-0.5 w-3 bg-slate-200/75" />Overall Financial RIP</span> : null}
          {chart.series.map((item) => <span key={item.entity_id} className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border-subtle)] px-2.5 py-1 text-[10px]"><span className="h-2 w-2 rounded-full" style={{ backgroundColor: item.color }} /><span>{item.name}</span><button type="button" onClick={() => removeSeries(item.entity_id)} aria-label={`Remove ${item.name} from Financial RIP chart`} className="ml-0.5 rounded px-1 text-sm leading-none text-[var(--text-secondary)] hover:text-[var(--text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]">×</button></span>)}
          {request.status === "loading" && display ? <span aria-live="polite" className="text-[10px] text-[var(--text-secondary)]">Updating history…</span> : null}
        </div></div>

        {!display && request.status === "loading" ? (
          <div className="mt-4 flex h-[20rem] items-center justify-center rounded-xl border border-[var(--border-subtle)] text-sm text-[var(--text-secondary)] sm:h-[24rem] desk:h-[28rem]" aria-busy="true">Loading Financial RIP history…</div>
        ) : !display && request.status === "error" ? (
          <div className="mt-4 flex h-[20rem] flex-col items-center justify-center rounded-xl border border-[var(--border-subtle)] px-4 text-center sm:h-[24rem] desk:h-[28rem]">
            <p className="text-sm text-[var(--text-secondary)]">Financial RIP history is temporarily unavailable.</p>
            <button type="button" onClick={() => setRetryNonce((value) => value + 1)} className="mt-3 min-h-10 rounded-md border border-[var(--border-subtle)] px-4 text-sm font-semibold">Retry</button>
          </div>
        ) : display ? <>
          <ChartFrame className="mt-4 h-[20rem] sm:h-[24rem] desk:h-[28rem]">
            <ResponsiveContainer>
              <LineChart data={chart.points} margin={{ top: 12, right: 14, bottom: 6, left: 0 }}>
                <CartesianGrid stroke="rgba(148,163,184,.16)" strokeDasharray="2 8" vertical={false} />
                <XAxis dataKey="timestamp" type="number" scale="time" domain={["dataMin", "dataMax"]} tickFormatter={(value) => labelDate(new Date(value).toISOString().slice(0, 10)).replace(/, \d{4}/, "")} minTickGap={28} tick={{ fill: "#94a3b8", fontSize: 10 }} />
                <YAxis domain={yDomain} tickFormatter={(value) => Number(value).toFixed(1)} tick={{ fill: "#94a3b8", fontSize: 10 }} width={42} />
                <Tooltip content={<ChartTooltip series={chart.series} />} />
                <Line type="linear" dataKey="overallFinancialRip" name="Overall Financial RIP" stroke="#cbd5e1" strokeOpacity={0.72} strokeWidth={3} dot={false} activeDot={{ r: 4 }} connectNulls={false} isAnimationActive={false} />
                {chart.series.map((item) => <Line key={item.entity_id} type="linear" dataKey={item.key} name={item.name} stroke={item.color} strokeWidth={1.75} dot={{ r: 2 }} activeDot={{ r: 5 }} connectNulls={false} isAnimationActive={false} />)}
              </LineChart>
            </ResponsiveContainer>
          </ChartFrame>
          <ol className="sr-only" aria-label="Visible Financial RIP observations">
            {chart.points.flatMap((point) => Object.entries(point.entities).map(([id, detail]) => <li key={`${point.date}:${id}`}>{labelDate(point.date)}, {names[id]} Financial RIP {formatFinancialRip(detail.financialRip)}, {formatFinancialRipDelta(detail.deltaVsOverall)}, Overall Financial RIP {formatFinancialRip(detail.overallFinancialRip)}, {detail.rank == null ? "rank unavailable" : `rank ${detail.rank} of ${detail.cohortSize}`}.</li>))}
          </ol>
          <p className="mt-2 text-[10px] text-[var(--text-secondary)]">Exact certified publications only{display.payload?.historyAvailableFrom ? ` · History available from ${labelDate(display.payload.historyAvailableFrom)}` : ""}{display.payload?.historyAvailableThrough ? ` through ${labelDate(display.payload.historyAvailableThrough)}` : ""}. Missing publication dates remain gaps.</p>
          {request.status === "error" ? <p role="alert" className="mt-2 text-xs text-red-300">The latest refresh failed, so the last successful history remains visible. <button type="button" onClick={() => setRetryNonce((value) => value + 1)} className="underline">Retry</button></p> : null}
        </> : (
          <div className="mt-4 h-[20rem] rounded-xl border border-[var(--border-subtle)] sm:h-[24rem] desk:h-[28rem]" />
        )}
      </>
    </>}
  </section>;
}
