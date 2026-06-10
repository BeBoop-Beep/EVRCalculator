"use client";

import { useMemo, useState } from "react";

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

import InfoPopover from "@/components/ui/InfoPopover";
import {
  normalizeHistoryTrendPoint,
  patchLatestHistoryRowWithSummaryRatios,
} from "./packValueHistoryNormalization.mjs";

// ─── Color tokens for this chart only ────────────────────────────────────────
const HISTORICAL_TREND_COLORS = {
  meanToCost:   "rgba(20,184,166,0.98)",      // emerald/teal — primary value signal
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
  const parsed = toNumber(value);
  if (parsed === null) {
    return "\u2014";
  }
  return `${parsed.toFixed(2)}x`;
}

function formatCurrency(value) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return "\u2014";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(parsed);
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
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(date);
}

function formatLongDate(value) {
  if (!value) {
    return "\u2014";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(date);
}

// ─── Tooltip ─────────────────────────────────────────────────────────────────
function TrendTooltip({ active, payload, packCost }) {
  if (!active || !payload?.length) {
    return null;
  }

  const row = payload[0]?.payload;
  if (!row) {
    return null;
  }

  const meanRatio = toNumber(row.meanCostRatio);
  const medianRatio = toNumber(row.medianCostRatio);
  const p95Ratio = toNumber(row.p95CostRatio);
  const effectivePackCost = toNumber(row.packCost) ?? toNumber(packCost);

  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)]/95 px-3 py-2 shadow-[0_16px_40px_rgba(0,0,0,0.35)] backdrop-blur-sm">
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Date</p>
      <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">{formatLongDate(row.snapshotDate)}</p>
      <p className="mt-2 text-xs text-[var(--text-secondary)]">
        Average Return <span className="font-semibold text-[var(--text-primary)]">{formatRatio(meanRatio)}</span>{" "}
        <span className="text-[var(--text-secondary)]">({formatCurrency(row.meanValue)})</span>
      </p>
      <p className="text-xs text-[var(--text-secondary)]">
        Typical Return <span className="font-semibold text-[var(--text-primary)]">{formatRatio(medianRatio)}</span>{" "}
        <span className="text-[var(--text-secondary)]">({formatCurrency(row.medianValue)})</span>
      </p>
      {p95Ratio !== null && (
        <p className="text-xs text-[var(--text-secondary)]">
          Big Hit Upside <span className="font-semibold text-[var(--text-primary)]">{formatRatio(p95Ratio)}</span>{" "}
          <span className="text-[var(--text-secondary)]">({formatCurrency(row.p95Value)})</span>
        </p>
      )}
      <p className="text-xs text-[var(--text-secondary)]">
        Break-even <span className="font-semibold text-[var(--text-primary)]">1.00x</span>
      </p>
      <p className="text-xs text-[var(--text-secondary)]">
        Pack Cost <span className="font-semibold text-[var(--text-primary)]">{formatCurrency(effectivePackCost)}</span>
      </p>
    </div>
  );
}

// ─── Final-point labels ───────────────────────────────────────────────────────
function RatioPointLabel({ x, y, value, fillColor, dy = -10 }) {
  const parsed = toNumber(value);
  if (parsed === null || !Number.isFinite(x) || !Number.isFinite(y)) {
    return null;
  }

  return (
    <text x={x + 8} y={y + dy} textAnchor="start" fontSize={10} fill={fillColor} opacity={0.8}>
      {formatRatio(parsed)}
    </text>
  );
}

