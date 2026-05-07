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

const SERIES_STROKE_WIDTH = 2.6;
const SERIES_DOT_RADIUS = 2.3;
const MARKET_LINE_OPACITY = 0.46;
const MARKET_MEDIAN_OPACITY = 0.3;

const DEFAULT_SERIES_VISIBILITY = {
  meanCustom: true,
  medianCustom: true,
  p95Custom: true,
  meanMarket: true,
  medianMarket: false,
  p95Market: true,
};

const LINE_COLORS = {
  meanCustom: "#c8a15a",
  medianCustom: "#b7854a",
  p95Custom: "#e4cf9d",
  meanMarket: "#27978f",
  medianMarket: "#5a81b3",
  p95Market: "#48a9bd",
};

function toNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatRatio(value) {
  const parsed = toNumber(value);
  return parsed === null ? "-" : `${parsed.toFixed(2)}x`;
}

function formatCurrency(value) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return "-";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(parsed);
}

function formatShortDate(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(date);
}

function formatLongDate(value) {
  if (!value) {
    return "-";
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

function getYAxisMax(points) {
  let maxRatio = 1;
  for (const row of points) {
    const values = [
      toNumber(row.mean_to_custom_cost_ratio),
      toNumber(row.median_to_custom_cost_ratio),
      toNumber(row.p95_to_custom_cost_ratio),
      toNumber(row.mean_to_market_cost_ratio),
      toNumber(row.median_to_market_cost_ratio),
      toNumber(row.p95_to_market_cost_ratio),
    ];
    for (const value of values) {
      if (value !== null) {
        maxRatio = Math.max(maxRatio, value);
      }
    }
  }

  const padded = maxRatio * 1.12;
  if (padded <= 1.25) return 1.25;
  if (padded <= 2.0) return 2.0;
  if (padded <= 3.0) return 3.0;
  if (padded <= 4.0) return 4.0;
  if (padded <= 5.0) return 5.0;
  return Math.ceil(padded);
}

function buildTicks(maxValue) {
  const step = maxValue > 2.5 ? 0.5 : 0.25;
  const rounded = Math.ceil(maxValue / step) * step;
  const ticks = [];
  for (let value = 0; value <= rounded + 0.0001; value += step) {
    ticks.push(Number(value.toFixed(2)));
  }
  return ticks;
}

function LegendToggle({ active, onToggle, color, label, strokeWidth = 2 }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={active}
      className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[10px] font-medium transition-colors ${
        active
          ? "border-[var(--border-subtle)]/70 bg-[var(--surface-panel)]/55 text-[var(--text-primary)]"
          : "border-transparent text-[var(--text-secondary)]/40 hover:text-[var(--text-secondary)]"
      }`}
    >
      <span
        className="inline-block w-7 flex-none rounded-full"
        style={{
          backgroundColor: color,
          height: `${Math.max(3.5, strokeWidth)}px`,
          opacity: active ? 0.95 : 0.3,
        }}
      />
      {label}
    </button>
  );
}

function TooltipRow({ label, value, color, muted = false }) {
  return (
    <p className={`flex items-center justify-between gap-6 text-xs ${muted ? "text-[var(--text-secondary)]/85" : "text-[var(--text-secondary)]"}`}>
      <span className="inline-flex items-center gap-2">
        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color, opacity: muted ? 0.7 : 0.95 }} />
        {label}
      </span>
      <span className={`font-semibold ${muted ? "text-[var(--text-secondary)]/90" : "text-[var(--text-primary)]"}`}>{value}</span>
    </p>
  );
}

function TrendTooltip({ active, payload }) {
  if (!active || !payload?.length) {
    return null;
  }
  const row = payload[0]?.payload;
  if (!row) {
    return null;
  }

  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)]/96 px-3.5 py-3 shadow-[0_16px_40px_rgba(0,0,0,0.42)] backdrop-blur-sm">
      <p className="text-sm font-semibold text-[var(--text-primary)]">{formatLongDate(row.snapshot_date)}</p>
      <div className="mt-3 space-y-2.5">
        <div>
          <p className="text-[9px] font-semibold uppercase tracking-[0.07em] text-[var(--text-secondary)]/70">
            Your Price · {formatCurrency(row.custom_pack_cost)}
          </p>
          <div className="mt-1.5 grid gap-1">
            <TooltipRow label="Mean / Cost" value={formatRatio(row.mean_to_custom_cost_ratio)} color={LINE_COLORS.meanCustom} />
            <TooltipRow label="Median / Cost" value={formatRatio(row.median_to_custom_cost_ratio)} color={LINE_COLORS.medianCustom} />
            <TooltipRow label="P95 / Cost" value={formatRatio(row.p95_to_custom_cost_ratio)} color={LINE_COLORS.p95Custom} />
          </div>
        </div>
        <div className="border-t border-[var(--border-subtle)]/40 pt-2.5">
          <p className="text-[9px] font-semibold uppercase tracking-[0.07em] text-[var(--text-secondary)]/70">
            Market · {formatCurrency(row.market_pack_cost)}
          </p>
          <div className="mt-1.5 grid gap-1">
            <TooltipRow label="Mean / Cost" value={formatRatio(row.mean_to_market_cost_ratio)} color={LINE_COLORS.meanMarket} muted />
            <TooltipRow label="Median / Cost" value={formatRatio(row.median_to_market_cost_ratio)} color={LINE_COLORS.medianMarket} muted />
            <TooltipRow label="P95 / Cost" value={formatRatio(row.p95_to_market_cost_ratio)} color={LINE_COLORS.p95Market} muted />
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ToolHistoricalComparisonChart({ historyTrend = [] }) {
  const [seriesVisible, setSeriesVisible] = useState(DEFAULT_SERIES_VISIBILITY);
  const resetSeriesVisibility = () => setSeriesVisible(DEFAULT_SERIES_VISIBILITY);
  const toggleSeries = (key) => setSeriesVisible((prev) => ({ ...prev, [key]: !prev[key] }));
  const allCustomVisible = seriesVisible.meanCustom && seriesVisible.medianCustom && seriesVisible.p95Custom;
  const allMarketVisible = seriesVisible.meanMarket && seriesVisible.medianMarket && seriesVisible.p95Market;
  const toggleCustomGroup = () => {
    const nextVisible = !allCustomVisible;
    setSeriesVisible((prev) => ({
      ...prev,
      meanCustom: nextVisible,
      medianCustom: nextVisible,
      p95Custom: nextVisible,
    }));
  };
  const toggleMarketGroup = () => {
    const nextVisible = !allMarketVisible;
    setSeriesVisible((prev) => ({
      ...prev,
      meanMarket: nextVisible,
      medianMarket: nextVisible,
      p95Market: nextVisible,
    }));
  };

  const chartData = useMemo(
    () =>
      (Array.isArray(historyTrend) ? historyTrend : [])
        .map((row, index) => ({
          id: `${index}:${row?.snapshot_date || "na"}:${row?.calculation_run_id || "na"}`,
          snapshot_date: row?.snapshot_date || null,
          run_created_at: row?.run_created_at || null,
          calculation_run_id: row?.calculation_run_id || null,
          market_pack_cost: toNumber(row?.market_pack_cost),
          custom_pack_cost: toNumber(row?.custom_pack_cost),
          mean_to_custom_cost_ratio: toNumber(row?.mean_to_custom_cost_ratio),
          median_to_custom_cost_ratio: toNumber(row?.median_to_custom_cost_ratio),
          p95_to_custom_cost_ratio: toNumber(row?.p95_to_custom_cost_ratio),
          mean_to_market_cost_ratio: toNumber(row?.mean_to_market_cost_ratio),
          median_to_market_cost_ratio: toNumber(row?.median_to_market_cost_ratio),
          p95_to_market_cost_ratio: toNumber(row?.p95_to_market_cost_ratio),
        }))
        .filter((row) => row.snapshot_date),
    [historyTrend]
  );

  const yMax = useMemo(() => getYAxisMax(chartData), [chartData]);
  const yTicks = useMemo(() => buildTicks(yMax), [yMax]);

  if (chartData.length < 2) {
    return (
      <div className="flex min-h-[20rem] flex-col items-center justify-center rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)]/60 px-6 py-10 text-center">
        <p className="max-w-md text-sm text-[var(--text-secondary)]">
          Historical trend will appear after multiple simulation snapshots.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Historical Pack Value vs Cost</p>
          <p className="mt-1 text-xs text-[var(--text-secondary)]/90">Your price is primary. Market pricing remains as context.</p>
        </div>
        <div className="flex min-w-0 flex-wrap items-start gap-x-4 gap-y-2 text-[11px]">
          <div className="flex flex-col gap-1">
            <button
              type="button"
              onClick={toggleCustomGroup}
              aria-pressed={allCustomVisible}
              className={`inline-flex w-fit items-center rounded px-2 py-1 text-[9px] font-semibold uppercase tracking-[0.06em] transition-colors ${
                allCustomVisible
                  ? "text-[var(--text-secondary)]/80 hover:text-[var(--text-primary)]"
                  : "text-[var(--text-secondary)]/65 hover:text-[var(--text-secondary)]"
              }`}
            >
              Your Price
            </button>
            <div className="flex flex-wrap gap-0.5">
              <LegendToggle active={seriesVisible.meanCustom} onToggle={() => toggleSeries("meanCustom")} color={LINE_COLORS.meanCustom} strokeWidth={SERIES_STROKE_WIDTH} label="Mean" />
              <LegendToggle active={seriesVisible.medianCustom} onToggle={() => toggleSeries("medianCustom")} color={LINE_COLORS.medianCustom} strokeWidth={SERIES_STROKE_WIDTH} label="Median" />
              <LegendToggle active={seriesVisible.p95Custom} onToggle={() => toggleSeries("p95Custom")} color={LINE_COLORS.p95Custom} strokeWidth={SERIES_STROKE_WIDTH} label="P95" />
            </div>
          </div>
          <div className="flex flex-col gap-1">
            <button
              type="button"
              onClick={toggleMarketGroup}
              aria-pressed={allMarketVisible}
              className={`inline-flex w-fit items-center rounded px-2 py-1 text-[9px] font-semibold uppercase tracking-[0.06em] transition-colors ${
                allMarketVisible
                  ? "text-[var(--text-secondary)]/75 hover:text-[var(--text-secondary)]"
                  : "text-[var(--text-secondary)]/45 hover:text-[var(--text-secondary)]/70"
              }`}
            >
              Market
            </button>
            <div className="flex flex-wrap gap-0.5">
              <LegendToggle active={seriesVisible.meanMarket} onToggle={() => toggleSeries("meanMarket")} color={LINE_COLORS.meanMarket} strokeWidth={SERIES_STROKE_WIDTH} label="Mean" />
              <LegendToggle active={seriesVisible.medianMarket} onToggle={() => toggleSeries("medianMarket")} color={LINE_COLORS.medianMarket} strokeWidth={SERIES_STROKE_WIDTH} label="Median" />
              <LegendToggle active={seriesVisible.p95Market} onToggle={() => toggleSeries("p95Market")} color={LINE_COLORS.p95Market} strokeWidth={SERIES_STROKE_WIDTH} label="P95" />
            </div>
          </div>
          <button
            type="button"
            onClick={resetSeriesVisibility}
            className="ml-auto self-end rounded px-2 py-1 text-[9px] font-medium uppercase tracking-[0.04em] text-[var(--text-secondary)]/45 transition-colors hover:text-[var(--text-secondary)]/80"
          >
            Reset
          </button>
        </div>
      </div>

      <div className="mt-4 h-[20rem] w-full sm:h-[23rem]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 10, right: 16, left: 0, bottom: 8 }}>
            <CartesianGrid stroke="var(--border-subtle)" strokeOpacity={0.28} strokeDasharray="2 8" vertical={false} />
            <XAxis
              dataKey="snapshot_date"
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
              tickFormatter={formatShortDate}
              minTickGap={22}
              interval="preserveStartEnd"
            />
            <YAxis
              domain={[0, yMax]}
              ticks={yTicks}
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
              tickFormatter={formatRatio}
              width={52}
            />
            <Tooltip content={<TrendTooltip />} cursor={{ stroke: "rgba(255,255,255,0.16)", strokeWidth: 1 }} />

            <ReferenceLine
              y={1}
              stroke="rgba(148,163,184,0.45)"
              strokeDasharray="6 6"
              strokeWidth={1}
              label={{ value: "Break-even", position: "insideTopRight", fill: "rgba(148,163,184,0.75)", fontSize: 10 }}
            />

            {seriesVisible.meanCustom ? (
              <Line type="monotone" dataKey="mean_to_custom_cost_ratio" name="Mean / Your Price" stroke={LINE_COLORS.meanCustom} strokeWidth={SERIES_STROKE_WIDTH} dot={{ r: SERIES_DOT_RADIUS, fill: LINE_COLORS.meanCustom, strokeWidth: 0 }} connectNulls isAnimationActive={false} />
            ) : null}
            {seriesVisible.medianCustom ? (
              <Line type="monotone" dataKey="median_to_custom_cost_ratio" name="Median / Your Price" stroke={LINE_COLORS.medianCustom} strokeWidth={SERIES_STROKE_WIDTH} dot={{ r: SERIES_DOT_RADIUS, fill: LINE_COLORS.medianCustom, strokeWidth: 0 }} connectNulls isAnimationActive={false} />
            ) : null}
            {seriesVisible.p95Custom ? (
              <Line type="monotone" dataKey="p95_to_custom_cost_ratio" name="P95 / Your Price" stroke={LINE_COLORS.p95Custom} strokeWidth={SERIES_STROKE_WIDTH} dot={{ r: SERIES_DOT_RADIUS, fill: LINE_COLORS.p95Custom, strokeWidth: 0 }} connectNulls isAnimationActive={false} />
            ) : null}

            {seriesVisible.meanMarket ? (
              <Line type="monotone" dataKey="mean_to_market_cost_ratio" name="Mean / Market" stroke={LINE_COLORS.meanMarket} strokeOpacity={MARKET_LINE_OPACITY} strokeWidth={SERIES_STROKE_WIDTH} dot={false} connectNulls isAnimationActive={false} />
            ) : null}
            {seriesVisible.medianMarket ? (
              <Line type="monotone" dataKey="median_to_market_cost_ratio" name="Median / Market" stroke={LINE_COLORS.medianMarket} strokeOpacity={MARKET_MEDIAN_OPACITY} strokeWidth={SERIES_STROKE_WIDTH} dot={false} connectNulls isAnimationActive={false} />
            ) : null}
            {seriesVisible.p95Market ? (
              <Line type="monotone" dataKey="p95_to_market_cost_ratio" name="P95 / Market" stroke={LINE_COLORS.p95Market} strokeOpacity={MARKET_LINE_OPACITY} strokeWidth={SERIES_STROKE_WIDTH} dot={false} connectNulls isAnimationActive={false} />
            ) : null}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
