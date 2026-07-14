"use client";

import { useEffect, useMemo, useState } from "react";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import ChartFrame from "@/components/explore/ChartFrame";
import { POSITIVE_VALUE_COLOR } from "@/lib/explore/interpretationTone";
import {
  filterHistoryPointsForDeltaWindow,
  getSelectedDeltaWindowFromHistory,
} from "@/lib/explore/marketDeltaWindows.mjs";
import {
  forwardFillDailyHistoryThroughDate,
  normalizeHistoryTrendPoint,
  patchLatestHistoryRowWithSummaryRatios,
} from "./packValueHistoryNormalization.mjs";
import {
  buildPerformanceTooltipRows,
  formatPerformanceCurrency,
  formatPerformanceRatio,
  formatReturnMultiple,
  getPerformanceSeriesLabels,
} from "./performanceVsCostFormatting.mjs";
import { formatHistoryDate } from "./historyDateFormatting.mjs";

// ─── Color tokens for this chart only ────────────────────────────────────────
const HISTORICAL_TREND_COLORS = {
  meanToCost:   POSITIVE_VALUE_COLOR,          // shared positive value signal
  meanLabel:    "rgba(183,245,231,0.86)",
  medianToCost: "rgba(99,130,191,0.90)",      // blue-slate — secondary, visible but not competing
  medianLabel:  "rgba(180,200,230,0.82)",
  p95ToCost:    "rgba(34,211,238,0.95)",      // electric cyan — high-end upside/chase signal
  p95Label:     "rgba(165,243,252,0.86)",
  breakEven:    "rgba(255,255,255,0.42)",
};

// ─── Helpers ─────────────────────────────────────────────────────────────────
function toNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function firstFiniteNumber(raw, keys) {
  for (const key of keys) {
    const value = toNumber(raw?.[key]);
    if (value !== null) {
      return value;
    }
  }
  return null;
}

function firstFiniteMetric(raw, keys) {
  for (const key of keys) {
    const value = toNumber(raw?.[key]);
    if (value !== null) {
      return { key, value };
    }
  }
  return { key: null, value: null };
}

function formatRatio(value) {
  return formatPerformanceRatio(value);
}

function formatCurrency(value) {
  return formatPerformanceCurrency(value);
}

function resolveDollarValue(explicitValue, ratioValue, packCostValue) {
  const explicit = toNumber(explicitValue);
  const ratio = toNumber(ratioValue);
  const packCost = toNumber(packCostValue);

  if (explicit !== null) {
    if (ratio !== null && packCost !== null) {
      const derived = ratio * packCost;
      if (Math.abs(explicit) < 1e-9 && Math.abs(derived) > 1e-6) {
        return derived;
      }
    }
    return explicit;
  }

  if (ratio === null || packCost === null) {
    return null;
  }

  return ratio * packCost;
}

function normalizeReturnMetrics(ratioValue, explicitValue, packCostValue) {
  const ratio = toNumber(ratioValue);
  const explicit = toNumber(explicitValue);
  const packCost = toNumber(packCostValue);

  if (explicit !== null) {
    return {
      returnValue: explicit,
      ratioValue: packCost !== null && packCost > 0 ? explicit / packCost : null,
    };
  }

  if (ratio === null || ratio < 0) {
    return {
      returnValue: null,
      ratioValue: null,
    };
  }

  return {
    returnValue: packCost !== null && packCost > 0 ? ratio * packCost : null,
    ratioValue: ratio,
  };
}

function normalizeHistoryPoint(raw, index, fallbackPackCost) {
  return normalizeHistoryTrendPoint(raw, index, fallbackPackCost);
}

/**
 * Compute a clean Y-axis upper bound for ratio series that may include P95
 * values well above 1.25x. Uses a stepped ceiling so the axis reads naturally.
 */
function getHistoricalRatioYAxisMax(points) {
  let maxRatio = 1;
  for (const pt of points) {
    const mean   = toNumber(pt.meanCostRatio);
    const median = toNumber(pt.medianCostRatio);
    const p95    = toNumber(pt.p95CostRatio);
    if (mean   !== null) maxRatio = Math.max(maxRatio, mean);
    if (median !== null) maxRatio = Math.max(maxRatio, median);
    if (p95    !== null) maxRatio = Math.max(maxRatio, p95);
  }

  const padded = maxRatio * 1.12;

  if (padded <= 1.25) return 1.25;
  if (padded <= 2.0)  return 2.0;
  if (padded <= 3.0)  return 3.0;
  if (padded <= 4.0)  return 4.0;
  if (padded <= 5.0)  return 5.0;
  return Math.ceil(padded);
}

