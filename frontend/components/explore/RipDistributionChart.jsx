"use client";

import { useEffect, useMemo, useState } from "react";

import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const IS_DEV = process.env.NODE_ENV !== "production";

const compactCurrencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  notation: "compact",
  maximumFractionDigits: 1,
});

function toNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatCompactCurrency(value) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return "—";
  }
  return compactCurrencyFormatter.format(parsed);
}

function formatProbabilityPercent(value) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return "—";
  }
  const normalized = parsed <= 1 ? parsed * 100 : parsed;
  return `${normalized.toFixed(1)}%`;
}

function formatCount(value) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return "—";
  }
  return parsed.toLocaleString("en-US");
}

function HistogramTooltip({ active, payload }) {
  if (!active || !payload?.length) {
    return null;
  }

  const row = payload[0]?.payload;
  if (!row) {
    return null;
  }

  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)]/95 px-3 py-2 shadow-[0_16px_40px_rgba(0,0,0,0.35)] backdrop-blur-sm">
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Outcome Range</p>
      <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
        {formatCompactCurrency(row.bin_floor)} to {formatCompactCurrency(row.bin_ceiling)}
      </p>
      <p className="mt-1 text-xs text-[var(--text-secondary)]">Count {formatCount(row.occurrence_count)}</p>
      <p className="text-xs text-[var(--text-secondary)]">Probability {formatProbabilityPercent(row.probabilityPercent)}</p>
      <p className="text-xs text-[var(--text-secondary)]">Cumulative {formatProbabilityPercent(row.cumulativePercent)}</p>
    </div>
  );
}

function ViewModeToggle({ viewMode, onChange, isCurveAvailable }) {
  return (
    <div className="inline-flex items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-0.5">
      <button
        type="button"
        onClick={() => onChange("histogram")}
        aria-pressed={viewMode === "histogram"}
        className={`min-w-[5.6rem] rounded-md px-3 py-1 text-[11px] font-semibold leading-none transition-colors ${
          viewMode === "histogram"
            ? "bg-[var(--brand)] text-white"
            : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        }`}
      >
        Histogram
      </button>
      <button
        type="button"
        onClick={() => {
          if (isCurveAvailable) {
            onChange("curve");
          }
        }}
        disabled={!isCurveAvailable}
        aria-pressed={viewMode === "curve"}
        className={`min-w-[5.6rem] rounded-md px-3 py-1 text-[11px] font-semibold leading-none transition-colors ${
          viewMode === "curve"
            ? "bg-[var(--brand)] text-white"
            : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        } ${!isCurveAvailable ? "cursor-not-allowed opacity-45" : ""}`}
      >
        Curve
      </button>
    </div>
  );
}

function MarkerChips({ markers }) {
  const markerRows = useMemo(
    () =>
      (Array.isArray(markers) ? markers : [])
        .map((marker) => ({
          label: String(marker?.label || "").trim(),
          value: toNumber(marker?.value),
        }))
        .filter((marker) => marker.label),
    [markers]
  );

  if (markerRows.length === 0) {
    return null;
  }

  return (
    <div className="mt-4 flex flex-wrap gap-2">
      {markerRows.map((marker) => (
        <span
          key={`${marker.label}:${marker.value ?? "na"}`}
          className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-1 text-xs text-[var(--text-secondary)]"
        >
          {marker.label}: <span className="ml-1 font-semibold text-[var(--text-primary)]">{formatCompactCurrency(marker.value)}</span>
        </span>
      ))}
    </div>
  );
}

