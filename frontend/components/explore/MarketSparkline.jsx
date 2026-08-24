"use client";

import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import usePointerMode, { POINTER_MODE_COARSE } from "@/hooks/usePointerMode";
import { computeChangeFromBaseline } from "@/lib/explore/marketDeltaWindows.mjs";
import { NEGATIVE_VALUE_COLOR, POSITIVE_VALUE_COLOR } from "@/lib/explore/interpretationTone";
import MarketTrendTooltipCard from "./MarketTrendTooltipCard";
import {
  TAP_MOVEMENT_THRESHOLD_PX,
  classifyPointerGesture,
  clampTooltipX,
  findNearestPointIndex,
} from "./compactSparklineInteraction.mjs";
import { buildMarketSparklineDomain } from "./marketSparklineDomain.mjs";

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const shortDate = (value) => value ? new Date(`${String(value).slice(0, 10)}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "";
const longDate = (value) => value ? new Date(`${String(value).slice(0, 10)}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "";
const numeric = (value) => value === null || value === undefined || value === "" ? null : Number.isFinite(Number(value)) ? Number(value) : null;

export default function MarketSparkline({
  points,
  valueKey = "value",
  trendDirection = "neutral",
  className = "",
  plotClassName = "h-12 desk:h-16",
  label = "Market-price trend",
  emptyLabel = "Awaiting trend",
  showDates = true,
  baselineValue = null,
}) {
  const [activeIndex, setActiveIndex] = useState(null);
  const [tooltipX, setTooltipX] = useState(null);
  // Viewport-space anchor for the portalled tooltip. The plot lives inside
  // scrolling/overflow-hidden ancestors, so the tooltip cannot be positioned
  // relative to it — see the portal note below.
  const [tooltipAnchor, setTooltipAnchor] = useState(null);
  const pointerMode = usePointerMode();
  const containerRef = useRef(null);
  const gestureRef = useRef(null);
  const chartId = useId().replace(/:/g, "");
  const chartPoints = (Array.isArray(points) ? points : []).map((point, index) => ({
    index,
    date: point?.date ?? null,
    y: numeric(point?.[valueKey] ?? point?.value),
    isCarriedForward: Boolean(point?.isCarriedForward),
    sourceDate: point?.sourceDate ?? null,
  }));
  const numericPoints = chartPoints.filter((point) => point.y !== null);
  const color = trendDirection === "negative" ? NEGATIVE_VALUE_COLOR : trendDirection === "positive" ? POSITIVE_VALUE_COLOR : "rgba(148,163,184,0.8)";
  const activePoint = activeIndex === null ? null : numericPoints[activeIndex] || null;
  // When the caller owns a selected timeframe it passes that window's baseline,
  // and every hovered point is measured against it — so the latest point's
  // tooltip is by construction the same number as the caller's summary chip.
  // Without a baseline (callers with no window concept) the historical
  // point-over-point reading is kept.
  const windowBaseline = numeric(baselineValue);
  const previousPoint = activeIndex > 0 ? numericPoints[activeIndex - 1] : null;
  const baselineChange = windowBaseline === null ? null : computeChangeFromBaseline(activePoint?.y, windowBaseline);
  const deltaAmount = baselineChange
    ? baselineChange.amount
    : activePoint && previousPoint ? activePoint.y - previousPoint.y : null;
  const deltaPercent = baselineChange
    ? baselineChange.percent
    : previousPoint?.y ? (deltaAmount / previousPoint.y) * 100 : null;
  const [domainMin, domainMax] = buildMarketSparklineDomain(numericPoints, { valueKey: "y" });
  const xRange = Math.max(chartPoints.length - 1, 1);
  const yRange = domainMax - domainMin || 1;
  const coordinates = numericPoints.map((point) => ({ ...point, x: 2 + (point.index / xRange) * 96, py: 36 - ((point.y - domainMin) / yRange) * 28 }));
  const polyline = coordinates.map(({ x, py }) => `${x.toFixed(2)},${py.toFixed(2)}`).join(" ");
  const areaPath = coordinates.length ? `M ${polyline.replaceAll(" ", " L ")} L 98 40 L 2 40 Z` : "";
  const activeCoordinate = activeIndex === null ? null : coordinates[activeIndex] || null;

  const clearSelection = () => { setActiveIndex(null); setTooltipX(null); setTooltipAnchor(null); };
  const anchorFromBounds = (bounds) => ({ left: bounds.left, top: bounds.top });
  const selectAtClientX = (clientX) => {
    const element = containerRef.current;
    if (!element || !numericPoints.length) return;
    const bounds = element.getBoundingClientRect();
    const ratio = bounds.width > 0 ? (clientX - bounds.left) / bounds.width : 0;
    setActiveIndex(findNearestPointIndex(numericPoints, chartPoints.length, ratio));
    setTooltipX(clampTooltipX({ chartLeft: bounds.left, chartWidth: bounds.width, pointerX: clientX - bounds.left, tooltipWidth: 224, viewportWidth: typeof window === "undefined" ? bounds.width : window.innerWidth, gutter: 8 }));
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

  // A portalled tooltip is positioned in viewport space, so it has to be
  // re-anchored while the page (or the rankings ladder's own scroll container)
  // moves under an open selection. Only listens while a point is selected.
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

  if (numericPoints.length < 2) return <div className={["flex items-center justify-center text-[10px] text-[var(--text-secondary)]", plotClassName, className].join(" ")}>{emptyLabel}</div>;
  const gradientId = `market-sparkline-gradient-${chartId}`;
  return (
    <div className={["min-w-0", className].filter(Boolean).join(" ")}>
      <div
        ref={containerRef}
        data-market-sparkline
        data-market-sparkline-point-count={numericPoints.length}
        data-pointer-mode={pointerMode}
        role="img"
        tabIndex={0}
        aria-label={activePoint ? `${label}. Selected ${longDate(activePoint.date)}: ${money.format(activePoint.y)}.` : `${label}. Use left and right arrow keys to inspect daily values.`}
        className={["group relative z-30 touch-pan-y overflow-visible rounded-lg", plotClassName].join(" ")}
        onPointerDown={(event) => { if (event.pointerType !== "mouse") gestureRef.current = { startX: event.clientX, startY: event.clientY, moved: false }; }}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={() => { gestureRef.current = null; }}
        onPointerLeave={(event) => { if (event.pointerType === "mouse" || pointerMode !== POINTER_MODE_COARSE) clearSelection(); }}
        onFocus={(event) => { const bounds = event.currentTarget.getBoundingClientRect(); setActiveIndex(numericPoints.length - 1); setTooltipX(clampTooltipX({ chartLeft: bounds.left, chartWidth: bounds.width, pointerX: bounds.width / 2, tooltipWidth: 224, viewportWidth: typeof window === "undefined" ? bounds.width : window.innerWidth })); setTooltipAnchor(anchorFromBounds(bounds)); }}
        onBlur={clearSelection}
        onKeyDown={(event) => { if (event.key === "ArrowRight" || event.key === "ArrowLeft") { event.preventDefault(); const step = event.key === "ArrowRight" ? 1 : -1; const base = activeIndex === null ? numericPoints.length - 1 : activeIndex; setActiveIndex(Math.max(0, Math.min(numericPoints.length - 1, base + step))); setTooltipAnchor(anchorFromBounds(event.currentTarget.getBoundingClientRect())); } else if (event.key === "Escape") clearSelection(); }}
      >
        <svg aria-hidden="true" viewBox="0 0 100 42" preserveAspectRatio="none" className="h-full w-full overflow-visible rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/42 max-desk:rounded-none max-desk:border-0 max-desk:bg-transparent">
          <defs><linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity="0.22"/><stop offset="100%" stopColor={color} stopOpacity="0"/></linearGradient></defs>
          <path d={areaPath} fill={`url(#${gradientId})`} />
          <polyline points={polyline} fill="none" stroke={color} strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
          {activeCoordinate ? <line data-market-sparkline-guide x1={activeCoordinate.x} x2={activeCoordinate.x} y1="4" y2="39" stroke="rgba(255,255,255,0.16)" strokeWidth="1" vectorEffect="non-scaling-stroke" /> : null}
        </svg>
        {activeCoordinate ? <span data-market-sparkline-marker aria-hidden="true" className="pointer-events-none absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border border-current bg-[rgba(2,6,23,0.82)] shadow-[0_0_8px_currentColor]" style={{ left: `${activeCoordinate.x}%`, top: `${(activeCoordinate.py / 42) * 100}%`, color }}><span className="absolute left-1/2 top-1/2 h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-current" /></span> : null}
        {/* The tooltip is portalled to <body> rather than positioned inside the
            plot. Its ancestors legitimately clip: the rankings ladder scrolls
            (overflow-y: auto) and its shell is overflow: hidden, so the #1 row's
            upward tooltip was cut off at the container edge no matter how high
            its z-index went — a clipping problem, not a stacking one. Escaping
            the clip is the fix; the card's own styling is untouched. */}
        {activePoint && tooltipX !== null && tooltipAnchor && typeof document !== "undefined"
          ? createPortal(
              <MarketTrendTooltipCard
                data-market-sparkline-tooltip
                date={activePoint.date}
                value={activePoint.y}
                deltaAmount={deltaAmount}
                deltaPercent={deltaPercent}
                isCarriedForward={activePoint.isCarriedForward}
                sourceDate={activePoint.sourceDate}
                accessibleLabel={`${label} value`}
                className="fixed z-[80]"
                style={{ left: tooltipAnchor.left + tooltipX, top: tooltipAnchor.top - 8.8, transform: "translate(-50%, -100%)" }}
              />,
              document.body
            )
          : null}
      </div>
      {showDates ? <div data-market-sparkline-dates className="mt-1 flex items-center justify-between gap-2 text-[9px] text-[var(--text-secondary)] desk:text-[10px]"><span>{shortDate(numericPoints[0].date)}</span><span className="text-right">{shortDate(numericPoints[numericPoints.length - 1].date)}</span></div> : null}
    </div>
  );
}
