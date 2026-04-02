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
  getPerformanceRangeData,
} from "@/lib/profile/portfolioPerformanceRange";
import OverviewRangeToggle from "@/components/Profile/OverviewRangeToggle";

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

/**
 * Unified Portfolio Performance Canvas
 * 
 * Premium Recharts AreaChart component for displaying portfolio performance over time.
 * Shared between owner and public portfolio views.
 * 
 * @component
 * @param {Object} props
 * @param {Object} props.performanceData - Performance data with points array and metadata
 * @param {string} [props.selectedRange="7D"] - Currently selected time range (7D, 1M, 6M, 1Y)
 * @param {Function} props.onRangeChange - Callback when time range is changed
 * @param {"owner" | "public"} [props.mode="owner"] - Rendering mode (not visually different, but available for future mode-specific logic)
 */
export default function PortfolioPerformanceCanvas({ 
  performanceData, 
  selectedRange = "7D", 
  onRangeChange,
  investedValue = null,
  performanceHighlights = null,
  mode = "owner",
}) {
  const isOwnerMode = mode === "owner";
  const perf = getPerformanceRangeData(selectedRange, performanceData);
  const chartData = perf.points.map((point, index) => ({
    ...point,
    isFinalPoint: index === perf.points.length - 1,
  }));

  const deltaClassName = perf.changePercent >= 0 ? "metric-positive" : "metric-negative";
  const parsedInvestedValue = Number(investedValue);
  const resolvedInvestedValue = Number.isFinite(parsedInvestedValue) && parsedInvestedValue > 0
    ? parsedInvestedValue
    : Math.max(0, perf.currentValue - perf.changeDollar);
  const profitLossValue = perf.currentValue - resolvedInvestedValue;
  const roiPercent = resolvedInvestedValue > 0
    ? ((perf.currentValue - resolvedInvestedValue) / resolvedInvestedValue) * 100
    : 0;
  const profitLossClass = profitLossValue >= 0 ? "metric-positive" : "metric-negative";
  const roiClass = roiPercent >= 0 ? "metric-positive" : "metric-negative";

  const formatSignedCurrency = (value) => {
    const sign = value > 0 ? "+" : value < 0 ? "-" : "";
    return `${sign}${currencyFormatter.format(Math.abs(value))}`;
  };
  const bestPerformer = performanceHighlights?.bestPerformer || null;
  const worstPerformer = performanceHighlights?.worstPerformer || null;

  return (
    <section className="dashboard-panel flex h-full min-h-[31rem] flex-col rounded-2xl border border-[var(--border-subtle)] p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">Portfolio Performance</p>
        </div>
        <OverviewRangeToggle
          selectedRange={selectedRange}
          onRangeChange={onRangeChange}
          ariaLabel="Portfolio performance time range"
        />
      </div>

      <div className="mt-4 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.08em] text-[var(--text-secondary)]">Current Value</p>
          <p className="mt-1 text-[2rem] font-bold leading-none text-[var(--text-primary)] sm:text-[2.35rem]">
            {currencyFormatter.format(perf.currentValue)}
          </p>
          <p className={`mt-1.5 text-sm font-semibold ${deltaClassName}`}>{formatPercent(perf.changePercent)}</p>
        </div>
        <div className="max-w-[16rem] text-left sm:text-right">
          <p className="text-[11px] uppercase tracking-[0.08em] text-[var(--text-secondary)]">
            {isOwnerMode ? "Signal" : "Public Signal"}
          </p>
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

      <div className="mt-5 border-t border-[var(--border-subtle)] pt-4">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Portfolio Value</p>
            <p className="mt-1.5 text-lg font-semibold text-[var(--text-primary)]">{currencyFormatter.format(perf.currentValue)}</p>
          </div>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Invested Value</p>
            <p className="mt-1.5 text-lg font-semibold text-[var(--text-primary)]">{currencyFormatter.format(resolvedInvestedValue)}</p>
          </div>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Profit/Loss</p>
            <p className={`mt-1.5 text-lg font-semibold ${profitLossClass}`}>{formatSignedCurrency(profitLossValue)}</p>
          </div>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">ROI %</p>
            <p className={`mt-1.5 text-lg font-semibold ${roiClass}`}>{formatPercent(roiPercent)}</p>
          </div>
        </div>
      </div>

      <div className="mt-4 border-t border-[var(--border-subtle)] pt-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="rounded-xl bg-[var(--surface-page)] p-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Best Performer</p>
            <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
              {bestPerformer?.name || "No qualifying items"}
            </p>
            <p className="mt-1 text-lg font-semibold metric-positive">
              {bestPerformer ? formatPercent(bestPerformer.changePercent) : "-"}
            </p>
          </div>

          <div className="rounded-xl bg-[var(--surface-page)] p-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Worst Performer</p>
            <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
              {worstPerformer?.name || "No qualifying items"}
            </p>
            <p className="mt-1 text-lg font-semibold metric-negative">
              {worstPerformer ? formatPercent(worstPerformer.changePercent) : "-"}
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
