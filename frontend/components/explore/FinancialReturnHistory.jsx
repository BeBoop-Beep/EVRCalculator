"use client";

import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import PlanLock from "@/components/membership/PlanLock";
import { INDEX_PLAN_PLUS } from "@/lib/access/indexPlanAccess.mjs";
import { readFinancialRipHistory } from "@/lib/rankings/ripBenchmarkClient.mjs";
import ChartFrame from "./ChartFrame";
import { benchmarkMetric } from "./ripBenchmarkPresentation.mjs";

const WINDOWS = { "30D": 29, "3M": 89, "6M": 179, "1Y": 365 };
const ALL_WINDOW_DAYS = 3652;
const COLORS = ["#2dd4bf", "#60a5fa", "#f59e0b", "#f472b6", "#a78bfa"];

const id = (target) => String(target?.target_id || target?.setId || target?.id || "");
const finite = (value) => value === null || value === undefined || value === "" ? null : Number.isFinite(Number(value)) ? Number(value) : null;
const minusDays = (date, count) => new Date(new Date(`${date}T00:00:00Z`).getTime() - count * 86400000).toISOString().slice(0, 10);
const plusDays = (date, count) => new Date(new Date(`${date}T00:00:00Z`).getTime() + count * 86400000).toISOString().slice(0, 10);
const dayDistance = (left, right) => (new Date(`${right}T00:00:00Z`) - new Date(`${left}T00:00:00Z`)) / 86400000;
const labelDate = (date) => new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" }).format(new Date(`${date}T00:00:00Z`));
const formatScore = (value) => {
  const number = finite(value);
  return number === null ? "Unavailable" : number.toFixed(1);
};
const formatDelta = (value) => {
  const number = finite(value);
  if (number === null) return "Unavailable";
  return `${number > 0 ? "+" : ""}${number.toFixed(1)}`;
};

function HistorySkeleton() {
  return <div className="mt-4" aria-busy="true" aria-label="Loading Financial RIP history">
    <div className="h-8 w-72 max-w-full animate-pulse rounded bg-white/[.06]" />
    <div className="mt-3 h-72 animate-pulse rounded-xl border border-[var(--border-subtle)] bg-white/[.035]" />
  </div>;
}

function LockedHistory() {
  return <div className="relative mt-5 overflow-hidden rounded-xl border border-[var(--border-subtle)]" data-financial-history-lock>
    <div aria-hidden="true" className="pointer-events-none h-72 select-none opacity-45 blur-[3px]">
      <div className="flex h-full flex-col justify-between p-6">
        {[0, 1, 2, 3].map((value) => <div key={value} className="border-t border-white/10" />)}
      </div>
      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 40" preserveAspectRatio="none">
        <polyline points="0,27 18,22 34,25 52,16 70,19 84,12 100,14" fill="none" stroke="currentColor" strokeWidth="0.7" />
        <polyline points="0,23 18,23 34,22 52,22 70,21 84,21 100,20" fill="none" stroke="currentColor" strokeWidth="0.45" strokeDasharray="2 2" />
      </svg>
    </div>
    <div className="absolute inset-0 flex items-center justify-center bg-black/20 p-4 backdrop-blur-sm">
      <PlanLock
        requiredPlan={INDEX_PLAN_PLUS}
        source="rankings"
        description="Unlock absolute Financial RIP history for Sets and Eras, including the moving Pokémon Overall reference."
        className="w-full max-w-md"
      />
    </div>
  </div>;
}

function TooltipContent({ active, payload, names }) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return <div className="max-h-80 overflow-auto rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-3 text-xs shadow-xl">
    <p className="font-semibold">{labelDate(point.date)}</p>
    {Object.entries(point.details || {}).map(([entityId, detail]) => <div key={entityId} className="mt-2 border-t border-[var(--border-subtle)] pt-2">
      <p className="font-semibold">{names[entityId] || "Selected market"}</p>
      <p>Financial RIP <strong>{formatScore(detail.score)}</strong></p>
      <p>Pokémon Overall {formatScore(detail.reference)}</p>
      <p>Difference vs Overall {formatDelta(detail.delta)}</p>
      {detail.rank == null ? null : <p>Rank #{detail.rank}{detail.cohort == null ? "" : ` of ${detail.cohort}`}</p>}
    </div>)}
  </div>;
}