function buildRatioTicks(upperBound) {
  const safeUpper = Number.isFinite(upperBound) ? upperBound : 1.25;
  // Use 0.5-step ticks for larger scales to avoid a crowded axis
  const step = safeUpper > 2.5 ? 0.5 : 0.25;
  const roundedUpper = Math.ceil(safeUpper / step) * step;
  const ticks = [];
  for (let value = 0; value <= roundedUpper + 0.0001; value += step) {
    ticks.push(Number(value.toFixed(2)));
  }
  return ticks;
}

function formatShortDate(value) {
  if (!value) {
    return "\u2014";
  }
  return formatHistoryDate(value, { month: "short", day: "numeric" }) || String(value);
}

function formatLongDate(value) {
  if (!value) {
    return "\u2014";
  }
  return formatHistoryDate(value, {
    year: "numeric",
    month: "short",
    day: "numeric",
  }) || String(value);
}

// ─── Tooltip ─────────────────────────────────────────────────────────────────
// Rows with a mapped color here are the chart's plotted lines and get top billing
// (colored dot + larger value) so they're readable at a glance; everything else
// (break-even, pack cost) is reference context and reads as a smaller footer line.
const TOOLTIP_ROW_COLORS = {
  p95: HISTORICAL_TREND_COLORS.p95ToCost,
  average: HISTORICAL_TREND_COLORS.meanToCost,
  typical: HISTORICAL_TREND_COLORS.medianToCost,
};

