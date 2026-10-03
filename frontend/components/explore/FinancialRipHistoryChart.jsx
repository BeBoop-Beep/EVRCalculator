"use client";

import { RANKINGS_SELECTED_BORDERED_SURFACE } from "@/lib/explore/rankingsSelectedState.mjs";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import ChartFrame from "./ChartFrame";
import MultiSelectFilter from "@/components/ui/MultiSelectFilter";
import DarkSelect from "@/components/ui/DarkSelect";
import { peekFinancialHistory, readFinancialHistoryCached } from "@/lib/rankings/financialHistoryCache.mjs";
import { useRankingsAccess } from "@/lib/rankings/useRankingsAccess";
import { INDEX_PLAN_PLUS } from "@/lib/access/indexPlanAccess.mjs";
import { PlanBadge, PlanUpgradeLink } from "@/components/membership/PlanLock";
import FinancialRipHistoryLegend from "./FinancialRipHistoryLegend";
import ChartTooltip, { FinancialRipTooltipContent, TOOLTIP_SCROLL_ATTR } from "./FinancialRipHistoryTooltip";
import { FINANCIAL_RIP_DEFAULT_SET_COUNT, FINANCIAL_RIP_WINDOWS, TREND_METRICS, buildFinancialRipCandidates, buildTrendChartModel, financialRipRequestEntities, financialRipWindowRange, financialRipYAxisDomain, formatTrendValue, nextSingleEraPreset, orderSeriesForDrawing, resolveActiveFocus, seriesEmphasis, setIdsForEra, shouldFetchFinancialRipHistory, toggleFocus, trendMetric } from "./financialRipHistoryModel.mjs";

