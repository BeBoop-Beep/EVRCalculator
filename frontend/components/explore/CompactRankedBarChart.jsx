"use client";

import { useId, useMemo } from "react";

import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import ChartFrame from "@/components/explore/ChartFrame";
import {
  getCompactChartHeight,
  getNiceShareDomainMaximum,
  truncateChartLabel,
} from "./rankedBarChartFormatting.mjs";

// Site-teal single-series bar (Simulation Results chart language): restrained
// teal→cyan gradient matching the existing contribution styling, with a
// slightly brighter hover state. One measure, one hue — identity lives in the
// fixed label column, never in per-category colors.
const DEFAULT_BAR_COLOR = "rgba(20,184,166,0.82)";
const DEFAULT_BAR_GRADIENT_END = "rgba(103,232,249,0.55)";
const HOVER_BAR_COLOR = "rgba(45,212,191,0.95)";

// Fixed three-column layout: [label column] [bar plot] [value column]. Both
// text columns are category axes over the same rows, so every row's name and
// value stay readable regardless of how tiny its bar is.
function CategoryLabelTick({ x, y, payload, rows, labelKey, maxLabelChars }) {
  const row = rows[payload?.index] || null;
  const fullLabel = String(row?.[labelKey] ?? payload?.value ?? "");
  return (
    <text
      x={x}
      y={y}
      dy={4}
      textAnchor="end"
      fill="var(--text-primary)"
      fontSize={12}
      fontWeight={500}
    >
      <title>{fullLabel}</title>
      {truncateChartLabel(fullLabel, maxLabelChars)}
    </text>
  );
}

function RightValueTick({ x, y, payload, rows, rightLabelFormatter }) {
  const row = rows[payload?.index] || null;
  if (!row || typeof rightLabelFormatter !== "function") {
    return null;
  }
  const formatted = rightLabelFormatter(row) || {};
  return (
    <text x={x} y={y} dy={4} textAnchor="start" fontSize={11.5}>
      <tspan fill="var(--text-primary)" fontWeight={600}>
        {formatted.primary ?? ""}
      </tspan>
      <tspan fill="var(--text-secondary)" fontWeight={500}>
        {formatted.secondary ?? ""}
      </tspan>
    </text>
  );
}

/**
 * Compact static ranked horizontal bar chart (Recharts, layout="vertical").
 *
 * `rows` must already be ranked (descending) and complete — this component
 * never sorts, filters, or paginates; every source row renders as exactly one
 * ~23px-pitch row. `valueKey` is a real share-of-total percentage (0-100) and
 * the axis domain is a readable "nice" ceiling above the actual maximum, so
 * bar lengths stay truthful while using the available width.
 *
 * `rightLabelFormatter(row)` returns { primary, secondary } — e.g.
 * { primary: "29.2%", secondary: " · 463,196" } — rendered as the fixed right
 * value column. Full exact values belong in `tooltipContent`.
 */
export default function CompactRankedBarChart({
  rows,
  valueKey = "sharePercent",
  labelKey = "label",
  rightLabelFormatter,
  tooltipContent = null,
  height = null,
  barColor = null,
  labelWidth = 190,
  valueWidth = 118,
  maxLabelChars = 26,
}) {
  const gradientId = useId();
  const chartRows = useMemo(() => (Array.isArray(rows) ? rows : []), [rows]);
  const domainMaximum = useMemo(
    () => getNiceShareDomainMaximum(Math.max(...chartRows.map((row) => Number(row?.[valueKey]) || 0), 0)),
    [chartRows, valueKey]
  );
  const chartHeight = height ?? getCompactChartHeight(chartRows.length);

  if (chartRows.length === 0) {
    return null;
  }

  const fill = barColor || `url(#${gradientId})`;

  return (
    <div className="min-w-0 overflow-visible" style={{ height: chartHeight }}>
      <ChartFrame className="h-full w-full overflow-visible">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={chartRows}
            layout="vertical"
            margin={{ top: 4, right: 6, bottom: 4, left: 0 }}
            barCategoryGap={4}
          >
            {barColor ? null : (
              <defs>
                <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor={DEFAULT_BAR_COLOR} />
                  <stop offset="100%" stopColor={DEFAULT_BAR_GRADIENT_END} />
                </linearGradient>
              </defs>
            )}

            <XAxis type="number" domain={[0, domainMaximum]} hide />

            {/* Left fixed label column: category names only, one line, ellipsis. */}
            <YAxis
              yAxisId="labels"
              type="category"
              dataKey={labelKey}
              width={labelWidth}
              axisLine={false}
              tickLine={false}
              interval={0}
              tick={<CategoryLabelTick rows={chartRows} labelKey={labelKey} maxLabelChars={maxLabelChars} />}
            />

            {/* Right fixed value column: share first, quieter secondary value. */}
            <YAxis
              yAxisId="values"
              orientation="right"
              type="category"
              dataKey={labelKey}
              width={valueWidth}
              axisLine={false}
              tickLine={false}
              interval={0}
              tick={<RightValueTick rows={chartRows} rightLabelFormatter={rightLabelFormatter} />}
            />

            {tooltipContent ? (
              <Tooltip
                content={tooltipContent}
                cursor={{ fill: "rgba(255,255,255,0.05)" }}
                allowEscapeViewBox={{ x: true, y: true }}
                wrapperStyle={{ zIndex: 9999, pointerEvents: "none" }}
              />
            ) : null}

            <Bar
              yAxisId="labels"
              dataKey={valueKey}
              barSize={14}
              radius={[0, 4, 4, 0]}
              fill={fill}
              activeBar={{ fill: HOVER_BAR_COLOR }}
              isAnimationActive={false}
            />
          </BarChart>
        </ResponsiveContainer>
      </ChartFrame>
    </div>
  );
}