function buildSparsePoints(history, startDate, endDate, selectedIds) {
  if (!history || !startDate || !endDate) return [];
  const byDate = new Map();
  for (const row of history.rows || []) {
    const entityId = String(row?.entity_id || "");
    const date = String(row?.market_date || "").slice(0, 10);
    if (!selectedIds.includes(entityId) || !/^\d{4}-\d{2}-\d{2}$/.test(date) || date < startDate || date > endDate) continue;
    const point = byDate.get(date) || { date, details: {}, overall: null };
    const reference = finite(row.overall_financial_rip_reference);
    if (point.overall === null && reference !== null) point.overall = reference;
    const absolute = finite(row.absolute_financial_rip_score);
    if (absolute !== null) {
      point[`e_${entityId}`] = absolute;
      point.details[entityId] = {
        score: absolute,
        reference,
        delta: finite(row.absolute_delta_vs_overall),
        rank: finite(row.rank),
        cohort: finite(row.cohort_size),
      };
    }
    byDate.set(date, point);
  }

  const published = [...byDate.values()].sort((left, right) => left.date.localeCompare(right.date));
  const sparse = [];
  if (!published.length || published[0].date !== startDate) sparse.push({ date: startDate, details: {}, overall: null });
  for (const point of published) {
    const previous = sparse.at(-1);
    if (previous && dayDistance(previous.date, point.date) > 1) {
      sparse.push({ date: plusDays(previous.date, 1), details: {}, overall: null });
    }
    sparse.push(point);
  }
  if (!sparse.length || sparse.at(-1).date !== endDate) {
    const previous = sparse.at(-1);
    if (previous && dayDistance(previous.date, endDate) > 1) {
      sparse.push({ date: plusDays(previous.date, 1), details: {}, overall: null });
    }
    sparse.push({ date: endDate, details: {}, overall: null });
  }
  return sparse;
}

