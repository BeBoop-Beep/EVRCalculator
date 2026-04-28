"use client";

import { useMemo, useState } from "react";

import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

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

function clampProbability(value) {
  if (!Number.isFinite(value)) {
    return null;
  }
  if (value <= 0) {
    return 0;
  }
  if (value >= 1) {
    return 1;
  }
  return value;
}

function normalizeProbability(value) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return null;
  }
  return clampProbability(parsed > 1 ? parsed / 100 : parsed);
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

function formatAxisCurrency(value) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return "—";
  }
  return compactCurrencyFormatter.format(parsed);
}


function formatChancePercent(value, fallbackBelowOne = false) {
  const parsed = toNumber(value);
  if (fallbackBelowOne || (Number.isFinite(parsed) && parsed > 0 && parsed < 1)) {
    return "Below 1%";
  }
  if (parsed === null) {
    return "—";
  }
  return `${parsed.toFixed(2)}%`;
}

// Maps a marker key/label to the inverse-percentile chance_to_reach_percent.
// NOTE: This mapping is kept for reference but no longer used.
// Line data now derives directly from bin survival_probability.
const PERCENTILE_CHANCE_MAP_DEPRECATED = [
  { patterns: ["p5", "5th"], chance: 95 },
  { patterns: ["p25", "25th"], chance: 75 },
  { patterns: ["p50", "50th", "median"], chance: 50 },
  { patterns: ["p75", "75th"], chance: 25 },
  { patterns: ["p90", "90th"], chance: 10 },
  { patterns: ["p95", "95th"], chance: 5 },
  { patterns: ["p99", "99th"], chance: 1 },
];

function CombinedTooltip({ active, payload }) {
  if (!active || !payload?.length) {
    return null;
  }
  const row = payload[0]?.payload;
  if (!row) {
    return null;
  }
  const hasBin =
    row.exact_frequency_percent !== null &&
    row.exact_frequency_percent !== undefined &&
    Number.isFinite(row.bin_floor);
  const hasCurve =
    row.chance_to_reach_percent !== null &&
    row.chance_to_reach_percent !== undefined;

  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)]/95 px-3 py-2 shadow-[0_16px_40px_rgba(0,0,0,0.35)] backdrop-blur-sm">
      {hasBin ? (
        <>
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Outcome Range</p>
          <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
            {String(row.range_label || "").trim() || `${formatCompactCurrency(row.bin_floor)} – ${formatCompactCurrency(row.bin_ceiling)}`}
          </p>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">
            Frequency&nbsp;
            <span className="font-semibold text-[var(--text-primary)]">
              {Number.isFinite(row.exact_frequency_percent) ? `${row.exact_frequency_percent.toFixed(2)}%` : "—"}
            </span>
          </p>
          {Number.isFinite(row.occurrence_count) ? (
            <p className="text-xs text-[var(--text-secondary)]">Count {formatCount(row.occurrence_count)}</p>
          ) : null}
          {Number.isFinite(row.survival_probability) ? (
            <p className="text-xs text-[var(--text-secondary)]">
              Chance at least this value {formatChancePercent(row.survival_probability * 100)}
            </p>
          ) : null}
        </>
      ) : null}
      {hasCurve ? (
        <p className={`text-xs text-[var(--text-secondary)] ${hasBin ? "mt-2 border-t border-[var(--border-subtle)] pt-2" : ""}`}>
          {row.curve_label ? (
            <span className="mr-1 font-semibold text-[var(--text-primary)]">{row.curve_label}:</span>
          ) : null}
          About{" "}
          <span className="font-semibold text-[var(--text-primary)]">
            {formatChancePercent(row.chance_to_reach_percent, row.curve_below_one_fallback === true)}
          </span>
          {" "}of packs reach at least{" "}
          <span className="font-semibold text-[var(--text-primary)]">
            {formatCompactCurrency(row.curve_exact_value ?? row.exact_value)}
          </span>
        </p>
      ) : null}
    </div>
  );
}

