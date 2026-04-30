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

function toNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
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

function buildRatioTicks(upperBound) {
  const safeUpper = Number.isFinite(upperBound) ? upperBound : 1.25;
  const roundedUpper = Math.ceil(safeUpper / 0.25) * 0.25;
  const ticks = [];
  for (let value = 0; value <= roundedUpper + 0.0001; value += 0.25) {
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

function TrendTooltip({ active, payload, packCost }) {
  if (!active || !payload?.length) {
    return null;
  }

  const row = payload[0]?.payload;
  if (!row) {
    return null;
  }

  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)]/95 px-3 py-2 shadow-[0_16px_40px_rgba(0,0,0,0.35)] backdrop-blur-sm">
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Date</p>
      <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">{formatLongDate(row.snapshot_date)}</p>
      <p className="mt-2 text-xs text-[var(--text-secondary)]">
        Mean / Cost <span className="font-semibold text-[var(--text-primary)]">{formatRatio(row.simulated_mean_pack_value_vs_pack_cost)}</span>
      </p>
      <p className="text-xs text-[var(--text-secondary)]">
        Median / Cost <span className="font-semibold text-[var(--text-primary)]">{formatRatio(row.simulated_median_pack_value_vs_pack_cost)}</span>
      </p>
      <p className="text-xs text-[var(--text-secondary)]">
        Break-even <span className="font-semibold text-[var(--text-primary)]">1.00x</span>
      </p>
      <p className="text-xs text-[var(--text-secondary)]">
        Pack Cost <span className="font-semibold text-[var(--text-primary)]">{formatCurrency(packCost)}</span>
      </p>
    </div>
  );
}

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

function EmptyTrendState() {
  return (
    <div className="flex min-h-[24rem] flex-col items-center justify-center rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)]/60 px-6 py-10 text-center">
      <p className="max-w-md text-sm text-[var(--text-secondary)]">
        Historical trend will appear after multiple daily simulation snapshots.
      </p>
    </div>
  );
}

export default function PackValueHistoryChart({ historyTrend = [], packCost = null }) {
  const [showMeanLine, setShowMeanLine] = useState(true);
  const [showMedianLine, setShowMedianLine] = useState(true);

  const historicalTrendInfo = (
    <div className="space-y-1.5 text-left">
      <p className="font-semibold text-[var(--text-primary)]">Historical Pack Value vs Cost</p>
      <ul className="space-y-1 pl-3 text-[var(--text-secondary)]">
        <li className="flex gap-2"><span className="flex-none">•</span><span>Mean / Cost compares average simulated pack value to pack cost over time.</span></li>
        <li className="flex gap-2"><span className="flex-none">•</span><span>Median / Cost compares typical simulated pack value to pack cost over time.</span></li>
        <li className="flex gap-2"><span className="flex-none">•</span><span>1.0x is break-even.</span></li>
        <li className="flex gap-2"><span className="flex-none">•</span><span>Above 1.0x means simulated value exceeded pack cost.</span></li>
        <li className="flex gap-2"><span className="flex-none">•</span><span>The break-even label includes the current pack cost when available.</span></li>
      </ul>
    </div>
  );

  const chartData = useMemo(
    () =>
      (Array.isArray(historyTrend) ? historyTrend : [])
        .map((row, index) => ({
          id: `${index}:${row?.snapshot_date || "na"}:${row?.calculation_run_id || "na"}`,
          snapshot_date: row?.snapshot_date || null,
          run_created_at: row?.run_created_at || null,
          calculation_run_id: row?.calculation_run_id || null,
          simulated_mean_pack_value_vs_pack_cost: toNumber(
            row?.simulated_mean_pack_value_vs_pack_cost
          ),
          simulated_median_pack_value_vs_pack_cost: toNumber(
            row?.simulated_median_pack_value_vs_pack_cost
          ),
        }))
        .filter(
          (row) =>
            row.snapshot_date &&
            (row.simulated_mean_pack_value_vs_pack_cost !== null ||
              row.simulated_median_pack_value_vs_pack_cost !== null)
        ),
    [historyTrend]
  );

  const yAxisUpperBound = useMemo(() => {
    const observedMax = chartData.reduce((maxValue, row) => {
      const meanValue = toNumber(row.simulated_mean_pack_value_vs_pack_cost);
      const medianValue = toNumber(row.simulated_median_pack_value_vs_pack_cost);
      return Math.max(maxValue, meanValue ?? 0, medianValue ?? 0);
    }, 1);
    return Math.max(1.25, observedMax * 1.15);
  }, [chartData]);

  const yAxisTicks = useMemo(() => buildRatioTicks(yAxisUpperBound), [yAxisUpperBound]);

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

        <div className="flex items-center gap-3 text-[11px]">
          <button
            type="button"
            onClick={() => setShowMeanLine((current) => !current)}
            aria-pressed={showMeanLine}
            className={`inline-flex items-center gap-1.5 rounded px-2 py-1 transition-colors ${
              showMeanLine
                ? "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                : "text-[var(--text-secondary)]/50 hover:text-[var(--text-secondary)]"
            }`}
          >
            <span
              className={`inline-block h-0.5 w-5 rounded ${
                showMeanLine ? "bg-[rgba(20,184,166,0.98)]" : "bg-[rgba(20,184,166,0.3)]"
              }`}
            />
            Mean / Cost
          </button>

          <button
            type="button"
            onClick={() => setShowMedianLine((current) => !current)}
            aria-pressed={showMedianLine}
            className={`inline-flex items-center gap-1.5 rounded px-2 py-1 transition-colors ${
              showMedianLine
                ? "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                : "text-[var(--text-secondary)]/50 hover:text-[var(--text-secondary)]"
            }`}
          >
            <span
              className={`inline-block h-0.5 w-5 rounded ${
                showMedianLine ? "bg-[rgba(148,163,184,0.9)]" : "bg-[rgba(148,163,184,0.3)]"
              }`}
            />
            Median / Cost
          </button>
        </div>
      </div>

      <div className="mt-4 h-[20rem] w-full sm:h-[23rem]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 10, right: 52, left: 0, bottom: 8 }}>
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
              stroke="rgba(255,255,255,0.52)"
              strokeDasharray="6 6"
              strokeWidth={1}
              label={{
                value: breakEvenLabel,
                position: "insideTopRight",
                fill: "var(--text-secondary)",
                fontSize: 11,
              }}
            />

            {showMeanLine ? (
              <Line
                type="monotone"
                dataKey="simulated_mean_pack_value_vs_pack_cost"
                name="Mean / Cost"
                stroke="rgba(20,184,166,0.98)"
                strokeWidth={2.5}
                dot={{ r: 2.5, fill: "rgba(20,184,166,0.98)", strokeWidth: 0 }}
                label={({ x, y, value, index }) =>
                  index === latestDataIndex
                    ? <RatioPointLabel x={x} y={y} value={value} fillColor="rgba(183,245,231,0.86)" dy={-10} />
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
                dataKey="simulated_median_pack_value_vs_pack_cost"
                name="Median / Cost"
                stroke="rgba(148,163,184,0.9)"
                strokeWidth={2}
                dot={{ r: 2, fill: "rgba(148,163,184,0.9)", strokeWidth: 0 }}
                label={({ x, y, value, index }) =>
                  index === latestDataIndex
                    ? <RatioPointLabel x={x} y={y} value={value} fillColor="rgba(203,213,225,0.82)" dy={12} />
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