export default function FinancialReturnHistory({
  targets = [],
  eras = [],
  benchmark = null,
  entitled = false,
  accessStatus = "resolved",
}) {
  const [mode, setMode] = useState("sets");
  const [windowKey, setWindowKey] = useState("30D");
  const [setSelection, setSetSelection] = useState([]);
  const [eraSelection, setEraSelection] = useState([]);
  const [display, setDisplay] = useState(null);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [retryNonce, setRetryNonce] = useState(0);

  const candidates = useMemo(() => mode === "sets"
    ? targets
      .map((target) => ({
        entity_type: "set",
        entity_id: id(target),
        name: target.name,
        rank: benchmarkMetric(benchmark?.rows, "set", id(target), "financial").rank,
      }))
      .filter((item) => item.entity_id)
      .sort((left, right) => (left.rank ?? 999) - (right.rank ?? 999))
    : eras
      .map((era) => ({ entity_type: "era", entity_id: String(era.eraId || ""), name: era.eraName }))
      .filter((item) => item.entity_id),
  [mode, targets, eras, benchmark]);

  useEffect(() => {
    if (!setSelection.length && mode === "sets" && candidates.length) {
      setSetSelection(candidates.slice(0, 3).map((item) => item.entity_id));
    }
  }, [mode, candidates, setSelection.length]);

  useEffect(() => {
    if (!eraSelection.length && mode === "eras" && candidates.length) {
      setEraSelection(candidates.slice(0, 5).map((item) => item.entity_id));
    }
  }, [mode, candidates, eraSelection.length]);

  const selectedIds = mode === "sets" ? setSelection : eraSelection;
  const selected = useMemo(() => candidates.filter((item) => selectedIds.includes(item.entity_id)), [candidates, selectedIds]);
  const endDate = benchmark?.freshness?.benchmarkMarketDate || benchmark?.market_date || null;
  const requestStartDate = endDate ? minusDays(endDate, windowKey === "ALL" ? ALL_WINDOW_DAYS : WINDOWS[windowKey]) : null;
  const requestKey = `${mode}:${windowKey}:${endDate || ""}:${selected.map((item) => item.entity_id).sort().join(",")}`;

  useEffect(() => {
    if (!entitled || accessStatus !== "resolved" || !endDate || !requestStartDate || !selected.length) return undefined;
    let live = true;
    setRefreshing(true);
    setError(null);
    readFinancialRipHistory(selected, { startDate: requestStartDate, endDate })
      .then((history) => {
        if (!live) return;
        const availableFrom = history?.historyAvailableFrom;
        const startDate = windowKey === "ALL" && availableFrom && availableFrom > requestStartDate ? availableFrom : requestStartDate;
        setDisplay({
          history,
          selected: selected.map((item) => ({ ...item })),
          startDate,
          endDate,
          mode,
          windowKey,
          requestKey,
        });
      })
      .catch((reason) => {
        if (live) setError(reason?.message || "Financial RIP history is temporarily unavailable.");
      })
      .finally(() => {
        if (live) setRefreshing(false);
      });
    return () => { live = false; };
  }, [entitled, accessStatus, endDate, requestStartDate, requestKey, retryNonce, selected, windowKey, mode]);

  const toggle = (entityId) => {
    const setter = mode === "sets" ? setSetSelection : setEraSelection;
    setter((current) => current.includes(entityId)
      ? current.filter((value) => value !== entityId)
      : current.length < 5 ? [...current, entityId] : current);
  };

  const displayIds = display?.selected?.map((item) => item.entity_id) || [];
  const displayNames = Object.fromEntries((display?.selected || []).map((item) => [item.entity_id, item.name]));
  const points = useMemo(
    () => buildSparsePoints(display?.history, display?.startDate, display?.endDate, displayIds),
    [display],
  );

  if (accessStatus !== "resolved") return <HistorySkeleton />;
  if (!entitled) return <LockedHistory />;

  return <div className="mt-5" data-financial-rip-history>
    <div className="flex flex-wrap items-end justify-between gap-2">
      <div>
        <h3 className="text-base font-semibold">Financial RIP history</h3>
        <p className="mt-1 text-xs text-[var(--text-secondary)]">Absolute Financial RIP V4 versus the same-day Pokémon Overall reference. Missing publication dates remain gaps.</p>
      </div>
      {refreshing && display ? <span aria-live="polite" className="text-xs text-[var(--text-secondary)]">Updating history…</span> : null}
    </div>

    <div className="mt-3 flex flex-wrap gap-2">
      <div>{["sets", "eras"].map((value) => <button key={value} type="button" onClick={() => setMode(value)} aria-pressed={mode === value} className="mr-1 rounded-full border px-3 py-1 text-xs">{value === "sets" ? "Sets" : "Eras"}</button>)}</div>
      <div>{[...Object.keys(WINDOWS), "ALL"].map((value) => <button key={value} type="button" onClick={() => setWindowKey(value)} aria-pressed={windowKey === value} className="mr-1 rounded px-2 py-1 text-xs">{value}</button>)}</div>
    </div>

    <div className="mt-2 flex max-h-24 flex-wrap gap-1 overflow-auto">
      {candidates.map((item) => <button type="button" key={item.entity_id} onClick={() => toggle(item.entity_id)} aria-pressed={selectedIds.includes(item.entity_id)} className="rounded-full border px-2 py-1 text-[10px]">{item.name}</button>)}
    </div>

    {!selected.length ? <p className="mt-4 text-sm text-[var(--text-secondary)]">Select at least one {mode === "sets" ? "Set" : "Era"} to chart.</p> : null}
    {!display && refreshing ? <HistorySkeleton /> : null}
    {!display && !refreshing && error ? <p role="alert" className="mt-4 text-sm text-red-300">{error} <button type="button" className="underline" onClick={() => setRetryNonce((value) => value + 1)}>Retry</button></p> : null}

    {display && selected.length ? <>
      <ChartFrame className="mt-4 h-[20rem]">
        <ResponsiveContainer>
          <LineChart data={points}>
            <CartesianGrid strokeOpacity={0.2} strokeDasharray="2 8" />
            <XAxis dataKey="date" tickFormatter={labelDate} minTickGap={24} />
            <YAxis tickFormatter={(value) => Number(value).toFixed(0)} width={36} />
            <Tooltip content={<TooltipContent names={displayNames} />} />
            <Legend />
            <Line dataKey="overall" name="Pokémon Overall" stroke="#fff" strokeDasharray="5 5" dot={false} connectNulls={false} />
            {(display.selected || []).map((item, index) => <Line key={item.entity_id} dataKey={`e_${item.entity_id}`} name={item.name} stroke={COLORS[index]} connectNulls={false} dot={{ r: 3 }} />)}
          </LineChart>
        </ResponsiveContainer>
      </ChartFrame>
      <ol className="sr-only" aria-label="Visible Financial RIP history">
        {points.flatMap((point) => Object.entries(point.details || {}).map(([entityId, detail]) => <li key={`${point.date}:${entityId}`}>{displayNames[entityId]}, {labelDate(point.date)}: Financial RIP {formatScore(detail.score)}; Pokémon Overall {formatScore(detail.reference)}; difference {formatDelta(detail.delta)}.</li>))}
      </ol>
      {error ? <p role="alert" className="mt-2 text-xs text-red-300">The latest refresh failed, so the last successful history remains visible. <button type="button" className="underline" onClick={() => setRetryNonce((value) => value + 1)}>Retry</button></p> : null}
    </> : null}
  </div>;
}