function MarkerChips({ markers, activeMarkerKey, onMarkerClick }) {
  const markerRows = useMemo(
    () =>
      (Array.isArray(markers) ? markers : [])
        .map((marker) => ({
          key: String(marker?.key || marker?.label || "").trim(),
          label: String(marker?.label || "").trim(),
          value: toNumber(marker?.value),
        }))
        .filter((marker) => marker.label && marker.value !== null),
    [markers]
  );

  if (markerRows.length === 0) {
    return null;
  }

  return (
    <div className="mt-4 flex flex-wrap gap-2">
      {markerRows.map((marker) => (
        <button
          key={marker.key}
          type="button"
          onClick={() => onMarkerClick(marker.key)}
          aria-pressed={activeMarkerKey === marker.key}
          className={`inline-flex h-7 items-center rounded-full border px-3 text-xs transition-colors ${
            activeMarkerKey === marker.key
              ? "border-[var(--brand)] bg-[color:color-mix(in_srgb,var(--brand)_14%,transparent)] text-[var(--text-primary)]"
              : "border-[var(--border-subtle)] bg-[var(--surface-page)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          }`}
        >
          {marker.label}: <span className="ml-1 font-semibold text-[var(--text-primary)]">{formatCompactCurrency(marker.value)}</span>
        </button>
      ))}
    </div>
  );
}

function ActiveMarkerLabel({ viewBox, label, value, slotIndex, totalSlots }) {
  if (!viewBox) return null;
  const { x, y } = viewBox;
  // Position the callout: to the right of the line if in the left half, otherwise to the left
  const isRightHalf = slotIndex >= Math.floor(totalSlots / 2);
  const boxWidth = 80;
  const boxHeight = 42;
  const offsetX = isRightHalf ? -(boxWidth + 8) : 8;
  const boxX = x + offsetX;
  const boxY = y + 8;
  return (
    <g>
      <rect
        x={boxX}
        y={boxY}
        width={boxWidth}
        height={boxHeight}
        rx={6}
        ry={6}
        fill="rgba(15,23,30,0.88)"
        stroke="rgba(20,184,166,0.65)"
        strokeWidth={1}
      />
      <text
        x={boxX + boxWidth / 2}
        y={boxY + 16}
        textAnchor="middle"
        fontSize={13}
        fontWeight="600"
        fill="rgba(20,184,166,0.98)"
      >
        {label}
      </text>
      <text
        x={boxX + boxWidth / 2}
        y={boxY + 33}
        textAnchor="middle"
        fontSize={14}
        fontWeight="700"
        fill="rgba(255,255,255,0.92)"
      >
        {value}
      </text>
    </g>
  );
}

function EmptyChartState({ title, body }) {
  return (
    <div className="flex min-h-[26rem] flex-col items-center justify-center rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)]/60 px-6 py-10 text-center">
      <p className="text-sm font-semibold text-[var(--text-primary)]">{title}</p>
      <p className="mt-2 max-w-md text-sm text-[var(--text-secondary)]">{body}</p>
    </div>
  );
}

