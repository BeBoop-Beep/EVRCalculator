"use client";

import { useId, useMemo } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

/**
 * PremiumTimeSeriesChart
 * 
 * A reusable, premium-styled time series chart component for displaying market data,
 * performance trends, and other time-series visualizations.
 * 
 * Can be used on:
 * - Card detail pages
 * - Product/sealed pages
 * - Portfolio pages
 * - Public profile pages
 * - Any future market/performance chart
 */
export default function PremiumTimeSeriesChart({
  // Data configuration
  data = [],
  title,
  subtitle,
  emptyMessage = "No data available",

  // Header controls
  periods = [],
  selectedPeriod = null,
  onPeriodChange,
  selectedMode = "price",
  onModeChange,
  modeOptions = [
    { value: "price", label: "Price" },
    { value: "delta", label: "Delta" },
  ],
  
  // Formatting
  formatValue = (value) => value,
  formatXAxisLabel = (value) => value,
  tooltipContent = null,
  
  // Visual mode and trend
  mode = "price", // "price" or "delta"
  trend = "neutral", // "positive", "negative", or "neutral"
  
  // Height/sizing
  height = "20rem",
  heightSm = "23rem",
  
  // CSS
  className = "",
}) {
  const instanceId = useId().replace(/:/g, "-");

  // Determine trend colors based on trend prop
  const trendColors = useMemo(() => {
    if (trend === "positive") {
      return {
        stroke: "rgba(20,184,166,0.95)", // teal
        fillStart: "rgba(20,184,166,0.26)",
        fillEnd: "rgba(20,184,166,0.01)",
        fillMid: "rgba(20,184,166,0.08)",
        dotPattern: "rgba(20,184,166,0.2)",
      };
    }
    if (trend === "negative") {
      return {
        stroke: "rgba(239,68,68,0.88)", // red/coral
        fillStart: "rgba(239,68,68,0.26)",
        fillEnd: "rgba(239,68,68,0.01)",
        fillMid: "rgba(239,68,68,0.08)",
        dotPattern: "rgba(239,68,68,0.2)",
      };
    }
    // neutral
    return {
      stroke: "rgba(148,163,184,0.82)", // slate/gray
      fillStart: "rgba(148,163,184,0.26)",
      fillEnd: "rgba(148,163,184,0.01)",
      fillMid: "rgba(148,163,184,0.08)",
      dotPattern: "rgba(148,163,184,0.2)",
    };
  }, [trend]);

  const gradientId = `premium-chart-gradient-${instanceId}`;
  const dotsPatternId = `premium-chart-dots-${instanceId}`;

  // Compute Y-axis domain based on data
  const yDomain = useMemo(() => {
    if (!data || !data.length) return [0, 1];
    
    const values = data
      .map((row) => {
        const val = row.value !== undefined ? row.value : null;
        const num = Number(val);
        return Number.isFinite(num) ? num : null;
      })
      .filter((v) => v !== null);
    
    if (!values.length) return [0, 1];
    
    const minVal = Math.min(...values);
    const maxVal = Math.max(...values);
    const range = maxVal - minVal;
    
    if (mode === "price") {
      const padding = range > 0 ? range * 0.28 : Math.max(maxVal * 0.06, 1);
      return [Math.max(0, minVal - padding), maxVal + padding];
    }
    
    // delta mode
    const spread = Math.max(Math.abs(minVal), Math.abs(maxVal));
    return spread > 0 ? [-(spread * 1.22), spread * 1.22] : [-1, 1];
  }, [data, mode]);

  const areaBaseValue = Array.isArray(yDomain) ? yDomain[0] : "dataMin";

  const dataLength = data?.length || 0;

  if (!data || !data.length) {
    return (
      <div className={`relative flex min-h-[20rem] flex-col items-center justify-center overflow-hidden rounded-xl border border-dashed border-[var(--border-subtle)] bg-[linear-gradient(160deg,rgba(14,20,34,0.82),rgba(8,12,22,0.94))] px-6 py-10 text-center ${className}`}>
        <div className="pointer-events-none absolute -top-16 right-[-4rem] h-36 w-36 rounded-full bg-[rgba(20,184,166,0.12)] blur-3xl" />
        <div className="pointer-events-none absolute -bottom-16 left-[-4rem] h-36 w-36 rounded-full bg-[rgba(126,95,255,0.1)] blur-3xl" />
        <p className="max-w-md text-sm text-[var(--text-secondary)]">{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div className={`relative overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[linear-gradient(160deg,rgba(11,16,28,0.97),rgba(6,9,18,0.99))] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.045),inset_0_-1px_0_rgba(0,0,0,0.35)] sm:p-5 ${className}`}>
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_50%_-10%,rgba(20,184,166,0.07)_0%,transparent_65%)]" />
      {(title || subtitle || periods.length || modeOptions.length) ? (
        <div className="relative mb-3 flex flex-wrap items-start justify-between gap-3">
          <div>
            {title ? <h2 className="text-base font-semibold text-[var(--text-primary)]">{title}</h2> : null}
            {subtitle ? <p className="mt-1 text-xs text-[var(--text-secondary)]">{subtitle}</p> : null}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {periods.length ? (
              <div className="inline-flex rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-1">
                {periods.map((period) => {
                  const value = period?.value ?? period?.key;
                  const label = period?.label ?? String(value || "");
                  const isActive = value === selectedPeriod;
                  return (
                    <button
                      key={String(value)}
                      type="button"
                      onClick={() => onPeriodChange?.(value)}
                      className={`rounded-md px-2.5 py-1 text-[11px] font-semibold tracking-[0.04em] transition ${
                        isActive
                          ? "bg-brand text-white shadow-[0_0_0_1px_rgba(20,184,166,0.35)]"
                          : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                      }`}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
            ) : null}

            {modeOptions.length ? (
              <div className="inline-flex rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-1">
                {modeOptions.map((modeOption) => {
                  const value = modeOption?.value;
                  const label = modeOption?.label ?? String(value || "");
                  const isActive = value === selectedMode;
                  return (
                    <button
                      key={String(value)}
                      type="button"
                      onClick={() => onModeChange?.(value)}
                      className={`rounded-md px-2.5 py-1 text-[11px] font-semibold tracking-[0.04em] transition ${
                        isActive
                          ? "bg-brand text-white shadow-[0_0_0_1px_rgba(20,184,166,0.35)]"
                          : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                      }`}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
      <div className={`relative w-full`} style={{ height, [`--sm-height`]: heightSm }}>
        <style>{`
          @media (min-width: 640px) {
            .chart-container { height: ${heightSm} }
          }
        `}</style>
        <div className="chart-container" style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data} margin={{ top: 10, right: 16, left: 8, bottom: 8 }}>
              <defs>
                {/* Fill is anchored to chart bottom and rises to the line. */}
                <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={trendColors.fillStart} stopOpacity={0.26} />
                  <stop offset="55%" stopColor={trendColors.fillMid} stopOpacity={0.08} />
                  <stop offset="100%" stopColor={trendColors.fillEnd} stopOpacity={0.01} />
                </linearGradient>
                
                {/* Premium dot texture pattern */}
                <pattern id={dotsPatternId} x="0" y="0" width="8" height="8" patternUnits="userSpaceOnUse">
                  <circle cx="4" cy="4" r="0.85" fill={trendColors.stroke} opacity={0.2} />
                </pattern>
              </defs>

              <CartesianGrid
                stroke="rgba(255,255,255,0.05)"
                strokeDasharray="2 9"
                vertical={false}
              />
              
              <XAxis
                dataKey="date"
                tickLine={false}
                axisLine={false}
                tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
                tickFormatter={formatXAxisLabel}
                minTickGap={24}
                interval="preserveStartEnd"
              />
              
              <YAxis
                domain={yDomain}
                tickLine={false}
                axisLine={false}
                tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
                tickFormatter={formatValue}
                width={72}
              />
              
              <Tooltip
                content={tooltipContent || null}
                cursor={{ stroke: "rgba(255,255,255,0.11)", strokeWidth: 1, strokeDasharray: "3 5" }}
              />

              {/* Gradient base area fill from bottom to line */}
              <Area
                type="monotone"
                dataKey="value"
                baseValue={areaBaseValue}
                stroke="none"
                fill={`url(#${gradientId})`}
                fillOpacity={1}
                isAnimationActive
                animationDuration={420}
                animationEasing="ease-out"
                connectNulls
              />
              
              {/* Dot texture overlay on the fill */}
              <Area
                type="monotone"
                dataKey="value"
                baseValue={areaBaseValue}
                stroke="none"
                fill={`url(#${dotsPatternId})`}
                fillOpacity={0.45}
                isAnimationActive
                animationDuration={420}
                animationEasing="ease-out"
                connectNulls
              />

              {/* Main crisp line on top */}
              <Line
                type="monotone"
                dataKey="value"
                stroke={trendColors.stroke}
                strokeWidth={2.6}
                dot={(props) => {
                  if (!props || props.index !== dataLength - 1) return null;
                  return (
                    <g key={`end-dot-${props.index}`}>
                      <circle cx={props.cx} cy={props.cy} r={11} fill={trendColors.stroke} opacity={0.11} />
                      <circle cx={props.cx} cy={props.cy} r={4.5} fill={trendColors.stroke} opacity={0.95} />
                      <circle cx={props.cx} cy={props.cy} r={1.8} fill="rgba(6,9,18,1)" opacity={0.9} />
                    </g>
                  );
                }}
                activeDot={{ r: 4, stroke: "rgba(6,9,18,1)", strokeWidth: 2, fill: trendColors.stroke }}
                connectNulls
                isAnimationActive
                animationDuration={420}
                animationEasing="ease-out"
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
