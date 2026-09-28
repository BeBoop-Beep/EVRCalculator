"use client";

import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import ChartFrame from "./ChartFrame";
import { readFinancialRipHistory } from "@/lib/rankings/ripBenchmarkClient.mjs";
import { useRankingsAccess } from "@/lib/rankings/useRankingsAccess";
import { INDEX_PLAN_PLUS } from "@/lib/access/indexPlanAccess.mjs";
import { PlanBadge, PlanUpgradeLink } from "@/components/membership/PlanLock";
import {
  FINANCIAL_RIP_WINDOWS,
  buildFinancialRipChartModel,
  eraFinancialRipCandidates,
  financialRipWindowRange,
  financialRipYAxisDomain,
  formatFinancialRip,
  formatFinancialRipDelta,
  setFinancialRipCandidates,
  setIdsForEra,
  shouldFetchFinancialRipHistory,
  toggleFinancialRipSelection,
} from "./financialRipHistoryModel.mjs";

const labelDate = (date) => new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }).format(new Date(`${date}T00:00:00Z`));

function ModeControls({ mode, onChange, disabled = false }) {
  return <div role="radiogroup" aria-label="Financial RIP entity type" className="inline-flex rounded-lg border border-[var(--border-subtle)] bg-black/10 p-1">
    {[{ key: "sets", label: "Sets" }, { key: "eras", label: "Eras" }].map((item) => <button key={item.key} type="button" role="radio" aria-checked={mode === item.key} disabled={disabled} onClick={() => onChange(item.key)} className={`min-h-9 rounded-md px-3 text-xs font-semibold transition-colors ${mode === item.key ? "bg-white/10 text-[var(--text-primary)]" : "text-[var(--text-secondary)]"}`}>{item.label}</button>)}
  </div>;
}

function WindowControls({ value, onChange, disabled = false }) {
  return <div role="radiogroup" aria-label="Financial RIP history time range" className="flex min-w-max gap-1">
    {FINANCIAL_RIP_WINDOWS.map((item) => <button key={item.key} type="button" role="radio" aria-checked={value === item.key} aria-label={item.ariaLabel} disabled={disabled} onClick={() => onChange(item.key)} className={`min-h-9 min-w-11 rounded-md border px-2 text-[10px] font-semibold tracking-wide ${value === item.key ? "border-sky-400/40 bg-sky-400/10 text-sky-200" : "border-[var(--border-subtle)] text-[var(--text-secondary)]"}`}>{item.label}</button>)}
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

function EntitySelector({ candidates, selectedIds, onToggle, mode, search, onSearch, eraPresets = [], onSelectEra }) {
  const visible = candidates.filter((item) => item.name.toLowerCase().includes(search.toLowerCase()));
  return <details className="relative mt-3 rounded-lg border border-[var(--border-subtle)] bg-black/10 px-3 py-2">
    <summary className="cursor-pointer text-xs font-semibold text-[var(--text-primary)]">Choose {mode === "sets" ? "Sets" : "Eras"} <span className="ml-1 font-normal text-[var(--text-secondary)]">{selectedIds.length} selected</span></summary>
    <div className="mt-3">
      <input type="search" value={search} onChange={(event) => onSearch(event.target.value)} placeholder={`Search ${mode === "sets" ? "Sets" : "Eras"}`} aria-label={`Search Financial RIP ${mode === "sets" ? "Sets" : "Eras"}`} className="min-h-10 w-full rounded-md border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 text-sm" />
      {mode === "sets" && eraPresets.length ? <div className="mt-2 flex flex-wrap gap-1.5" aria-label="Select Sets by Era">{eraPresets.map((era) => <button key={era.entity_id} type="button" onClick={() => onSelectEra?.(era.entity_id)} className="min-h-8 rounded-md border border-[var(--border-subtle)] px-2.5 text-[10px] font-semibold text-[var(--text-secondary)] hover:bg-white/[.04]">{era.name}</button>)}</div> : null}
      <div className="mt-2 grid max-h-52 gap-1 overflow-auto sm:grid-cols-2 lg:grid-cols-3">
        {visible.map((item) => { const selected = selectedIds.includes(item.entity_id); return <label key={item.entity_id} className="flex min-h-10 items-center gap-2 rounded-md px-2 text-xs hover:bg-white/[.04]"><input type="checkbox" checked={selected} onChange={() => onToggle(item.entity_id)} /><span>{item.name}</span></label>; })}
      </div>
    </div>
  </details>;
}

function ChartTooltip({ active, payload, names }) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return <div className="max-h-80 min-w-56 overflow-auto rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-3 text-xs shadow-2xl">
    <p className="font-semibold text-[var(--text-primary)]">{labelDate(point.date)}</p>
    <div className="mt-2 border-t border-[var(--border-subtle)] pt-2"><p className="text-[var(--text-secondary)]">Overall Financial RIP</p><p className="text-base font-semibold tabular-nums">{formatFinancialRip(point.overallFinancialRip)}</p></div>
    {Object.entries(point.entities || {}).map(([id, detail]) => <div key={id} className="mt-2 border-t border-[var(--border-subtle)] pt-2"><p className="font-semibold">{names[id]}</p><p>Financial RIP <strong>{formatFinancialRip(detail.financialRip)}</strong></p><p className="text-[var(--text-secondary)]">{formatFinancialRipDelta(detail.deltaVsOverall)}</p><p className="text-[var(--text-secondary)]">{detail.rank == null ? "Rank unavailable" : `Rank #${detail.rank} of ${detail.cohortSize}`}</p></div>)}
  </div>;
}

