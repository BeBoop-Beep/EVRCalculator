"use client";

import React, { useId, useMemo } from "react";
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import ChartEdgeDateTick from "@/components/explore/ChartEdgeDateTick";
import ChartFrame from "@/components/explore/ChartFrame";
import MarketTrendTooltipCard from "@/components/explore/MarketTrendTooltipCard";
import { MINIMAL_Y_AXIS_PROPS, buildEdgeDateTicks, getMinimalPlotMargin } from "@/components/explore/minimalChartAxis.mjs";
import usePointerMode, { POINTER_MODE_COARSE } from "@/hooks/usePointerMode";
import { NEGATIVE_VALUE_COLOR, POSITIVE_VALUE_COLOR } from "@/lib/explore/interpretationTone";
import { formatHistoryDate, getHistoryDateKey } from "@/components/explore/historyDateFormatting.mjs";
import { toFiniteNumber } from "./setMarketMobileModel.mjs";

// ---------------------------------------------------------------------------
// ONE chart for the mobile Market tab.
//
// Set Value and Sealed Market both draw a dated price series, and on a phone
// two different chart treatments a screen apart read as two different products.
// This is the desktop Set Value chart's exact visual language — glow stroke over
// a fading area, dotted horizontal grid, and the two edge dates as the only
// axis labels — re-proportioned for a phone and shared by both sections.
//
// The axis is deliberately sparse. A phone-width plot cannot print six dated
// ticks and a currency gutter without turning the series into a thin line in
// the middle of a box, so exact readings come from tap-scrub instead: coarse
// pointers bind `click`, which persists after the finger lifts and never fires
// while the page is being scrolled past the chart.
// ---------------------------------------------------------------------------

const NEUTRAL_MARKET_COLOR = "rgba(148,163,184,0.9)";

function formatAxisCurrency(value) {
  const parsed = toFiniteNumber(value);
  if (parsed === null) return "";
  const abs = Math.abs(parsed);
  if (abs >= 1000000) return `$${(parsed / 1000000).toFixed(1)}M`;
  if (abs >= 1000) return `$${(parsed / 1000).toFixed(abs >= 10000 ? 0 : 1)}K`;
  return `$${parsed.toFixed(abs >= 100 ? 0 : 2)}`;
}

function formatEdgeDate(value) {
  return formatHistoryDate(value, { month: "short", day: "numeric" }) || String(value || "").slice(5);
}

function MobileChartTooltip({ active, payload }) {
  const row = active && payload?.[0]?.payload;
  if (!row) return null;
  return (
    <MarketTrendTooltipCard
      date={row.date}
      value={row.value}
      deltaAmount={row.deltaFromWindowStart}
      deltaPercent={row.deltaPercentFromWindowStart}
      accessibleLabel="Market value at selected date"
    />
  );
}

export default function MarketMobileChart({
  points,
  valueKey = "value",
  trendDirection = "neutral",
  seriesLabel = "Market value",
  heightClassName = "h-[clamp(196px,27dvh,248px)]",
  emptyMessage = "Not enough history yet. The chart appears after a few days of market observations.",
}) {
  const isCoarsePointer = usePointerMode() === POINTER_MODE_COARSE;
  const chartId = useId().replace(/:/g, "");
  const fillId = `market-mobile-fill-${chartId}`;
  const glowId = `market-mobile-glow-${chartId}`;

  const series = useMemo(() => {
    const normalized = (Array.isArray(points) ? points : [])
      .map((point) => ({
        date: getHistoryDateKey(point?.date),
        value: toFiniteNumber(point?.[valueKey] ?? point?.value),
      }))
      .filter((point) => point.date);
    // Deltas are measured from the first VALUED point of the visible window, so
    // the tooltip answers "how far has this moved inside the window I picked?"
    // rather than "how far from yesterday?".
    const baseline = normalized.find((point) => point.value !== null)?.value ?? null;
    return normalized.map((point) => {
      const amount = point.value !== null && baseline !== null ? point.value - baseline : null;
      return {
        ...point,
        deltaFromWindowStart: amount,
        deltaPercentFromWindowStart: amount !== null && baseline ? (amount / baseline) * 100 : null,
      };
    });
  }, [points, valueKey]);

  const valued = series.filter((point) => point.value !== null);

  if (valued.length < 2) {
    return (
      <div
        data-market-mobile-chart="empty"
        className={`flex ${heightClassName} min-w-0 items-center justify-center rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)]/40 px-5 text-center`}
      >
        <p className="text-[12px] leading-relaxed text-[var(--text-secondary)]">{emptyMessage}</p>
      </div>
    );
  }

  const values = valued.map((point) => point.value);
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const range = maxValue - minValue || Math.max(maxValue, 1) * 0.08 || 1;
  const yMin = Math.max(0, minValue - range * 0.16);
  const yMax = maxValue + range * 0.16;
  const ticks = buildEdgeDateTicks(series, "date");
  const trendColor =
    trendDirection === "negative"
      ? NEGATIVE_VALUE_COLOR
      : trendDirection === "positive"
      ? POSITIVE_VALUE_COLOR
      : NEUTRAL_MARKET_COLOR;

  return (
    <div data-market-mobile-chart="series" className="min-w-0">
      <ChartFrame className={`${heightClassName} w-full overflow-hidden rounded-xl`}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={series} margin={getMinimalPlotMargin({ top: 8, bottom: 2 })}>
          <defs>
            <linearGradient id={fillId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={trendColor} stopOpacity="0.16" />
              <stop offset="68%" stopColor={trendColor} stopOpacity="0.04" />
              <stop offset="100%" stopColor={trendColor} stopOpacity="0" />
            </linearGradient>
            <filter id={glowId} x="-12%" y="-18%" width="124%" height="136%">
              <feGaussianBlur stdDeviation="1.8" />
            </filter>
          </defs>
          <Area
            type="linear"
            dataKey="value"
            baseValue={yMin}
            fill={`url(#${fillId})`}
            stroke="none"
            dot={false}
            activeDot={false}
            legendType="none"
            tooltipType="none"
            isAnimationActive={false}
          />
          <CartesianGrid stroke="var(--border-subtle)" strokeOpacity={0.3} strokeDasharray="2 8" vertical={false} />
          <XAxis
            dataKey="date"
            ticks={ticks}
            tickLine={false}
            axisLine={false}
            interval={0}
            minTickGap={0}
            tick={<ChartEdgeDateTick ticks={ticks} formatter={formatEdgeDate} />}
            tickFormatter={formatEdgeDate}
          />
          <YAxis {...MINIMAL_Y_AXIS_PROPS} domain={[yMin, yMax]} tickCount={3} tickFormatter={formatAxisCurrency} />
          <Tooltip
            trigger={isCoarsePointer ? "click" : "hover"}
            content={<MobileChartTooltip />}
            cursor={{ stroke: "rgba(255,255,255,0.16)", strokeWidth: 1 }}
          />
          <Line
            type="linear"
            dataKey="value"
            stroke={trendColor}
            strokeWidth={7}
            strokeOpacity={0.16}
            filter={`url(#${glowId})`}
            dot={false}
            activeDot={false}
            legendType="none"
            tooltipType="none"
            isAnimationActive={false}
          />
          <Line
            type="linear"
            dataKey="value"
            name={seriesLabel}
            stroke={trendColor}
            strokeWidth={2.4}
            dot={false}
            activeDot={{ r: 4.5, fill: trendColor, stroke: "var(--surface-page)", strokeWidth: 2 }}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
      </ChartFrame>
    </div>
  );
}
