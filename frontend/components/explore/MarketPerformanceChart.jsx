"use client";

import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import usePointerMode, { POINTER_MODE_COARSE } from "@/hooks/usePointerMode";
import {
  TAP_MOVEMENT_THRESHOLD_PX,
  classifyPointerGesture,
} from "./compactSparklineInteraction.mjs";
import { positionMarketPerformanceTooltip } from "./marketPerformanceTooltipPosition.mjs";
import {
  buildMarketPerformanceDomain,
  buildRelativePerformanceDomain,
  isMarketIndexReferenceVisible,
  MARKET_CHART_VIEW_INDEX,
  MARKET_CHART_VIEW_PERFORMANCE,
  MARKET_INDEX_REFERENCE_VALUE,
  projectMarketChartValues,
} from "./marketPerformanceDomain.mjs";
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

// AREA FILL SCALES WITH SERIES COUNT. At two or three lines the soft gradient
// under each one reads as depth. At eight — which Market Explorer reaches once
// Sealed submarkets are overlaid — eight translucent fills stack into one muddy
// block and the lines stop being separable. The per-series opacity is therefore
// divided down past three series, so the homepage's three-line chart is
// byte-identical to before while the dense comparison stays legible.
const BASE_AREA_OPACITY = 0.16;
const AREA_OPACITY_FULL_AT = 3;

export function resolveAreaOpacity(seriesCount) {
  const count = Number.isFinite(seriesCount) ? seriesCount : 0;
  if (count <= AREA_OPACITY_FULL_AT) return BASE_AREA_OPACITY;
  return Math.max(0.03, (BASE_AREA_OPACITY * AREA_OPACITY_FULL_AT) / count);
}