// ─── Empty state ──────────────────────────────────────────────────────────────
function EmptyTrendState() {
  return (
    <div className="flex min-h-[24rem] flex-col items-center justify-center rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)]/60 px-6 py-10 text-center">
      <p className="max-w-md text-sm text-[var(--text-secondary)]">
        Historical trend will appear after multiple daily simulation snapshots.
      </p>
    </div>
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
export default function PackValueHistoryChart({ historyTrend = [], packCost = null, summary = null }) {
  const [showMeanLine,   setShowMeanLine]   = useState(true);
  const [showMedianLine, setShowMedianLine] = useState(true);
  const [showP95Line,    setShowP95Line]    = useState(true);

  const historicalTrendInfo = (
    <div className="space-y-1.5 text-left">
      <p className="font-semibold text-[var(--text-primary)]">Historical Pack Value vs Cost</p>
      <ul className="space-y-1 pl-3 text-[var(--text-secondary)]">
        <li className="flex gap-2"><span className="flex-none">•</span><span>Average Return compares average simulated pack value to pack cost over time.</span></li>
        <li className="flex gap-2"><span className="flex-none">•</span><span>Typical Return compares typical simulated pack value to pack cost over time.</span></li>
        <li className="flex gap-2"><span className="flex-none">•</span><span>Big Hit Upside shows the 95th-percentile outcome versus pack cost.</span></li>
        <li className="flex gap-2"><span className="flex-none">•</span><span>1.0x is break-even. Above 1.0x means simulated value exceeded pack cost.</span></li>
        <li className="flex gap-2"><span className="flex-none">•</span><span>The break-even label includes the estimated pack market price when available.</span></li>
      </ul>
    </div>
  );

  const chartData = useMemo(
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

      return [...normalizedRows.slice(0, -1), patchedLatestRow].filter(
        (row) => row.snapshotDate && (row.meanCostRatio !== null || row.medianCostRatio !== null)
      );
    },
    [historyTrend, packCost, summary]
  );

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
    return <EmptyTrendState />;
  }

  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Historical Pack Value vs Cost</p>
          <InfoPopover text={historicalTrendInfo} />
        </div>

        <div className="flex flex-wrap items-center gap-2 text-[11px]">
          {/* TODO(perf-vs-cost): Optional future mode toggle (Standard | Include God Pull) if we need a P99 line without changing default readability. */}
          <LegendToggle
            active={showMeanLine}
            onToggle={() => setShowMeanLine((c) => !c)}
            activeColor={HISTORICAL_TREND_COLORS.meanToCost}
            inactiveColor="rgba(20,184,166,0.25)"
            label="Average Return"
          />
          <LegendToggle
            active={showMedianLine}
            onToggle={() => setShowMedianLine((c) => !c)}
            activeColor={HISTORICAL_TREND_COLORS.medianToCost}
            inactiveColor="rgba(99,130,191,0.25)"
            label="Typical Return"
          />
          {hasP95Data && (
            <LegendToggle
              active={showP95Line}
              onToggle={() => setShowP95Line((c) => !c)}
              activeColor={HISTORICAL_TREND_COLORS.p95ToCost}
              inactiveColor="rgba(34,211,238,0.20)"
              label="Big Hit Upside"
            />
          )}
        </div>
      </div>

      <div className="mt-4 h-[20rem] w-full sm:h-[23rem]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 10, right: 52, left: 0, bottom: 8 }}>
            <CartesianGrid stroke="var(--border-subtle)" strokeOpacity={0.28} strokeDasharray="2 8" vertical={false} />

            <XAxis
              dataKey="snapshotDate"
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
              tickFormatter={formatShortDate}
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
              width={52}
            />

            <Tooltip content={<TrendTooltip packCost={packCost} />} cursor={{ stroke: "rgba(255,255,255,0.16)", strokeWidth: 1 }} />

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

            {/* Big Hit Upside — rendered below Average Return so Average Return stays visually on top */}
            {hasP95Data && showP95Line ? (
              <Line
                type="monotone"
                dataKey="p95CostRatio"
                name="Big Hit Upside"
                stroke={HISTORICAL_TREND_COLORS.p95ToCost}
                strokeWidth={2.5}
                dot={{ r: 2.5, fill: HISTORICAL_TREND_COLORS.p95ToCost, strokeWidth: 0 }}
                label={({ x, y, value, index }) =>
                  index === latestDataIndex
                    ? <RatioPointLabel x={x} y={y} value={value} fillColor={HISTORICAL_TREND_COLORS.p95Label} dy={-10} />
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
                name="Average Return"
                stroke={HISTORICAL_TREND_COLORS.meanToCost}
                strokeWidth={2.5}
                dot={{ r: 2.5, fill: HISTORICAL_TREND_COLORS.meanToCost, strokeWidth: 0 }}
                label={({ x, y, value, index }) =>
                  index === latestDataIndex
                    ? <RatioPointLabel x={x} y={y} value={value} fillColor={HISTORICAL_TREND_COLORS.meanLabel} dy={hasP95Data ? 12 : -10} />
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
                name="Typical Return"
                stroke={HISTORICAL_TREND_COLORS.medianToCost}
                strokeWidth={2}
                dot={{ r: 2, fill: HISTORICAL_TREND_COLORS.medianToCost, strokeWidth: 0 }}
                label={({ x, y, value, index }) =>
                  index === latestDataIndex
                    ? <RatioPointLabel x={x} y={y} value={value} fillColor={HISTORICAL_TREND_COLORS.medianLabel} dy={24} />
                    : null
                }
                activeDot={{ r: 3.5, stroke: "var(--surface-page)", strokeWidth: 2 }}
                connectNulls
                isAnimationActive={false}
              />
            ) : null}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
