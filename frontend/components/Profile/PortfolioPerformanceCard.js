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

import {
  PERFORMANCE_TIME_RANGES,
  getPerformanceRangeData,
} from "@/lib/profile/portfolioPerformanceRange";

/** @typedef {import("@/types/portfolioDashboard").PortfolioPerformancePoint} PortfolioPerformancePoint */

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
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{label}</p>
      <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">{currencyFormatter.format(value)}</p>
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

export default function PortfolioPerformanceCard({ performanceData, selectedRange = "7D", onRangeChange }) {
  const perf = getPerformanceRangeData(selectedRange, performanceData);
  const chartData = perf.points.map((point, index) => ({
    ...point,
    isFinalPoint: index === perf.points.length - 1,
  }));

  const deltaClassName = perf.changePercent >= 0 ? "metric-positive" : "metric-negative";

  return (
    <section className="dashboard-panel flex h-full min-h-[31rem] flex-col rounded-2xl border border-[var(--border-subtle)] p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">Portfolio Performance</p>
        </div>
        <div
          className="flex rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-0.5"
          role="group"
          aria-label="Portfolio performance time range"
        >
          {PERFORMANCE_TIME_RANGES.map((range) => (
            <button
              key={range}
              type="button"
              onClick={() => onRangeChange?.(range)}
              aria-pressed={selectedRange === range}
              className={`rounded-md px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                selectedRange === range
                  ? "bg-[var(--brand)] text-white"
                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              {range}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.08em] text-[var(--text-secondary)]">Current Value</p>
          <p className="mt-1 text-[2rem] font-semibold leading-none text-[var(--text-primary)] sm:text-[2.4rem]">
            {currencyFormatter.format(perf.currentValue)}
          </p>
          <p className={`mt-2 text-sm font-semibold ${deltaClassName}`}>{formatPercent(perf.changePercent)}</p>
        </div>
        <div className="max-w-[16rem] text-left sm:text-right">
          <p className="text-[11px] uppercase tracking-[0.08em] text-[var(--text-secondary)]">Signal</p>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">{perf.helper}</p>
        </div>
      </div>

      <div className="mt-5 min-h-[20rem] flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
            <defs>
              <linearGradient id="portfolioAreaGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--brand)" stopOpacity={0.48} />
                <stop offset="45%" stopColor="var(--brand)" stopOpacity={0.16} />
                <stop offset="95%" stopColor="var(--brand)" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="var(--border-subtle)" strokeOpacity={0.35} strokeDasharray="2 6" vertical={false} />
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
              fill="url(#portfolioAreaGradient)"
              dot={<FinalPointDot />}
              activeDot={{ r: 4, stroke: "var(--surface-page)", strokeWidth: 2 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
