"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { getCollectionValueData } from "@/lib/profile/collectionValueHistory";

/** Collection value chart data point for chart visualization */

const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload || payload.length === 0) {
    return null;
  }

  const value = payload[0]?.value;
  if (typeof value !== "number") {
    return null;
  }

  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)]/95 px-3 py-2 shadow-[0_16px_40px_rgba(0,0,0,0.35)] backdrop-blur-sm">
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
        {label}
      </p>
      <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
        {currencyFormatter.format(value)}
      </p>
    </div>
  );
}

function formatPercent(percent) {
  const absolute = Math.abs(percent).toFixed(2);
  const sign = percent > 0 ? "+" : percent < 0 ? "-" : "";
  return `${sign}${absolute}%`;
}

function FinalPointDot({ cx, cy, payload }) {
  if (typeof cx !== "number" || typeof cy !== "number") {
    return null;
  }

  if (!payload?.isFinalPoint) {
    return null;
  }

  return (
    <g>
      <circle cx={cx} cy={cy} r={7} fill="var(--brand)" fillOpacity="0.18" />
      <circle cx={cx} cy={cy} r={4} fill="var(--brand)" stroke="var(--surface-panel)" strokeWidth={2} />
    </g>
  );
}

/**
 * Collection Value Chart Component
 * Displays collection value over time with selected range data
 * 
 * @component
 * @param {Object} props
 * @param {string} [props.selectedRange="7D"] - Time range (7D, 30D, 90D, 1Y, All)
 * @param {string} [props.tcg="All"] - TCG filter (All, Pokemon, etc.)
 * @param {Object} [props.valueHistory] - Optional custom value history data
 * @param {number} [props.minHeight] - Minimum chart height in pixels (default: 320)
 */
export default function CollectionValueChart({
  selectedRange = "7D",
  tcg = "All",
  valueHistory = null,
  minHeight = 320,
}) {
  const perf = getCollectionValueData(selectedRange, tcg, valueHistory);
  const chartData = perf.points.map((point, index) => ({
    ...point,
    isFinalPoint: index === perf.points.length - 1,
  }));

  const deltaClassName = perf.changePercent >= 0 ? "metric-positive" : "metric-negative";

  return (
    <div className="flex h-full min-h-[20rem] flex-col rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-4 sm:p-5">
      <div className="min-h-[15rem] flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
            <defs>
              <linearGradient id="collectionAreaGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--brand)" stopOpacity={0.48} />
                <stop offset="45%" stopColor="var(--brand)" stopOpacity={0.16} />
                <stop offset="95%" stopColor="var(--brand)" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid
              stroke="var(--border-subtle)"
              strokeOpacity={0.35}
              strokeDasharray="2 6"
              vertical={false}
            />
            <XAxis
              dataKey="dateLabel"
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
              dy={8}
            />
            <YAxis
              tickFormatter={(value) => `$${Math.round(value / 1000)}k`}
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
              width={48}
              dx={-4}
            />
            <Tooltip content={<CustomTooltip />} />
            <Area
              type="monotone"
              dataKey="totalValue"
              stroke="var(--brand)"
              strokeWidth={3}
              fill="url(#collectionAreaGradient)"
              dot={<FinalPointDot />}
              activeDot={{ r: 4, stroke: "var(--surface-page)", strokeWidth: 2 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Footer Metrics */}
      <div className="mt-6 border-t border-[var(--border-subtle)] pt-4">
        <div className="grid grid-cols-3 gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
              Current Value
            </p>
            <p className="mt-1 text-lg font-bold text-[var(--text-primary)] sm:text-xl">
              {currencyFormatter.format(perf.currentValue)}
            </p>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
              Period Change
            </p>
            <p className="mt-1 text-lg font-bold text-[var(--text-primary)] sm:text-xl">
              {currencyFormatter.format(perf.changeDollar)}
            </p>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
              Percent Change
            </p>
            <p className={`mt-1 text-lg font-bold sm:text-xl ${deltaClassName}`}>
              {formatPercent(perf.changePercent)}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