function TrendTooltip({ active, payload, packCost, variant = "market" }) {
  if (!active || !payload?.length) {
    return null;
  }

  const row = payload[0]?.payload;
  if (!row) {
    return null;
  }

  const tooltipRows = buildPerformanceTooltipRows(row, packCost, variant);
  const primaryRows = tooltipRows.filter((entry) => TOOLTIP_ROW_COLORS[entry.key]);
  const referenceRows = tooltipRows.filter((entry) => !TOOLTIP_ROW_COLORS[entry.key]);

  return (
    <div className="min-w-[11rem] max-w-[16rem] rounded-lg border border-[var(--border-subtle)] bg-[rgba(2,6,23,0.96)] px-2.5 py-2 text-left shadow-[0_14px_32px_rgba(0,0,0,0.38)]">
      <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{formatLongDate(row.snapshotDate)}</p>
      <div className="mt-1.5 space-y-1">
        {primaryRows.map((entry) => (
          <div key={entry.key} className="flex items-center justify-between gap-3">
            <span className="inline-flex items-center gap-1.5 text-[11px] text-[var(--text-secondary)]">
              <span className="h-1.5 w-1.5 flex-none rounded-full" style={{ backgroundColor: TOOLTIP_ROW_COLORS[entry.key] }} />
              {entry.label}
            </span>
            <span className="text-sm font-semibold tabular-nums text-[var(--text-primary)]">{entry.value}</span>
          </div>
        ))}
      </div>
      {referenceRows.length > 0 ? (
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-0.5 border-t border-[var(--border-subtle)] pt-1.5">
          {referenceRows.map((entry) => (
            <span key={entry.key} className="text-[10px] text-[var(--text-secondary)]">
              {entry.label} <span className="font-semibold text-[var(--text-primary)]">{entry.value}</span>
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

// ─── Final-point labels ───────────────────────────────────────────────────────
function RatioPointLabel({ x, y, value, dollarValue = null }) {
  const parsed = toNumber(value);
  if (parsed === null || !Number.isFinite(x) || !Number.isFinite(y)) {
    return null;
  }

  const dollar = toNumber(dollarValue);
  const labelX = x + 8;
  const labelY = y + 3;

  return (
    <g opacity={0.96}>
      <text x={labelX} y={labelY} textAnchor="start" fontSize={10.5} fontWeight={650} fill="rgba(248,250,252,0.94)">
        <tspan>{formatReturnMultiple(parsed)}</tspan>
        {dollar !== null ? (
          <tspan className="hidden sm:inline" dx="3" fill="rgba(203,213,225,0.78)" fontWeight={600}>
            ({formatCurrency(Math.abs(dollar))})
          </tspan>
        ) : null}
      </text>
    </g>
  );
}

// ─── Empty state ──────────────────────────────────────────────────────────────
// Compact by design: a settled "no data yet" note must not occupy a
// chart-sized blank panel (Phase 9C loading-presentation polish).
function EmptyTrendState({ flush = false }) {
  return (
    <p className={[
      "rounded-xl px-4 py-3 text-sm text-[var(--text-secondary)]",
      flush
        ? "border border-dashed border-[rgba(255,255,255,0.06)] bg-transparent"
        : "border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)]/60",
    ].join(" ")}>
      Performance history isn&apos;t available for this set yet. The trend appears after multiple daily simulation snapshots.
    </p>
  );
}

// ─── Legend toggle button ─────────────────────────────────────────────────────
function LegendToggle({ active, onToggle, activeColor, inactiveColor, label }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={active}
      className={`inline-flex items-center gap-1.5 rounded px-2 py-1 transition-colors ${
        active
          ? "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          : "text-[var(--text-secondary)]/50 hover:text-[var(--text-secondary)]"
      }`}
    >
      <span
        className="inline-block h-0.5 w-5 rounded"
        style={{ backgroundColor: active ? activeColor : inactiveColor }}
      />
      {label}
    </button>
  );
}

// ─── Main chart ───────────────────────────────────────────────────────────────
function MarketWindowSelector({ windows, value, onChange }) {
  const windowOptions = Array.isArray(windows) ? windows.filter(Boolean) : [];
  if (windowOptions.length <= 1) {
    return null;
  }

  return (
    <div className="flex min-w-0 flex-wrap gap-1.5">
      {windowOptions.map((entry) => {
        const isActive = entry.key === value;
        return (
          <button
            key={`performance-window:${entry.key}`}
            type="button"
            onClick={() => onChange(entry.key)}
            aria-pressed={isActive}
            className={[
              "rounded-md border px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] transition-colors",
              isActive
                ? "border-[rgba(45,212,191,0.34)] bg-[rgba(45,212,191,0.10)] text-[rgb(45,212,191)]"
                : "border-[var(--border-subtle)] bg-[var(--surface-page)]/42 text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
            ].join(" ")}
          >
            {entry.label}
          </button>
        );
      })}
    </div>
  );
}

export default function PackValueHistoryChart({
  historyTrend = [],
  packCost = null,
  summary = null,
  flush = false,
  variant = "market",
  marketAsOfDate = null,
}) {
  const [showMeanLine,   setShowMeanLine]   = useState(true);
  const [showMedianLine, setShowMedianLine] = useState(true);
  const [showP95Line,    setShowP95Line]    = useState(true);
  const [selectedWindowKey, setSelectedWindowKey] = useState(null);

  // "simulation" keeps the labels technical (…vs Cost / 50th / 95th percentile)
  // for the Simulation Results view; "market" is Overview's simplified reader copy.
  const seriesLabels = getPerformanceSeriesLabels(variant);

  const fullChartData = useMemo(
    () => {
      const normalizedRows = (Array.isArray(historyTrend) ? historyTrend : [])
        .map((row, index) => normalizeHistoryPoint(row, index, packCost));

      if (normalizedRows.length === 0) {
        return [];
      }

      const latestRow = normalizedRows[normalizedRows.length - 1];
      const effectiveLatestPackCost = toNumber(latestRow.packCost) ?? toNumber(summary?.pack_cost) ?? toNumber(packCost);
      const meanValueSummary = firstFiniteNumber(summary, ["average_pack_value", "simulated_mean_pack_value", "mean_pack_value", "mean_value"]);
      const medianValueSummary = firstFiniteNumber(summary, ["typical_pack_value", "simulated_median_pack_value", "median_pack_value", "median_value"]);

      const meanRatioSummary =
        firstFiniteNumber(summary, ["mean_value_to_cost_ratio", "average_return_vs_cost", "mean_cost_ratio", "average_return_ratio"]) ??
        (meanValueSummary !== null && effectiveLatestPackCost !== null && effectiveLatestPackCost > 0
          ? meanValueSummary / effectiveLatestPackCost
          : null);

      const medianRatioSummary =
        firstFiniteNumber(summary, ["median_value_to_cost_ratio", "typical_return_vs_cost", "typical_value_to_cost_ratio", "median_cost_ratio", "typical_return_ratio"]) ??
        (medianValueSummary !== null && effectiveLatestPackCost !== null && effectiveLatestPackCost > 0
          ? medianValueSummary / effectiveLatestPackCost
          : null);

      const patchedLatestRow = patchLatestHistoryRowWithSummaryRatios(latestRow, {
        meanRatioSummary,
        medianRatioSummary,
        effectivePackCost: effectiveLatestPackCost,
      });

      const rows = [...normalizedRows.slice(0, -1), patchedLatestRow].filter(
        (row) => row.snapshotDate && (row.meanCostRatio !== null || row.medianCostRatio !== null)
      );

      // Clamped/filled through the canonical marketAsOfDate; when absent the
      // helper stops at the latest real observation — never runtime today.
      return forwardFillDailyHistoryThroughDate(rows, {
        dateField: "snapshotDate",
        valueKeys: ["meanCostRatio", "medianCostRatio", "p95CostRatio"],
        endDateKey: marketAsOfDate,
      });
    },
    [historyTrend, packCost, summary, marketAsOfDate]
  );

  const {
    windows: availableDeltaWindows,
    effectiveKey: effectiveWindowKey,
    selectedWindow: selectedDeltaWindow,
  } = useMemo(
    () => getSelectedDeltaWindowFromHistory(fullChartData, {
      selectedKey: selectedWindowKey,
      preferredKey: "30D",
      dateKey: "snapshotDate",
      valueKey: "meanCostRatio",
    }),
    [fullChartData, selectedWindowKey]
  );

  const chartData = useMemo(
    () => filterHistoryPointsForDeltaWindow(fullChartData, selectedDeltaWindow, { dateKey: "snapshotDate" }),
    [fullChartData, selectedDeltaWindow]
  );

  useEffect(() => {
    if (!effectiveWindowKey || selectedWindowKey === effectiveWindowKey) {
      return;
    }
    setSelectedWindowKey(effectiveWindowKey);
  }, [effectiveWindowKey, selectedWindowKey]);

  // Determine whether any row actually has P95 data so we can hide the toggle
  // gracefully when the backend view does not yet expose that column.
  const hasP95Data = useMemo(
    () => chartData.some((row) => row.p95CostRatio !== null),
    [chartData]
  );

  const yAxisUpperBound = useMemo(() => getHistoricalRatioYAxisMax(chartData), [chartData]);
  const yAxisTicks      = useMemo(() => buildRatioTicks(yAxisUpperBound), [yAxisUpperBound]);

  const latestDataIndex = chartData.length - 1;

  const breakEvenLabel = useMemo(() => {
    const cost = toNumber(packCost);
    if (cost === null) {
      return "Break-even / Profit Line";
    }
    return `1.0x Break-even (${formatCurrency(cost)})`;
  }, [packCost]);

  if (chartData.length < 2) {
    return <EmptyTrendState flush={flush} />;
  }

  return (
    <div className={flush ? "flex h-full min-h-[26rem] flex-col" : "rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 p-4 sm:p-5"}>
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <MarketWindowSelector
            windows={availableDeltaWindows}
            value={effectiveWindowKey}
            onChange={setSelectedWindowKey}
          />
        </div>

        <div className="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-2 text-[11px]">
          {/* TODO(perf-vs-cost): Optional future mode toggle (Standard | Include God Pull) if we need a P99 line without changing default readability. */}
          <LegendToggle
            active={showMeanLine}
            onToggle={() => setShowMeanLine((c) => !c)}
            activeColor={HISTORICAL_TREND_COLORS.meanToCost}
            inactiveColor="rgba(45,212,191,0.25)"
            label={seriesLabels.mean}
          />
          <LegendToggle
            active={showMedianLine}
            onToggle={() => setShowMedianLine((c) => !c)}
            activeColor={HISTORICAL_TREND_COLORS.medianToCost}
            inactiveColor="rgba(99,130,191,0.25)"
            label={seriesLabels.median}
          />
          {hasP95Data && (
            <LegendToggle
              active={showP95Line}
              onToggle={() => setShowP95Line((c) => !c)}
              activeColor={HISTORICAL_TREND_COLORS.p95ToCost}
              inactiveColor="rgba(34,211,238,0.20)"
              label={seriesLabels.p95}
            />
          )}
        </div>
      </div>

      <ChartFrame className={flush ? "mt-3 min-h-[24rem] w-full flex-1" : "mt-4 h-[20rem] w-full sm:h-[23rem]"}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 10, right: 112, left: 6, bottom: 14 }}>
            <CartesianGrid stroke="var(--border-subtle)" strokeOpacity={0.28} strokeDasharray="2 8" vertical={false} />

            <XAxis
              dataKey="snapshotDate"
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
              tickFormatter={formatShortDate}
              tickMargin={12}
              minTickGap={22}
              interval="preserveStartEnd"
            />

            <YAxis
              domain={[0, yAxisUpperBound]}
              ticks={yAxisTicks}
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
              tickFormatter={formatRatio}
              tickMargin={10}
              width={60}
            />

            <Tooltip content={<TrendTooltip packCost={packCost} variant={variant} />} cursor={{ stroke: "rgba(255,255,255,0.16)", strokeWidth: 1 }} />

            <ReferenceLine
              y={1}
              stroke={HISTORICAL_TREND_COLORS.breakEven}
              strokeDasharray="6 6"
              strokeWidth={1}
              label={{
                value: breakEvenLabel,
                position: "insideTopRight",
                fill: "var(--text-secondary)",
                fontSize: 11,
              }}
            />

            {/* Big Hit Upside rendered below Expected Value so Expected Value stays visually on top. */}
            {hasP95Data && showP95Line ? (
              <Line
                type="monotone"
                dataKey="p95CostRatio"
                name={seriesLabels.p95}
                stroke={HISTORICAL_TREND_COLORS.p95ToCost}
                strokeWidth={2.5}
                dot={{ r: 2.5, fill: HISTORICAL_TREND_COLORS.p95ToCost, strokeWidth: 0 }}
                label={({ x, y, value, index }) =>
                  index === latestDataIndex
                    ? <RatioPointLabel x={x} y={y} value={value} dollarValue={chartData[index]?.p95Value} />
                    : null
                }
                activeDot={{ r: 4, stroke: "var(--surface-page)", strokeWidth: 2 }}
                connectNulls
                isAnimationActive={false}
              />
            ) : null}

            {showMeanLine ? (
              <Line
                type="monotone"
                dataKey="meanCostRatio"
                name={seriesLabels.mean}
                stroke={HISTORICAL_TREND_COLORS.meanToCost}
                strokeWidth={2.5}
                dot={{ r: 2.5, fill: HISTORICAL_TREND_COLORS.meanToCost, strokeWidth: 0 }}
                label={({ x, y, value, index }) =>
                  index === latestDataIndex
                    ? <RatioPointLabel x={x} y={y} value={value} dollarValue={chartData[index]?.meanValue} />
                    : null
                }
                activeDot={{ r: 4, stroke: "var(--surface-page)", strokeWidth: 2 }}
                connectNulls
                isAnimationActive={false}
              />
            ) : null}

            {showMedianLine ? (
              <Line
                type="monotone"
                dataKey="medianCostRatio"
                name={seriesLabels.median}
                stroke={HISTORICAL_TREND_COLORS.medianToCost}
                strokeWidth={2}
                dot={{ r: 2, fill: HISTORICAL_TREND_COLORS.medianToCost, strokeWidth: 0 }}
                label={({ x, y, value, index }) =>
                  index === latestDataIndex
                    ? <RatioPointLabel x={x} y={y} value={value} dollarValue={chartData[index]?.medianValue} />
                    : null
                }
                activeDot={{ r: 3.5, stroke: "var(--surface-page)", strokeWidth: 2 }}
                connectNulls
                isAnimationActive={false}
              />
            ) : null}
          </LineChart>
        </ResponsiveContainer>
      </ChartFrame>
    </div>
  );
}