export default function MarketPerformanceChart({ model, timeframe = "All", viewMode = MARKET_CHART_VIEW_PERFORMANCE, className = "", plotClassName = "h-56 desk:h-[19rem]" }) {
  const [activeIndex, setActiveIndex] = useState(null);
  const [tooltipAnchor, setTooltipAnchor] = useState(null);
  const [tooltipSize, setTooltipSize] = useState({ width: 248, height: 160 });
  const pointerMode = usePointerMode();
  const containerRef = useRef(null);
  const tooltipRef = useRef(null);
  const gestureRef = useRef(null);
  const chartId = useId().replace(/:/g, "");

  const dates = Array.isArray(model?.dates) ? model.dates : [];
  const rawSeries = Array.isArray(model?.series) ? model.series : [];
  const isIndexView = viewMode === MARKET_CHART_VIEW_INDEX;
  const series = rawSeries.map((entry) => ({
    ...entry,
    rawValues: entry.values || [],
    values: projectMarketChartValues(entry.values || [], viewMode),
    performanceValues: projectMarketChartValues(entry.values || [], MARKET_CHART_VIEW_PERFORMANCE),
  }));

  const clearSelection = () => { setActiveIndex(null); setTooltipAnchor(null); };
  const anchorFromBounds = (bounds, source = "keyboard", pointerYRatio = null) => ({
    bounds: { left: bounds.left, top: bounds.top, right: bounds.right, bottom: bounds.bottom, width: bounds.width, height: bounds.height },
    source,
    pointerYRatio,
  });
  const selectAtPointer = (clientX, clientY) => {
    const element = containerRef.current;
    if (!element || dates.length === 0) return;
    const bounds = element.getBoundingClientRect();
    const ratio = bounds.width > 0 ? (clientX - bounds.left) / bounds.width : 0;
    const clamped = Math.max(0, Math.min(1, Number.isFinite(ratio) ? ratio : 0));
    setActiveIndex(Math.round(clamped * Math.max(dates.length - 1, 0)));
    const yRatio = bounds.height > 0 ? (clientY - bounds.top) / bounds.height : 0.5;
    setTooltipAnchor(anchorFromBounds(bounds, "pointer", Math.max(0, Math.min(1, yRatio))));
  };
  const handlePointerMove = (event) => {
    if (event.pointerType === "mouse") return selectAtPointer(event.clientX, event.clientY);
    const gesture = gestureRef.current;
    if (!gesture) return;
    const kind = classifyPointerGesture({ startX: gesture.startX, startY: gesture.startY, currentX: event.clientX, currentY: event.clientY, threshold: TAP_MOVEMENT_THRESHOLD_PX });
    if (kind === "scroll") gestureRef.current = null;
    if (kind === "scrub") { gesture.moved = true; selectAtPointer(event.clientX, event.clientY); }
  };
  const handlePointerUp = (event) => {
    if (event.pointerType === "mouse") return;
    const gesture = gestureRef.current;
    gestureRef.current = null;
    if (!gesture || gesture.moved) return;
    selectAtPointer(event.clientX, event.clientY);
  };

  useEffect(() => {
    if (activeIndex === null || typeof window === "undefined") return undefined;
    const reanchor = () => {
      const element = containerRef.current;
      if (element) setTooltipAnchor((current) => current
        ? anchorFromBounds(element.getBoundingClientRect(), current.source, current.pointerYRatio)
        : current);
    };
    window.addEventListener("scroll", reanchor, true);
    window.addEventListener("resize", reanchor);
    return () => {
      window.removeEventListener("scroll", reanchor, true);
      window.removeEventListener("resize", reanchor);
    };
  }, [activeIndex]);

  useEffect(() => {
    const element = tooltipRef.current;
    if (!element || activeIndex === null) return undefined;
    const measure = () => {
      const bounds = element.getBoundingClientRect();
      setTooltipSize((current) => {
        const measuredWidth = Number.isFinite(bounds.width) && bounds.width > 0 ? bounds.width : current.width;
        const heightCandidate = Math.max(
          Number.isFinite(bounds.height) ? bounds.height : 0,
          Number.isFinite(element.scrollHeight) ? element.scrollHeight : 0,
        );
        const measuredHeight = heightCandidate > 0 ? heightCandidate : current.height;
        return current.width === measuredWidth && current.height === measuredHeight
          ? current
          : { width: measuredWidth, height: measuredHeight };
      });
    };
    measure();
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [activeIndex, series.length, viewMode]);

  const allValues = series.flatMap((entry) => (entry.values || []).filter((value) => value !== null).map((value) => ({ value })));
  if (series.length === 0) {
    return (
      <div data-market-performance-visibility-empty className={["flex items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 text-xs text-[var(--text-secondary)]", plotClassName, className].filter(Boolean).join(" ")}>
        Select a market to display.
      </div>
    );
  }
  if (dates.length < 2 || allValues.length < 2) {
    return (
      <div data-market-performance-empty className={["flex items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 text-xs text-[var(--text-secondary)]", plotClassName, className].filter(Boolean).join(" ")}>
        Not enough history to chart this range.
      </div>
    );
  }

  const [domainMin, domainMax] = isIndexView
    ? buildMarketPerformanceDomain(allValues, timeframe)
    : buildRelativePerformanceDomain(allValues);
  const yRange = domainMax - domainMin || 1;
  const xRange = Math.max(dates.length - 1, 1);
  const xAt = (index) => 2 + (index / xRange) * (VIEW_WIDTH - 4);
  const yAt = (value) => PLOT_BOTTOM - ((value - domainMin) / yRange) * (PLOT_BOTTOM - PLOT_TOP);
  const referenceValue = isIndexView ? MARKET_INDEX_REFERENCE_VALUE : 0;
  const referenceY = yAt(referenceValue);
  const referenceVisible = isIndexView ? isMarketIndexReferenceVisible([domainMin, domainMax]) : true;
  const gridValues = [0.25, 0.5, 0.75].map((ratio) => domainMin + (domainMax - domainMin) * ratio);
  const domainPrecision = domainMax - domainMin < 2 ? 2 : domainMax - domainMin < 10 ? 1 : 0;

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
    : drawn.map((entry) => ({
        key: entry.key,
        label: entry.label,
        color: entry.color,
        value: entry.values?.[activeIndex] ?? null,
        rawValue: entry.rawValues?.[activeIndex] ?? null,
        performanceValue: entry.performanceValues?.[activeIndex] ?? null,
        point: entry.pointMeta?.[activeIndex] || null,
      }));
  const spokenReading = activeDate
    ? `${formatMarketDate(activeDate)}. ${activeReadings.map((reading) => `${reading.label} index ${reading.rawValue === null ? "unavailable" : formatIndexValue(reading.rawValue)}, ${timeframe} performance ${reading.performanceValue === null ? "unavailable" : `${reading.performanceValue.toFixed(2)} percent`}${reading.point?.isCarriedForward ? `, previous close carried from ${formatMarketDate(reading.point.sourceDate)}` : ""}`).join(". ")}.`
    : null;
  const tooltipPosition = activeIndex === null || !tooltipAnchor
    ? null
    : positionMarketPerformanceTooltip({
        chartBounds: tooltipAnchor.bounds,
        crosshairX: tooltipAnchor.bounds.width * (xAt(activeIndex) / VIEW_WIDTH),
        pointerY: tooltipAnchor.pointerYRatio === null
          ? null
          : tooltipAnchor.bounds.top + tooltipAnchor.bounds.height * tooltipAnchor.pointerYRatio,
        tooltipWidth: tooltipSize.width,
        tooltipHeight: tooltipSize.height,
        viewportWidth: typeof window === "undefined" ? tooltipAnchor.bounds.right : window.innerWidth,
        viewportHeight: typeof window === "undefined" ? tooltipAnchor.bounds.bottom : window.innerHeight,
        interactionSource: tooltipAnchor.source,
      });

  const gradientPrefix = `market-performance-${chartId}`;
  const areaOpacity = resolveAreaOpacity(drawn.length);

  return (
    <div className={["min-w-0", className].filter(Boolean).join(" ")}>
      <div
        ref={containerRef}
        data-market-performance-chart
        data-market-chart-view={viewMode}
        data-market-performance-domain-min={domainMin}
        data-market-performance-domain-max={domainMax}
        data-pointer-mode={pointerMode}
        role="img"
        tabIndex={0}
        aria-label={spokenReading
          ? `${isIndexView ? "Pokémon canonical Market Index" : "Pokémon selected-window percentage performance"}. Selected ${spokenReading}`
          : `${isIndexView ? "Pokémon canonical Market Index" : "Pokémon selected-window percentage performance"}, ${formatMarketDate(dates[0])} to ${formatMarketDate(dates[dates.length - 1])}. Use left and right arrow keys to inspect daily values.`}
        className={["group relative z-10 touch-pan-y overflow-visible rounded-lg border border-[var(--border-subtle)] bg-[rgba(2,6,23,0.16)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]/65", plotClassName].join(" ")}
        onPointerDown={(event) => { if (event.pointerType !== "mouse") gestureRef.current = { startX: event.clientX, startY: event.clientY, moved: false }; }}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={() => { gestureRef.current = null; }}
        onPointerLeave={(event) => { if (event.pointerType === "mouse" || pointerMode !== POINTER_MODE_COARSE) clearSelection(); }}
        onFocus={(event) => {
          const bounds = event.currentTarget.getBoundingClientRect();
          setActiveIndex(dates.length - 1);
          setTooltipAnchor(anchorFromBounds(bounds, "keyboard"));
        }}
        onBlur={clearSelection}
        onKeyDown={(event) => {
          if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
            event.preventDefault();
            const step = event.key === "ArrowRight" ? 1 : -1;
            const base = activeIndex === null ? dates.length - 1 : activeIndex;
            setActiveIndex(Math.max(0, Math.min(dates.length - 1, base + step)));
            setTooltipAnchor(anchorFromBounds(event.currentTarget.getBoundingClientRect(), "keyboard"));
          } else if (event.key === "Escape") {
            clearSelection();
          }
        }}
      >
        <svg aria-hidden="true" viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`} preserveAspectRatio="none" className="h-full w-full overflow-visible rounded-lg">
          <defs>
            {drawn.map((entry) => (
              <linearGradient key={entry.key} id={`${gradientPrefix}-${entry.key}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={entry.color} stopOpacity={areaOpacity} />
                <stop offset="100%" stopColor={entry.color} stopOpacity="0" />
              </linearGradient>
            ))}
          </defs>
          {gridValues.map((value) => <line key={value} data-market-performance-grid x1="2" x2={VIEW_WIDTH - 2} y1={yAt(value)} y2={yAt(value)} stroke="rgba(148,163,184,0.13)" strokeWidth="1" vectorEffect="non-scaling-stroke" />)}
          {drawn.map((entry) => (entry.coordinates.length
            ? <path key={`${entry.key}-area`} data-market-performance-area={entry.key} d={`M ${entry.polyline.replaceAll(" ", " L ")} L ${entry.coordinates[entry.coordinates.length - 1].x.toFixed(2)},${PLOT_BOTTOM} L ${entry.coordinates[0].x.toFixed(2)},${PLOT_BOTTOM} Z`} fill={`url(#${gradientPrefix}-${entry.key})`} />
            : null))}
          {referenceVisible ? <line data-market-performance-reference={referenceValue} x1="2" x2={VIEW_WIDTH - 2} y1={referenceY} y2={referenceY} stroke="rgba(255,255,255,0.28)" strokeWidth="1" vectorEffect="non-scaling-stroke" /> : null}
          {drawn.map((entry) => (entry.coordinates.length >= 2
            ? <polyline key={`${entry.key}-line`} data-market-performance-series={entry.key} points={entry.polyline} fill="none" stroke={entry.color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
            : null))}
          {activeIndex === null ? null : (
            <line data-market-performance-guide x1={xAt(activeIndex)} x2={xAt(activeIndex)} y1={PLOT_TOP} y2={PLOT_BOTTOM} stroke="rgba(255,255,255,0.2)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
          )}
        </svg>
        {gridValues.map((value) => <span key={value} aria-hidden="true" className="pointer-events-none absolute right-1 text-[9px] tabular-nums text-[var(--text-secondary)]" style={{ top: `${(yAt(value) / VIEW_HEIGHT) * 100}%`, transform: "translateY(-50%)" }}>{isIndexView ? formatIndexValue(value) : `${value > 0 ? "+" : ""}${value.toFixed(domainPrecision)}%`}</span>)}
        {referenceVisible ? <span
          data-market-performance-reference-label
          aria-hidden="true"
          className="pointer-events-none absolute left-[2.5%] text-[9px] leading-none text-[var(--text-secondary)]"
          style={{ top: `${(referenceY / VIEW_HEIGHT) * 100}%`, transform: "translateY(-115%)" }}
        >
          {isIndexView ? formatIndexValue(referenceValue) : "0%"}
        </span> : null}
        {activeIndex === null ? null : drawn.map((entry) => {
          const value = entry.values?.[activeIndex] ?? null;
          if (value === null) return null;
          return (
            <span
              key={`${entry.key}-marker`}
              data-market-performance-marker={entry.key}
              aria-hidden="true"
              className="pointer-events-none absolute h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border border-current bg-[rgba(2,6,23,0.9)]"
              style={{ left: `${xAt(activeIndex)}%`, top: `${(yAt(value) / VIEW_HEIGHT) * 100}%`, color: entry.color }}
            />
          );
        })}
        {activeDate && tooltipPosition && typeof document !== "undefined"
          ? createPortal(
              <div
                ref={tooltipRef}
                data-market-performance-tooltip
                data-market-performance-tooltip-horizontal={tooltipPosition.horizontalPlacement}
                data-market-performance-tooltip-vertical={tooltipPosition.verticalPlacement}
                className="pointer-events-none fixed z-[80] overflow-y-auto rounded-lg border border-[var(--border-subtle)] bg-[rgba(2,6,23,0.96)] px-2.5 py-2 text-left shadow-[0_14px_32px_rgba(0,0,0,0.38)]"
                style={{ left: tooltipPosition.left, top: tooltipPosition.top, width: tooltipPosition.width, maxHeight: tooltipPosition.maxHeight }}
              >
                <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{formatMarketDate(activeDate)}</p>
                <ul className="mt-1 space-y-0.5">
                  {activeReadings.map((reading) => (
                    <li key={reading.key} className="flex items-center justify-between gap-3 text-[11px]">
                      <span className="inline-flex items-center gap-1.5 text-[var(--text-secondary)]">
                        <span aria-hidden="true" className="inline-block h-2 w-2 rounded-[2px]" style={{ backgroundColor: reading.color }} />
                          <span>
                            {reading.label}
                            <span className="block text-[9px]">{isIndexView ? "Canonical index" : `${timeframe} performance`}</span>
                          {reading.point?.isCarriedForward ? (
                            <span data-market-performance-carried-source={reading.key} className="block text-[9px]">
                              Last observed {formatShortDate(reading.point.sourceDate)}
                            </span>
                          ) : null}
                        </span>
                      </span>
                      <span className="text-right font-semibold tabular-nums text-[var(--text-primary)]">
                        {isIndexView ? (
                          <>
                            <span className="block">Market Index {reading.rawValue === null ? "—" : formatIndexValue(reading.rawValue)}</span>
                            <span className="block text-[9px] font-normal text-[var(--text-secondary)]">{timeframe} Performance {reading.performanceValue === null ? "—" : `${reading.performanceValue > 0 ? "+" : ""}${reading.performanceValue.toFixed(2)}%`}</span>
                          </>
                        ) : (
                          <>
                            <span className="block">{reading.performanceValue === null ? "—" : `${reading.performanceValue > 0 ? "+" : ""}${reading.performanceValue.toFixed(2)}%`}</span>
                            <span className="block text-[9px] font-normal text-[var(--text-secondary)]">Market Index {reading.rawValue === null ? "—" : formatIndexValue(reading.rawValue)}</span>
                          </>
                        )}
                      </span>
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