export default function FinancialRipHistoryChart({ targets = [], openingSets = [], eras = [], marketDate = null }) {
  const { canViewRankingsIntelligence: entitled, authStatus } = useRankingsAccess();
  const [mode, setMode] = useState("sets");
  const [windowKey, setWindowKey] = useState("30D");
  const [setSelection, setSetSelection] = useState([]);
  const [eraSelection, setEraSelection] = useState([]);
  const [search, setSearch] = useState("");
  const [request, setRequest] = useState({ status: "idle", view: null, key: null, pendingKey: null, error: null });
  const [retryNonce, setRetryNonce] = useState(0);
  const setCandidates = useMemo(() => setFinancialRipCandidates(targets, openingSets), [targets, openingSets]);
  const eraCandidates = useMemo(() => eraFinancialRipCandidates(openingSets, eras), [openingSets, eras]);
  useEffect(() => { setSetSelection((current) => current.length ? current.filter((id) => setCandidates.some((item) => item.entity_id === id)).slice(0, MAX_FINANCIAL_RIP_SET_SELECTION) : setCandidates.slice(0, 3).map((item) => item.entity_id)); }, [setCandidates]);
  useEffect(() => { setEraSelection((current) => current.length ? current.filter((id) => eraCandidates.some((item) => item.entity_id === id)) : eraCandidates.map((item) => item.entity_id)); }, [eraCandidates]);
  const candidates = mode === "sets" ? setCandidates : eraCandidates;
  const selectedIds = mode === "sets" ? setSelection : eraSelection;
  const selected = useMemo(() => candidates.filter((item) => selectedIds.includes(item.entity_id)), [candidates, selectedIds]);
  const knownFrom = request.view?.payload?.historyAvailableFrom || null;
  const knownThrough = request.view?.payload?.historyAvailableThrough || marketDate;
  const range = useMemo(() => financialRipWindowRange(windowKey, knownThrough, knownFrom), [windowKey, knownThrough, knownFrom]);
  const fetchRange = useMemo(() => financialRipWindowRange(windowKey, marketDate, windowKey === "ALL" ? null : knownFrom), [windowKey, marketDate, knownFrom]);
  const selectionKey = selected.map((item) => item.entity_id).sort().join(",");
  const requestKey = `${mode}:${selectionKey}:${fetchRange.startDate}:${fetchRange.endDate}:${retryNonce}`;

  useEffect(() => {
    if (!shouldFetchFinancialRipHistory({ entitled, authStatus, selectedCount: selected.length, startDate: fetchRange.startDate, endDate: fetchRange.endDate })) return undefined;
    let active = true;
    setRequest((current) => ({ ...current, status: "loading", pendingKey: requestKey, error: null }));
    readFinancialRipHistory(selected, { startDate: fetchRange.startDate, endDate: fetchRange.endDate })
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
  }, [authStatus, entitled, fetchRange.endDate, fetchRange.startDate, marketDate, mode, requestKey, selected, windowKey]);

  const display = request.view;
  const chart = useMemo(
    () => buildFinancialRipChartModel(display?.payload?.rows || [], display?.selected || [], display?.range || range),
    [display, range],
  );
  const names = useMemo(
    () => Object.fromEntries((display?.selected || []).map((item) => [item.entity_id, item.name])),
    [display],
  );
  const yDomain = useMemo(() => financialRipYAxisDomain(chart.points, chart.series), [chart]);
  const accessPending = authStatus !== "resolved" && authStatus !== "degraded";
  const toggle = (id) => { const setter = mode === "sets" ? setSetSelection : setEraSelection; setter((current) => toggleFinancialRipSelection(current, id)); };
  const selectEraSets = (eraId) => { const ids = setIdsForEra(setCandidates, eraId); if (ids.length) setSetSelection(ids); };

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
      <EntitySelector candidates={candidates} selectedIds={selectedIds} onToggle={toggle} mode={mode} search={search} onSearch={setSearch} eraPresets={eraCandidates} onSelectEra={selectEraSets} />

      {!selected.length ? (
        <div className="mt-4 flex h-[20rem] items-center justify-center rounded-xl border border-[var(--border-subtle)] px-4 text-center text-sm text-[var(--text-secondary)] sm:h-[24rem] desk:h-[28rem]">
          Choose at least one {mode === "sets" ? "Set" : "Era"} to view Financial RIP history.
        </div>
      ) : <>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {chart.series.map((item) => <span key={item.entity_id} className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border-subtle)] px-2.5 py-1 text-[10px]"><span className="h-2 w-2 rounded-full" style={{ backgroundColor: item.color }} />{item.name}</span>)}
          {display ? <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border-subtle)] px-2.5 py-1 text-[10px]"><span className="h-0.5 w-3 bg-slate-200" />Overall Financial RIP</span> : null}
          {request.status === "loading" && display ? <span aria-live="polite" className="text-[10px] text-[var(--text-secondary)]">Updating history…</span> : null}
        </div>

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
                <XAxis dataKey="date" tickFormatter={(value) => labelDate(value).replace(/, \d{4}/, "")} minTickGap={28} tick={{ fill: "#94a3b8", fontSize: 10 }} />
                <YAxis domain={yDomain} tickFormatter={(value) => Number(value).toFixed(1)} tick={{ fill: "#94a3b8", fontSize: 10 }} width={42} />
                <Tooltip content={<ChartTooltip names={names} />} />
                <Legend wrapperStyle={{ fontSize: 11, paddingTop: 8 }} />
                <Line type="linear" dataKey="overallFinancialRip" name="Overall Financial RIP" stroke="#94a3b8" strokeWidth={4} dot={false} activeDot={{ r: 4 }} connectNulls={false} isAnimationActive={false} />
                {chart.series.map((item) => <Line key={item.entity_id} type="linear" dataKey={item.key} name={item.name} stroke={item.color} strokeWidth={2.25} dot={{ r: 3 }} activeDot={{ r: 5 }} connectNulls={false} isAnimationActive={false} />)}
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
      </>}
    </>}
  </section>;
}
