"use client";

import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import usePointerMode, { POINTER_MODE_COARSE } from "@/hooks/usePointerMode";
import {
  TAP_MOVEMENT_THRESHOLD_PX,
  classifyPointerGesture,
  clampTooltipX,
} from "./compactSparklineInteraction.mjs";
import { buildMarketSparklineDomain } from "./marketSparklineDomain.mjs";
import { formatIndexValue, formatMarketDate, formatShortDate } from "@/lib/explore/marketOverviewPresentation.mjs";

// Purpose-built dual-series index chart.
//
// MarketSparkline is single-series and owns its own tooltip; two of them
// stacked would produce two competing selections and two tooltips. This keeps
// its interaction contract — pointer inspection, touch scrub vs. page scroll,
// arrow-key stepping, a portalled (unclippable) tooltip, responsive SVG — but
// drives ONE shared selection across both series and reports both values.
//
// Y values are normalized index values only; the two baskets' dollar totals
// never share this axis.
const VIEW_WIDTH = 100;
const VIEW_HEIGHT = 46;
const PLOT_TOP = 3;
const PLOT_BOTTOM = 43;

export default function MarketPerformanceChart({ model, className = "", plotClassName = "h-56 desk:h-[19rem]" }) {
  const [activeIndex, setActiveIndex] = useState(null);
  const [tooltipX, setTooltipX] = useState(null);
  const [tooltipAnchor, setTooltipAnchor] = useState(null);
  const pointerMode = usePointerMode();
  const containerRef = useRef(null);
  const gestureRef = useRef(null);
  const chartId = useId().replace(/:/g, "");

  const dates = Array.isArray(model?.dates) ? model.dates : [];
  const series = Array.isArray(model?.series) ? model.series : [];

  const clearSelection = () => { setActiveIndex(null); setTooltipX(null); setTooltipAnchor(null); };
  const anchorFromBounds = (bounds) => ({ left: bounds.left, top: bounds.top });
  const selectAtClientX = (clientX) => {
    const element = containerRef.current;
    if (!element || dates.length === 0) return;
    const bounds = element.getBoundingClientRect();
    const ratio = bounds.width > 0 ? (clientX - bounds.left) / bounds.width : 0;
    const clamped = Math.max(0, Math.min(1, Number.isFinite(ratio) ? ratio : 0));
    setActiveIndex(Math.round(clamped * Math.max(dates.length - 1, 0)));
    setTooltipX(clampTooltipX({ chartLeft: bounds.left, chartWidth: bounds.width, pointerX: clientX - bounds.left, tooltipWidth: 248, viewportWidth: typeof window === "undefined" ? bounds.width : window.innerWidth, gutter: 8 }));
    setTooltipAnchor(anchorFromBounds(bounds));
  };
  const handlePointerMove = (event) => {
    if (event.pointerType === "mouse") return selectAtClientX(event.clientX);
    const gesture = gestureRef.current;
    if (!gesture) return;
    const kind = classifyPointerGesture({ startX: gesture.startX, startY: gesture.startY, currentX: event.clientX, currentY: event.clientY, threshold: TAP_MOVEMENT_THRESHOLD_PX });
    if (kind === "scroll") gestureRef.current = null;
    if (kind === "scrub") { gesture.moved = true; selectAtClientX(event.clientX); }
  };
  const handlePointerUp = (event) => {
    if (event.pointerType === "mouse") return;
    const gesture = gestureRef.current;
    gestureRef.current = null;
    if (!gesture || gesture.moved) return;
    selectAtClientX(event.clientX);
  };

  useEffect(() => {
    if (activeIndex === null || typeof window === "undefined") return undefined;
    const reanchor = () => {
      const element = containerRef.current;
      if (element) setTooltipAnchor(anchorFromBounds(element.getBoundingClientRect()));
    };
    window.addEventListener("scroll", reanchor, true);
    window.addEventListener("resize", reanchor);
    return () => {
      window.removeEventListener("scroll", reanchor, true);
      window.removeEventListener("resize", reanchor);
    };
  }, [activeIndex]);

  const allValues = series.flatMap((entry) => (entry.values || []).filter((value) => value !== null).map((value) => ({ value })));
  if (dates.length < 2 || allValues.length < 2) {
    return (
      <div data-market-performance-empty className={["flex items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 text-xs text-[var(--text-secondary)]", plotClassName, className].filter(Boolean).join(" ")}>
        Not enough history to chart this range.
      </div>
    );
  }

  const [domainMin, domainMax] = buildMarketSparklineDomain(allValues, { valueKey: "value" });
  const yRange = domainMax - domainMin || 1;
  const xRange = Math.max(dates.length - 1, 1);
  const xAt = (index) => 2 + (index / xRange) * (VIEW_WIDTH - 4);
  const yAt = (value) => PLOT_BOTTOM - ((value - domainMin) / yRange) * (PLOT_BOTTOM - PLOT_TOP);

  const drawn = series.map((entry) => {
    const coordinates = (entry.values || [])
      .map((value, index) => (value === null ? null : { index, value, x: xAt(index), y: yAt(value) }))
      .filter(Boolean);
    return {
      ...entry,
      coordinates,
      polyline: coordinates.map(({ x, y }) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" "),
    };
  });

  const activeDate = activeIndex === null ? null : dates[activeIndex] || null;
  const activeReadings = activeIndex === null
    ? []
    : drawn.map((entry) => ({ key: entry.key, label: entry.label, color: entry.color, value: entry.values?.[activeIndex] ?? null }));
  const spokenReading = activeDate
    ? `${formatMarketDate(activeDate)}. ${activeReadings.map((reading) => `${reading.label} index ${reading.value === null ? "unavailable" : formatIndexValue(reading.value)}`).join(". ")}.`
    : null;

  const gradientPrefix = `market-performance-${chartId}`;

  return (
    <div className={["min-w-0", className].filter(Boolean).join(" ")}>
      <div
        ref={containerRef}
        data-market-performance-chart
        data-pointer-mode={pointerMode}
        role="img"
        tabIndex={0}
        aria-label={spokenReading
          ? `Pokémon Market Performance. Selected ${spokenReading}`
          : `Pokémon Market Performance, ${formatMarketDate(dates[0])} to ${formatMarketDate(dates[dates.length - 1])}. Use left and right arrow keys to inspect daily index values.`}
        className={["group relative z-10 touch-pan-y overflow-visible rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]/65", plotClassName].join(" ")}
        onPointerDown={(event) => { if (event.pointerType !== "mouse") gestureRef.current = { startX: event.clientX, startY: event.clientY, moved: false }; }}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={() => { gestureRef.current = null; }}
        onPointerLeave={(event) => { if (event.pointerType === "mouse" || pointerMode !== POINTER_MODE_COARSE) clearSelection(); }}
        onFocus={(event) => {
          const bounds = event.currentTarget.getBoundingClientRect();
          setActiveIndex(dates.length - 1);
          setTooltipX(clampTooltipX({ chartLeft: bounds.left, chartWidth: bounds.width, pointerX: bounds.width / 2, tooltipWidth: 248, viewportWidth: typeof window === "undefined" ? bounds.width : window.innerWidth }));
          setTooltipAnchor(anchorFromBounds(bounds));
        }}
        onBlur={clearSelection}
        onKeyDown={(event) => {
          if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
            event.preventDefault();
            const step = event.key === "ArrowRight" ? 1 : -1;
            const base = activeIndex === null ? dates.length - 1 : activeIndex;
            setActiveIndex(Math.max(0, Math.min(dates.length - 1, base + step)));
            setTooltipAnchor(anchorFromBounds(event.currentTarget.getBoundingClientRect()));
          } else if (event.key === "Escape") {
            clearSelection();
          }
        }}
      >
        <svg aria-hidden="true" viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`} preserveAspectRatio="none" className="h-full w-full overflow-visible rounded-lg">
          <defs>
            {drawn.map((entry) => (
              <linearGradient key={entry.key} id={`${gradientPrefix}-${entry.key}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={entry.color} stopOpacity="0.16" />
                <stop offset="100%" stopColor={entry.color} stopOpacity="0" />
              </linearGradient>
            ))}
          </defs>
          {[0, 0.5, 1].map((fraction) => (
            <line key={fraction} x1="2" x2={VIEW_WIDTH - 2} y1={PLOT_TOP + fraction * (PLOT_BOTTOM - PLOT_TOP)} y2={PLOT_TOP + fraction * (PLOT_BOTTOM - PLOT_TOP)} stroke="rgba(255,255,255,0.055)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
          ))}
          {drawn.map((entry) => (entry.coordinates.length
            ? <path key={`${entry.key}-area`} d={`M ${entry.polyline.replaceAll(" ", " L ")} L ${entry.coordinates[entry.coordinates.length - 1].x.toFixed(2)},${PLOT_BOTTOM} L ${entry.coordinates[0].x.toFixed(2)},${PLOT_BOTTOM} Z`} fill={`url(#${gradientPrefix}-${entry.key})`} />
            : null))}
          {drawn.map((entry) => (
            <polyline key={`${entry.key}-line`} data-market-performance-series={entry.key} points={entry.polyline} fill="none" stroke={entry.color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
          ))}
          {activeIndex === null ? null : (
            <line data-market-performance-guide x1={xAt(activeIndex)} x2={xAt(activeIndex)} y1={PLOT_TOP} y2={PLOT_BOTTOM} stroke="rgba(255,255,255,0.2)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
          )}
        </svg>
        {activeIndex === null ? null : drawn.map((entry) => {
          const value = entry.values?.[activeIndex] ?? null;
          if (value === null) return null;
          return (
            <span
              key={`${entry.key}-marker`}
              aria-hidden="true"
              className="pointer-events-none absolute h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border border-current bg-[rgba(2,6,23,0.9)]"
              style={{ left: `${xAt(activeIndex)}%`, top: `${(yAt(value) / VIEW_HEIGHT) * 100}%`, color: entry.color }}
            />
          );
        })}
        {activeDate && tooltipX !== null && tooltipAnchor && typeof document !== "undefined"
          ? createPortal(
              <div
                data-market-performance-tooltip
                className="pointer-events-none fixed z-[80] min-w-[11rem] max-w-[min(16rem,calc(100vw-1rem))] rounded-lg border border-[var(--border-subtle)] bg-[rgba(2,6,23,0.96)] px-2.5 py-2 text-left shadow-[0_14px_32px_rgba(0,0,0,0.38)]"
                style={{ left: tooltipAnchor.left + tooltipX, top: tooltipAnchor.top - 10, transform: "translate(-50%, -100%)" }}
              >
                <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{formatMarketDate(activeDate)}</p>
                <ul className="mt-1 space-y-0.5">
                  {activeReadings.map((reading) => (
                    <li key={reading.key} className="flex items-center justify-between gap-3 text-[11px]">
                      <span className="inline-flex items-center gap-1.5 text-[var(--text-secondary)]">
                        <span aria-hidden="true" className="inline-block h-2 w-2 rounded-[2px]" style={{ backgroundColor: reading.color }} />
                        {reading.label}
                      </span>
                      <span className="font-semibold tabular-nums text-[var(--text-primary)]">{reading.value === null ? "—" : formatIndexValue(reading.value)}</span>
                    </li>
                  ))}
                </ul>
              </div>,
              document.body
            )
          : null}
      </div>
      <div data-market-performance-dates className="mt-1.5 flex items-center justify-between gap-2 text-[10px] text-[var(--text-secondary)]">
        <span>{formatShortDate(dates[0])}</span>
        <span className="text-right">{formatShortDate(dates[dates.length - 1])}</span>
      </div>
    </div>
  );
}