export default function RipDistributionChart({ bins = [], markers = [] }) {
  const [viewMode, setViewMode] = useState("histogram");

  const chartData = useMemo(
    () =>
      Array.isArray(bins)
        ? bins
            .map((bin, index) => {
              const floor = toNumber(bin?.bin_floor);
              const ceiling = toNumber(bin?.bin_ceiling);
              const probability = toNumber(bin?.probability);
              const cumulativeProbability = toNumber(bin?.cumulative_probability);
              const survivalProbability = toNumber(bin?.survival_probability);
              const midpoint =
                floor !== null && ceiling !== null
                  ? (floor + ceiling) / 2
                  : floor ?? ceiling;

              return {
                id: `${index}:${bin?.bin_floor ?? "na"}`,
                bin_floor: floor,
                bin_ceiling: ceiling,
                midpoint,
                rangeLabel:
                  midpoint === null
                    ? `Bin ${index + 1}`
                    : formatCompactCurrency(midpoint),
                probabilityPercent:
                  probability === null ? null : probability <= 1 ? probability * 100 : probability,
                cumulativePercent:
                  cumulativeProbability === null
                    ? null
                    : cumulativeProbability <= 1
                      ? cumulativeProbability * 100
                      : cumulativeProbability,
                survivalPercent:
                  survivalProbability === null
                    ? null
                    : survivalProbability <= 1
                      ? survivalProbability * 100
                      : survivalProbability,
                occurrence_count: toNumber(bin?.occurrence_count),
              };
            })
            .filter((row) => row.bin_floor !== null || row.bin_ceiling !== null)
        : [],
    [bins]
  );

  const isCurveAvailable = chartData.some((row) => row.cumulativePercent !== null || row.survivalPercent !== null);

  useEffect(() => {
    if (viewMode === "curve" && !isCurveAvailable) {
      setViewMode("histogram");
    }
  }, [isCurveAvailable, viewMode]);

  if (chartData.length === 0) {
    return (
      <div className="flex min-h-[21rem] flex-col items-center justify-center rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)]/60 px-6 py-10 text-center">
        <p className="text-sm font-semibold text-[var(--text-primary)]">No outcome distribution is available.</p>
        <p className="mt-2 max-w-md text-sm text-[var(--text-secondary)]">
          Distribution bins were not returned by the live payload for this set.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Outcome Distribution</p>
        <ViewModeToggle viewMode={viewMode} onChange={setViewMode} isCurveAvailable={isCurveAvailable} />
      </div>

      {IS_DEV && viewMode === "histogram" && !isCurveAvailable ? (
        <p className="mt-2 text-xs text-[var(--text-secondary)]">Curve disabled: cumulative/survival data unavailable in payload.</p>
      ) : null}

      <div className="mt-4 h-[23rem] w-full sm:h-[26rem]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 8, right: 16, left: 4, bottom: 8 }}>
            <CartesianGrid stroke="var(--border-subtle)" strokeOpacity={0.35} strokeDasharray="2 6" vertical={false} />
            <XAxis
              dataKey="rangeLabel"
              tickLine={false}
              axisLine={false}
              interval="preserveStartEnd"
              minTickGap={24}
              tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
              dy={8}
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              width={52}
              tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
              tickFormatter={(value) => `${toNumber(value)?.toFixed(0) || "0"}%`}
            />
            <Tooltip content={<HistogramTooltip />} cursor={{ fill: "rgba(255,255,255,0.03)" }} />

            {viewMode === "histogram" ? (
              <Bar
                dataKey="probabilityPercent"
                fill="var(--brand)"
                fillOpacity={0.88}
                radius={[4, 4, 0, 0]}
                maxBarSize={22}
              />
            ) : (
              <>
                <Line
                  type="monotone"
                  dataKey="cumulativePercent"
                  stroke="var(--brand)"
                  strokeWidth={2.4}
                  dot={false}
                  activeDot={{ r: 4, stroke: "var(--surface-page)", strokeWidth: 2 }}
                />
                <Line
                  type="monotone"
                  dataKey="survivalPercent"
                  stroke="rgba(255,255,255,0.62)"
                  strokeWidth={1.8}
                  strokeDasharray="4 4"
                  dot={false}
                />
              </>
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <MarkerChips markers={markers} />
    </div>
  );
}