const labelDate = (date) =>
  new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${date}T00:00:00Z`));

function ModeControls({ mode, onChange, disabled = false }) {
  return (
    <div role="radiogroup" aria-label="Financial RIP entity type" className="inline-flex rounded-lg border border-[var(--border-subtle)] bg-black/10 p-1">
      {[
        { key: "sets", label: "Sets" },
        { key: "eras", label: "Eras" },
      ].map((item) => (
        <button key={item.key} type="button" role="radio" aria-checked={mode === item.key} disabled={disabled} onClick={() => onChange(item.key)} className={`min-h-9 rounded-md px-3 text-xs font-semibold transition-colors ${mode === item.key ? RANKINGS_SELECTED_BORDERED_SURFACE : "text-[var(--text-secondary)]"}`}>
          {item.label}
        </button>
      ))}
    </div>
  );
}

function WindowControls({ value, onChange, disabled = false }) {
  return (
    <div role="radiogroup" aria-label="Financial RIP history time range" className="flex min-w-max gap-1">
      {FINANCIAL_RIP_WINDOWS.map((item) => (
        <button key={item.key} type="button" role="radio" aria-checked={value === item.key} aria-label={item.ariaLabel} disabled={disabled} onClick={() => onChange(item.key)} className={`min-h-9 min-w-11 rounded-md border px-2 text-[10px] font-semibold tracking-wide focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300/70 ${value === item.key ? RANKINGS_SELECTED_BORDERED_SURFACE : "border-[var(--border-subtle)] text-[var(--text-secondary)]"}`}>
          {item.label}
        </button>
      ))}
    </div>
  );
}

function MetricControls({ value, onChange, disabled = false }) {
  return <div className={`w-52 ${disabled ? "pointer-events-none opacity-60" : ""}`} aria-disabled={disabled}>
    <DarkSelect ariaLabel="Trend metric" eyebrow="Metric" value={value} onChange={onChange} options={TREND_METRICS.map((item) => ({ value: item.key, label: item.label, disabled }))} />
  </div>;
}

function LockedPreview() {
  return (
    <div data-financial-rip-history-locked className="relative mt-4 min-h-[20rem] overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[linear-gradient(180deg,rgba(30,41,59,.34),rgba(15,23,42,.2))]">
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
    </div>
  );
}

function EntitySelector({ candidates, selectedIds, onChange, mode, eraPresets = [], presetEraId, onPresetChange }) {
  const options = candidates.map((item) => ({
    id: item.entity_id,
    label: item.name,
  }));
  return (
    <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-start">
      {mode === "sets" ? (
        <MultiSelectFilter
          label="Era preset"
          name="financial-era-preset"
          options={eraPresets.map((era) => ({
            id: era.entity_id,
            label: era.name,
          }))}
          selectedIds={presetEraId ? [presetEraId] : []}
          onChange={(ids) => onPresetChange(nextSingleEraPreset(presetEraId, ids))}
          allLabel="Manual Sets"
          summaryNoun="Era"
          searchPlaceholder="Search Eras…"
          showChips={false}
        />
      ) : null}
      <MultiSelectFilter label={mode === "sets" ? "Sets" : "Eras"} name={`financial-${mode}`} options={options} selectedIds={selectedIds} onChange={onChange} allLabel={`Choose ${mode === "sets" ? "Sets" : "Eras"}`} summaryNoun={mode === "sets" ? "Sets" : "Eras"} searchPlaceholder={`Search ${mode === "sets" ? "Sets…" : "Eras…"}`} showChips={false} />
    </div>
  );
}

const MAX_FINANCIAL_RIP_SET_SELECTION = 5;
const WHEEL_LINE_PX = 16;

export default function FinancialRipHistoryChart({ targets = [], financialCohort = null, openingSets = [], eras = [], marketDate = null, sessionCache = null }) {
  const { canViewRankingsIntelligence: entitled, authStatus } = useRankingsAccess();
  const [mode, setMode] = useState("sets");
  const [metricKey, setMetricKey] = useState("financial");
  const [windowKey, setWindowKey] = useState("30D");
  const [setSelection, setSetSelection] = useState([]);
  const [eraSelection, setEraSelection] = useState([]);
  const [presetEraId, setPresetEraId] = useState(null);
  const [request, setRequest] = useState({
    status: "idle",
    view: null,
    key: null,
    pendingKey: null,
    error: null,
  });
  const [retryNonce, setRetryNonce] = useState(0);
  const [focusId, setFocusId] = useState(null);
  const [hoverId, setHoverId] = useState(null);
  const [pinnedDate, setPinnedDate] = useState(null);
  const seeded = useRef({ sets: false, eras: false });
  const [seededModes, setSeededModes] = useState({ sets: false, eras: false });
  const plotRef = useRef(null);
  const { setCandidates, eraCandidates } = useMemo(
    () =>
      buildFinancialRipCandidates({
        financialCohort,
        targets,
        openingSets,
        eras,
      }),
    [financialCohort, targets, openingSets, eras],
  );

  // Defaults are seeded exactly once.  An empty selection afterwards (Clear All) is a valid
  // user state and must never be silently re-populated.
  useEffect(() => {
    if (!seeded.current.sets) {
      if (!setCandidates.length) return;
      seeded.current.sets = true;
      setSeededModes((current) => ({ ...current, sets: true }));
      setSetSelection(setCandidates.slice(0, FINANCIAL_RIP_DEFAULT_SET_COUNT).map((item) => item.entity_id));
      return;
    }
    setSetSelection((current) => {
      const next = (presetEraId ? current : current.slice(0, MAX_FINANCIAL_RIP_SET_SELECTION)).filter((id) => setCandidates.some((item) => item.entity_id === id));
      return next.length === current.length ? current : next;
    });
  }, [presetEraId, setCandidates]);
  useEffect(() => {
    if (!seeded.current.eras) {
      if (!eraCandidates.length) return;
      seeded.current.eras = true;
      setSeededModes((current) => ({ ...current, eras: true }));
      setEraSelection(eraCandidates.map((item) => item.entity_id));
      return;
    }
    setEraSelection((current) => {
      const next = current.filter((id) => eraCandidates.some((item) => item.entity_id === id));
      return next.length === current.length ? current : next;
    });
  }, [eraCandidates]);

  const candidates = mode === "sets" ? setCandidates : eraCandidates;
  const selectedIds = mode === "sets" ? setSelection : eraSelection;
  const selected = useMemo(() => candidates.filter((item) => selectedIds.includes(item.entity_id)), [candidates, selectedIds]);
  const requestEntities = useMemo(() => financialRipRequestEntities(selected, request.view?.mode === mode ? request.view?.selected : [], seededModes[mode] ? candidates : []), [candidates, mode, request.view, seededModes, selected]);
  const knownFrom = request.view?.payload?.historyAvailableFrom || null;
  const knownThrough = request.view?.payload?.historyAvailableThrough || marketDate;
  const range = useMemo(() => financialRipWindowRange(windowKey, knownThrough, knownFrom), [windowKey, knownThrough, knownFrom]);
  const fetchRange = useMemo(() => financialRipWindowRange(windowKey, marketDate, windowKey === "ALL" ? null : knownFrom), [windowKey, marketDate, knownFrom]);
  const selectionKey = selected
    .map((item) => item.entity_id)
    .sort()
    .join(",");
  const requestKey = `${mode}:${selectionKey}:${fetchRange.startDate}:${fetchRange.endDate}:${retryNonce}`;

  useEffect(() => {
    if (
      !shouldFetchFinancialRipHistory({
        entitled,
        authStatus,
        selectedCount: requestEntities.length,
        startDate: fetchRange.startDate,
        endDate: fetchRange.endDate,
      })
    )
      return undefined;
    const loadedIds = new Set((request.view?.selected || []).map((item) => item.entity_id));
    if (request.view?.mode === mode && request.view?.windowKey === windowKey && selected.every((item) => loadedIds.has(item.entity_id))) return undefined;
    const commit = (payload) => ({
      status: "ready",
      view: {
        payload,
        selected: selected.map((item) => ({ ...item })),
        range: financialRipWindowRange(windowKey, payload?.historyAvailableThrough || marketDate, payload?.historyAvailableFrom || null),
        mode,
        windowKey,
      },
      key: requestKey,
      pendingKey: null,
      error: null,
    });
    const options = {
      sessionCache,
      startDate: fetchRange.startDate,
      endDate: fetchRange.endDate,
    };
    // A completed exact or superset entry (e.g. the prefetched 22-Set cohort) is applied
    // synchronously: no spinner, no network.
    const cached = peekFinancialHistory(requestEntities, options);
    if (cached !== undefined) {
      setRequest(commit(cached));
      return undefined;
    }
    let active = true;
    setRequest((current) => ({
      ...current,
      status: "loading",
      pendingKey: requestKey,
      error: null,
    }));
    readFinancialHistoryCached(requestEntities, options)
      .then((payload) => {
        if (active) setRequest(commit(payload));
      })
      .catch((error) => {
        if (active)
          setRequest((current) => ({
            ...current,
            status: "error",
            pendingKey: null,
            error: error?.message || "Trend history is temporarily unavailable.",
          }));
      });
    return () => {
      active = false;
    };
  }, [authStatus, entitled, fetchRange.endDate, fetchRange.startDate, marketDate, mode, request.view, requestEntities, requestKey, selected, sessionCache, windowKey]);

  const display = request.view?.mode === mode ? request.view : null;
  const chart = useMemo(() => buildTrendChartModel(display?.payload?.rows || [], selected, display?.range || range, metricKey), [display, metricKey, range, selected]);
  const activeMetric = trendMetric(metricKey);
  const names = useMemo(() => Object.fromEntries((display?.selected || []).map((item) => [item.entity_id, item.name])), [display]);
  const yDomain = useMemo(() => financialRipYAxisDomain(chart.points, chart.series), [chart]);
  const accessPending = authStatus !== "resolved" && authStatus !== "degraded";
  const seriesIds = useMemo(() => chart.series.map((item) => item.entity_id), [chart.series]);
  const activeFocus = resolveActiveFocus({
    persistentId: focusId,
    hoverId,
    seriesIds,
  });
  const drawSeries = useMemo(() => orderSeriesForDrawing(chart.series, activeFocus), [chart.series, activeFocus]);
  const pinnedPoint = useMemo(() => (pinnedDate ? chart.points.find((point) => point.date === pinnedDate) || null : null), [chart.points, pinnedDate]);

  // Focus is display-only; it follows what is actually plotted.
  useEffect(() => {
    if (focusId != null && !seriesIds.includes(focusId)) setFocusId(null);
  }, [focusId, seriesIds]);
  useEffect(() => {
    if (hoverId != null && !seriesIds.includes(hoverId)) setHoverId(null);
  }, [hoverId, seriesIds]);
  useEffect(() => {
    setPinnedDate(null);
  }, [mode, windowKey, selectionKey]);
  useEffect(() => {
    setFocusId(null);
    setHoverId(null);
  }, [mode]);
  useEffect(() => {
    if (!pinnedDate) return undefined;
    const onKey = (event) => {
      if (event.key === "Escape") setPinnedDate(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [pinnedDate]);

  // Wheel / trackpad over the plot scrolls the (pointer-transparent) hover tooltip when it
  // overflows.  Wheel inside a tooltip scroll region is left to native scrolling, and when the
  // tooltip is at its scroll limit the page scrolls normally.
  useEffect(() => {
    const node = plotRef.current;
    if (!node) return undefined;
    const onWheel = (event) => {
      if (event.target?.closest?.(`[${TOOLTIP_SCROLL_ATTR}]`)) return;
      const region = node.querySelector(`[data-financial-history-tooltip][data-pinned="false"] [${TOOLTIP_SCROLL_ATTR}]`);
      if (!region || region.scrollHeight <= region.clientHeight + 1) return;
      const delta = event.deltaMode === 1 ? event.deltaY * WHEEL_LINE_PX : event.deltaY;
      const atTop = region.scrollTop <= 0 && delta < 0;
      const atBottom = region.scrollTop + region.clientHeight >= region.scrollHeight - 1 && delta > 0;
      if (atTop || atBottom) return;
      region.scrollTop += delta;
      event.preventDefault();
    };
    node.addEventListener("wheel", onWheel, { passive: false });
    return () => node.removeEventListener("wheel", onWheel);
  }, [display]);

  const changeSelection = (ids) => {
    if (mode === "sets") {
      setPresetEraId(null);
      setSetSelection(ids.slice(0, MAX_FINANCIAL_RIP_SET_SELECTION));
    } else setEraSelection(ids);
  };
  const selectEraSets = (eraId) => {
    setPresetEraId(eraId);
    const ids = setIdsForEra(setCandidates, eraId);
    if (ids.length) setSetSelection(ids);
  };
  const removeSeries = useCallback(
    (id) => {
      if (mode === "sets") setSetSelection((current) => current.filter((item) => item !== id));
      else setEraSelection((current) => current.filter((item) => item !== id));
      setFocusId((current) => (current === id ? null : current));
      setHoverId((current) => (current === id ? null : current));
    },
    [mode],
  );
  const clearAll = useCallback(() => {
    if (mode === "sets") {
      setPresetEraId(null);
      setSetSelection([]);
    } else setEraSelection([]);
    setFocusId(null);
    setHoverId(null);
    setPinnedDate(null);
  }, [mode]);
  const pinFromChart = (state) => {
    const date = state?.activePayload?.[0]?.payload?.date || chart.points[state?.activeTooltipIndex]?.date || null;
    if (date) setPinnedDate((current) => (current === date ? null : date));
  };

  return (
    <section className="mt-5 border-t border-[var(--border-subtle)] pt-5" data-financial-rip-history-chart>
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h3 className="text-lg font-semibold text-[var(--text-primary)]">Trend</h3>
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-[var(--text-secondary)]">{activeMetric.subtitle}</p>
        </div>
        <div className="flex max-w-full flex-col gap-2 overflow-x-auto sm:flex-row sm:items-center">
          <ModeControls mode={mode} onChange={setMode} disabled={!entitled || accessPending} />
          <MetricControls value={metricKey} onChange={setMetricKey} disabled={!entitled || accessPending} />
          <WindowControls value={windowKey} onChange={setWindowKey} disabled={!entitled || accessPending} />
        </div>
      </div>

      {accessPending ? (
        <div className="mt-4 flex h-[20rem] items-center justify-center rounded-xl border border-[var(--border-subtle)] text-sm text-[var(--text-secondary)] sm:h-[24rem] desk:h-[28rem]" aria-busy="true">
          Loading access…
        </div>
      ) : !entitled ? (
        <LockedPreview />
      ) : (
        <>
          <EntitySelector candidates={candidates} selectedIds={selectedIds} onChange={changeSelection} mode={mode} eraPresets={eraCandidates} presetEraId={presetEraId} onPresetChange={(eraId) => (eraId ? selectEraSets(eraId) : setPresetEraId(null))} />

          <>
            <FinancialRipHistoryLegend series={chart.series} overallLabel={activeMetric.overallLabel} showOverall={Boolean(display)} persistentFocusId={focusId} onToggleFocus={(id) => setFocusId((current) => toggleFocus(current, id))} onHoverFocus={setHoverId} onRemove={removeSeries} onClearAll={clearAll} updating={request.status === "loading" && Boolean(display)} />

            {!display && request.status === "loading" ? (
              <div className="mt-4 flex h-[20rem] items-center justify-center rounded-xl border border-[var(--border-subtle)] text-sm text-[var(--text-secondary)] sm:h-[24rem] desk:h-[28rem]" aria-busy="true">
                Loading Trend history…
              </div>
            ) : !display && request.status === "error" ? (
              <div className="mt-4 flex h-[20rem] flex-col items-center justify-center rounded-xl border border-[var(--border-subtle)] px-4 text-center sm:h-[24rem] desk:h-[28rem]">
                <p className="text-sm text-[var(--text-secondary)]">Trend history is temporarily unavailable.</p>
                <button type="button" onClick={() => setRetryNonce((value) => value + 1)} className="mt-3 min-h-10 rounded-md border border-[var(--border-subtle)] px-4 text-sm font-semibold">
                  Retry
                </button>
              </div>
            ) : display ? (
              <>
                <div ref={plotRef} className="relative" data-financial-history-plot data-active-focus={activeFocus || undefined}>
                  <ChartFrame className="mt-4 h-[20rem] sm:h-[24rem] desk:h-[28rem]">
                    <ResponsiveContainer>
                      <LineChart data={chart.points} margin={{ top: 12, right: 14, bottom: 6, left: 0 }} onClick={pinFromChart}>
                        <CartesianGrid stroke="rgba(148,163,184,.16)" strokeDasharray="2 8" vertical={false} />
                        <XAxis dataKey="timestamp" type="number" scale="time" domain={["dataMin", "dataMax"]} tickFormatter={(value) => labelDate(new Date(value).toISOString().slice(0, 10)).replace(/, \d{4}/, "")} minTickGap={28} tick={{ fill: "#94a3b8", fontSize: 10 }} />
                        <YAxis domain={yDomain} tickFormatter={(value) => formatTrendValue(value, metricKey)} tick={{ fill: "#94a3b8", fontSize: 10 }} width={58} />
                        <Tooltip content={<ChartTooltip series={chart.series} metricKey={metricKey} overallLabel={activeMetric.overallLabel} focusId={activeFocus} suppressed={Boolean(pinnedPoint)} />} />
                        <Line type="linear" dataKey="overallTrend" name={activeMetric.overallLabel} stroke="#ffffff" strokeOpacity={0.9} strokeWidth={3} strokeDasharray="9 7" dot={false} activeDot={{ r: 4 }} connectNulls={false} isAnimationActive={false} />
                        {drawSeries.map((item) => {
                          const emphasis = seriesEmphasis(item.entity_id, activeFocus);
                          return <Line key={item.entity_id} type="linear" dataKey={item.key} name={item.name} stroke={item.color} strokeOpacity={emphasis.strokeOpacity} strokeWidth={emphasis.strokeWidth} dot={emphasis.showDots ? { r: 2 } : false} activeDot={emphasis.showDots ? { r: 5 } : false} connectNulls={false} isAnimationActive={false} />;
                        })}
                      </LineChart>
                    </ResponsiveContainer>
                  </ChartFrame>
                  {pinnedPoint ? (
                    <div data-financial-history-pinned className="absolute right-2 top-5 z-30">
                      <FinancialRipTooltipContent point={pinnedPoint} series={chart.series} metricKey={metricKey} overallLabel={activeMetric.overallLabel} focusId={activeFocus} pinned onClose={() => setPinnedDate(null)} />
                    </div>
                  ) : null}
                </div>
                {windowKey === "1D" && chart.points.length === 1 ? <p role="status" className="mt-2 text-xs text-[var(--text-secondary)]">Previous certified observation unavailable.</p> : null}
                <p className="mt-1 text-[10px] text-[var(--text-secondary)]">Click or tap the chart to pin the values for a date; scroll the list for long selections.</p>
                <ol className="sr-only" aria-label={`Visible ${activeMetric.label} observations`}>
                  {chart.points.flatMap((point) =>
                    Object.entries(point.entities).map(([id, detail]) => (
                      <li key={`${point.date}:${id}`}>
                        {labelDate(point.date)}, {names[id]} {activeMetric.label} {formatTrendValue(detail.trendValue, metricKey)}, {activeMetric.overallLabel} {formatTrendValue(detail.overallFinancialRip, metricKey)}.
                      </li>
                    )),
                  )}
                </ol>
                <p className="mt-2 text-[10px] text-[var(--text-secondary)]">
                  Exact certified publications only
                  {display.payload?.historyAvailableFrom ? ` · History available from ${labelDate(display.payload.historyAvailableFrom)}` : ""}
                  {display.payload?.historyAvailableThrough ? ` through ${labelDate(display.payload.historyAvailableThrough)}` : ""}. Missing publication dates remain gaps.
                </p>
                {request.status === "error" ? (
                  <p role="alert" className="mt-2 text-xs text-red-300">
                    The latest refresh failed, so the last successful history remains visible.{" "}
                    <button type="button" onClick={() => setRetryNonce((value) => value + 1)} className="underline">
                      Retry
                    </button>
                  </p>
                ) : null}
              </>
            ) : (
              <div className="mt-4 h-[20rem] rounded-xl border border-[var(--border-subtle)] sm:h-[24rem] desk:h-[28rem]" />
            )}
          </>
        </>
      )}
    </section>
  );
}