export default function RipDistributionChart({ bins = [], thresholdBins = [], markers = [] }) {
  const [activeMarkerKey, setActiveMarkerKey] = useState(null);
  const [viewMode, setViewMode] = useState("full");
  const [showBars, setShowBars] = useState(true);
  const [showLine, setShowLine] = useState(true);
  const hasThresholdBins = Array.isArray(thresholdBins) && thresholdBins.length > 0;

  const chartData = useMemo(() => {
    const rows = hasThresholdBins
      ? thresholdBins
          .map((bin, index) => {
            const floor = toNumber(bin?.threshold_floor);
            const ceiling = toNumber(bin?.threshold_ceiling);
            const occurrenceCount = toNumber(bin?.occurrence_count);
            const probability = normalizeProbability(bin?.probability);
            const cumulativeProbability = normalizeProbability(bin?.cumulative_probability);
            const survivalProbabilityDirect = normalizeProbability(bin?.survival_probability);
            const survivalProbabilityFallback =
              cumulativeProbability !== null && probability !== null
                ? clampProbability(1 - cumulativeProbability + probability)
                : null;
            const survivalProbability = survivalProbabilityDirect ?? survivalProbabilityFallback;
            const midpoint =
              floor !== null && ceiling !== null
                ? (floor + ceiling) / 2
                : floor ?? ceiling;
            const bucketOrder = toNumber(bin?.bucket_order);
            const bucketLabel = String(bin?.bucket_label || "").trim();

            return {
              id: `${index}:${bin?.threshold_floor ?? "na"}:${bin?.bucket_order ?? "na"}`,
              sort_order: bucketOrder,
              bin_floor: floor,
              bin_ceiling: ceiling,
              occurrence_count: occurrenceCount,
              exact_midpoint: midpoint,
              range_label:
                bucketLabel ||
                (floor === null && ceiling === null
                  ? `Bin ${index + 1}`
                  : `${formatCompactCurrency(floor)}–${formatCompactCurrency(ceiling)}`),
              probability,
              cumulative_probability: cumulativeProbability,
              survival_probability: survivalProbability,
            };
          })
          .filter((row) => row.bin_floor !== null || row.bin_ceiling !== null)
      : (Array.isArray(bins) ? bins : [])
          .map((bin, index) => {
            const floor = toNumber(bin?.bin_floor);
            const ceiling = toNumber(bin?.bin_ceiling);
            const occurrenceCount = toNumber(bin?.occurrence_count);
            const probability = normalizeProbability(bin?.probability);
            const cumulativeProbability = normalizeProbability(bin?.cumulative_probability);
            const survivalProbabilityDirect = normalizeProbability(bin?.survival_probability);
            const survivalProbabilityFallback =
              cumulativeProbability !== null && probability !== null
                ? clampProbability(1 - cumulativeProbability + probability)
                : null;
            const survivalProbability = survivalProbabilityDirect ?? survivalProbabilityFallback;
            const midpoint =
              floor !== null && ceiling !== null
                ? (floor + ceiling) / 2
                : floor ?? ceiling;

            return {
              id: `${index}:${bin?.bin_floor ?? "na"}`,
              sort_order: index + 1,
              bin_floor: floor,
              bin_ceiling: ceiling,
              occurrence_count: occurrenceCount,
              exact_midpoint: midpoint,
              range_label:
                floor === null && ceiling === null
                  ? `Bin ${index + 1}`
                  : `${formatCompactCurrency(floor)}–${formatCompactCurrency(ceiling)}`,
              probability,
              cumulative_probability: cumulativeProbability,
              survival_probability: survivalProbability,
            };
          })
          .filter((row) => row.bin_floor !== null || row.bin_ceiling !== null);

    if (hasThresholdBins) {
      rows.sort((left, right) => {
        const leftOrder = toNumber(left.sort_order) ?? Number.MAX_SAFE_INTEGER;
        const rightOrder = toNumber(right.sort_order) ?? Number.MAX_SAFE_INTEGER;
        if (leftOrder !== rightOrder) {
          return leftOrder - rightOrder;
        }
        const leftFloor = toNumber(left.bin_floor) ?? Number.MAX_SAFE_INTEGER;
        const rightFloor = toNumber(right.bin_floor) ?? Number.MAX_SAFE_INTEGER;
        return leftFloor - rightFloor;
      });
    }

    return rows;
  }, [bins, hasThresholdBins, thresholdBins]);

  const histogramData = useMemo(
    () =>
      chartData
        .filter((row) => typeof row.range_label === "string" && Number.isFinite(row.probability))
        .map((row, index) => ({
          ...row,
          slot_index: index,
          id: `bin:${index}:${row.bin_floor}:${row.bin_ceiling}`,
          exact_value: row.exact_midpoint,
          exact_frequency_percent: row.probability * 100,
        })),
    [chartData]
  );

  const coreCutoffIndex = useMemo(() => {
    if (!histogramData.length) {
      return -1;
    }

    const thresholdIndex = histogramData.findIndex((row) => {
      const cumulative = toNumber(row.cumulative_probability);
      return cumulative !== null && cumulative >= 0.99;
    });

    if (thresholdIndex >= 0) {
      return thresholdIndex;
    }

    return Math.min(histogramData.length - 1, Math.max(9, Math.floor(histogramData.length * 0.6)));
  }, [histogramData]);

  const displayBinData = useMemo(() => {
    if (viewMode === "full") {
      return histogramData;
    }
    if (coreCutoffIndex < 0) {
      return histogramData;
    }
    return histogramData.slice(0, coreCutoffIndex + 1);
  }, [coreCutoffIndex, histogramData, viewMode]);

  const markerRows = useMemo(
    () =>
      (Array.isArray(markers) ? markers : [])
        .map((marker) => ({
          key: String(marker?.key || marker?.label || "").trim(),
          label: String(marker?.label || "").trim(),
          value: toNumber(marker?.value),
        }))
        .filter((marker) => marker.key && marker.value !== null),
    [markers]
  );

  const combinedData = useMemo(() => {
    const rows = displayBinData.map((row) => ({
      ...row,
      x_slot: String(row.slot_index),
      // Populate chance_to_reach_percent directly from threshold bin survival_probability
      chance_to_reach_percent: (row.survival_probability ?? null) !== null ? row.survival_probability * 100 : null,
      curve_label: null,
      curve_exact_value: null,
      curve_below_one_fallback: false,
    }));

    const maxFrequencyPercent = Math.max(
      ...rows.map((row) => row.exact_frequency_percent ?? 0).filter(Number.isFinite),
      1
    );

    rows.forEach((row) => {
      if (Number.isFinite(row.exact_frequency_percent)) {
        row.frequency_shape_score = Math.pow(row.exact_frequency_percent / maxFrequencyPercent, 0.35) * 90;
      }
    });

    const findSlotForValue = (value) => {
      const exactMatch = rows.find((row) => {
        const floor = toNumber(row.bin_floor);
        const ceiling = toNumber(row.bin_ceiling);
        if (floor !== null && ceiling !== null) {
          return value >= floor && value < ceiling;
        }
        if (floor !== null && ceiling === null) {
          return value >= floor;
        }
        if (floor === null && ceiling !== null) {
          return value < ceiling;
        }
        return false;
      });
      if (exactMatch) {
        return exactMatch.slot_index;
      }

      let nearest = null;
      let nearestDistance = Number.POSITIVE_INFINITY;
      for (const row of rows) {
        const midpoint = toNumber(row.exact_value);
        if (midpoint === null) {
          continue;
        }
        const distance = Math.abs(value - midpoint);
        if (distance < nearestDistance) {
          nearestDistance = distance;
          nearest = row.slot_index;
        }
      }
      return nearest;
    };

    // Map marker values to category slots for ReferenceLine rendering.
    // Markers are annotations only; they don't drive the line curve.
    for (const marker of markerRows) {
      const slot = findSlotForValue(marker.value);
      if (slot !== null && slot !== undefined) {
        const row = rows.find((candidate) => candidate.slot_index === slot);
        if (row) {
          row._marker_slot = slot;
        }
      }
    }

    return rows;
  }, [displayBinData, markerRows]);

  // Check if curve is available: at least 2 displayed rows have valid survival_probability-derived chance_to_reach_percent.
  const isCurveAvailable = useMemo(() => {
    const validRows = combinedData.filter(
      (row) => row.chance_to_reach_percent !== null && Number.isFinite(row.chance_to_reach_percent)
    );
    return validRows.length >= 2;
  }, [combinedData]);

  // Map marker values to category slots for ReferenceLine rendering.
  const markerSlotsMap = useMemo(() => {
    const map = new Map();
    const findSlotForValue = (value) => {
      const exactMatch = combinedData.find((row) => {
        const floor = toNumber(row.bin_floor);
        const ceiling = toNumber(row.bin_ceiling);
        if (floor !== null && ceiling !== null) {
          return value >= floor && value < ceiling;
        }
        if (floor !== null && ceiling === null) {
          return value >= floor;
        }
        if (floor === null && ceiling !== null) {
          return value < ceiling;
        }
        return false;
      });
      if (exactMatch) {
        return exactMatch.x_slot;
      }

      let nearest = null;
      let nearestDistance = Number.POSITIVE_INFINITY;
      for (const row of combinedData) {
        const midpoint = toNumber(row.exact_value);
        if (midpoint === null) {
          continue;
        }
        const distance = Math.abs(value - midpoint);
        if (distance < nearestDistance) {
          nearestDistance = distance;
          nearest = row.x_slot;
        }
      }
      return nearest;
    };

    for (const marker of markerRows) {
      const slot = findSlotForValue(marker.value);
      if (slot !== null && slot !== undefined) {
        map.set(marker.key, slot);
      }
    }
    return map;
  }, [combinedData, markerRows]);

  // Detect which markers share the same slot (for handling overlapping markers).
  const markersBySlot = useMemo(() => {
    const slotMap = new Map();
    for (const [markerKey, slot] of markerSlotsMap.entries()) {
      if (!slotMap.has(slot)) {
        slotMap.set(slot, []);
      }
      slotMap.get(slot).push(markerKey);
    }
    return slotMap;
  }, [markerSlotsMap]);

  if (histogramData.length === 0) {
    return <EmptyChartState title="No outcome distribution is available." body="Distribution bins were not returned by the live payload for this set." />;
  }

  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Outcome Distribution</p>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Bars show the shape of outcome frequency. Line shows the chance of reaching at least each value.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="inline-flex items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-0.5">
            <button
              type="button"
              onClick={() => setViewMode("core")}
              aria-pressed={viewMode === "core"}
              className={`min-w-[5.2rem] rounded-md px-3 py-1 text-[11px] font-semibold leading-none transition-colors ${
                viewMode === "core"
                  ? "bg-[var(--brand)] text-white"
                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              Core View
            </button>
            <button
              type="button"
              onClick={() => setViewMode("full")}
              aria-pressed={viewMode === "full"}
              className={`min-w-[5.2rem] rounded-md px-3 py-1 text-[11px] font-semibold leading-none transition-colors ${
                viewMode === "full"
                  ? "bg-[var(--brand)] text-white"
                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              Full Range
            </button>
          </div>
          <div className="flex items-center gap-3 text-[11px]">
            <button
              type="button"
              onClick={() => setShowBars(!showBars)}
              aria-pressed={showBars}
              className={`inline-flex items-center gap-1.5 rounded px-2 py-1 transition-colors ${
                showBars
                  ? "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                  : "text-[var(--text-secondary)]/50 hover:text-[var(--text-secondary)]"
              }`}
            >
              <span className={`inline-block h-2.5 w-2.5 rounded-sm ${
                showBars
                  ? "bg-[rgba(20,184,166,0.45)]"
                  : "bg-[rgba(20,184,166,0.15)]"
              }`} />
              Frequency Shape
            </button>
            {isCurveAvailable ? (
              <button
                type="button"
                onClick={() => setShowLine(!showLine)}
                aria-pressed={showLine}
                className={`inline-flex items-center gap-1.5 rounded px-2 py-1 transition-colors ${
                  showLine
                    ? "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                    : "text-[var(--text-secondary)]/50 hover:text-[var(--text-secondary)]"
                }`}
              >
                <span className={`inline-block h-0.5 w-5 rounded ${
                  showLine
                    ? "bg-[rgba(94,234,212,0.98)]"
                    : "bg-[rgba(94,234,212,0.25)]"
                }`} />
                Chance To Reach
              </button>
            ) : null}
          </div>
        </div>
      </div>

      <div className="mt-4 h-[20rem] w-full sm:h-[23rem]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={combinedData} margin={{ top: 8, right: 56, left: 4, bottom: 8 }}>
            <CartesianGrid stroke="var(--border-subtle)" strokeOpacity={0.28} strokeDasharray="2 8" vertical={false} />

            <XAxis
              type="category"
              dataKey="x_slot"
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
              tickFormatter={(slot) => {
                const row = combinedData.find((candidate) => String(candidate.x_slot) === String(slot));
                return formatAxisCurrency(row?.exact_value);
              }}
              interval="preserveStartEnd"
              minTickGap={24}
              dy={8}
            />

            <YAxis
              yAxisId="left"
              orientation="left"
              tickLine={false}
              axisLine={false}
              width={12}
              tick={false}
            />

            <YAxis
              yAxisId="right"
              orientation="right"
              domain={[0, 100]}
              tickLine={false}
              axisLine={false}
              width={44}
              tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
              tickFormatter={(v) => `${Number(v).toFixed(0)}%`}
            />

            <Tooltip content={<CombinedTooltip />} cursor={{ fill: "rgba(255,255,255,0.03)" }} />

            {Array.from(markerSlotsMap.entries()).map(([markerKey, slot]) => {
              const markersInSlot = markersBySlot.get(slot) || [];
              const isActiveInSlot = activeMarkerKey && activeMarkerKey === markerKey;
              const hasMultipleInSlot = markersInSlot.length > 1;

              // When multiple markers share a slot, only render the active one prominently.
              if (hasMultipleInSlot && activeMarkerKey && !isActiveInSlot) {
                return null;
              }

              const activeMarker = isActiveInSlot
                ? markerRows.find((m) => m.key === markerKey)
                : null;
              const slotIndex = toNumber(slot);

              // Find which bucket this marker falls in for the optional bucket label
              const bucketRow = isActiveInSlot
                ? combinedData.find((row) => String(row.x_slot) === String(slot))
                : null;
              const bucketLabel = bucketRow?.range_label || null;

              return (
                <ReferenceLine
                  key={`marker:${markerKey}`}
                  yAxisId="left"
                  x={slot}
                  stroke={
                    isActiveInSlot
                      ? "rgba(20,184,166,0.98)"
                      : hasMultipleInSlot && activeMarkerKey
                      ? "rgba(255,255,255,0.08)"
                      : "rgba(255,255,255,0.16)"
                  }
                  strokeWidth={isActiveInSlot ? 2.5 : 1}
                  strokeDasharray={isActiveInSlot ? "6 3" : "2 6"}
                  ifOverflow="extendDomain"
                  label={isActiveInSlot && activeMarker ? (
                    <ActiveMarkerLabel
                      label={activeMarker.label}
                      value={formatAxisCurrency(activeMarker.value)}
                      slotIndex={slotIndex !== null ? slotIndex : 0}
                      totalSlots={combinedData.length}
                    />
                  ) : null}
                />
              );
            })}

            {showBars ? (
              <Bar
                yAxisId="left"
                dataKey="frequency_shape_score"
                fill="rgba(20,184,166,0.22)"
                stroke="rgba(20,184,166,0.45)"
                strokeWidth={0.5}
                radius={[2, 2, 0, 0]}
                barCategoryGap="7%"
                barGap={0}
                minPointSize={2}
                isAnimationActive={false}
              />
            ) : null}

            {isCurveAvailable && showLine ? (
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="chance_to_reach_percent"
                stroke="rgba(94,234,212,0.98)"
                strokeWidth={3}
                dot={{ r: 4, fill: "rgba(94,234,212,0.95)", strokeWidth: 0 }}
                activeDot={{ r: 6, stroke: "var(--surface-page)", strokeWidth: 2 }}
                connectNulls
                isAnimationActive={false}
              />
            ) : null}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-1 min-h-[1rem]" aria-hidden="true" />

      <MarkerChips
        markers={markerRows}
        activeMarkerKey={activeMarkerKey}
        onMarkerClick={(markerKey) => setActiveMarkerKey((current) => (current === markerKey ? null : markerKey))}
      />

      <p className="mt-2 text-xs text-[var(--text-secondary)]">
        Bars are grouped to reveal the distribution shape. Hover for exact frequencies and odds.
      </p>
    </div>
  );
}
