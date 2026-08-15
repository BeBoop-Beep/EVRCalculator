"use client";

import { useId, useRef, useState } from "react";
import usePointerMode, { POINTER_MODE_COARSE } from "@/hooks/usePointerMode";
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
}) {
  const [activeIndex, setActiveIndex] = useState(null);
  const [tooltipX, setTooltipX] = useState(null);
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
  const previousPoint = activeIndex > 0 ? numericPoints[activeIndex - 1] : null;
  const deltaAmount = activePoint && previousPoint ? activePoint.y - previousPoint.y : null;
  const deltaPercent = previousPoint?.y ? (deltaAmount / previousPoint.y) * 100 : null;
  const [domainMin, domainMax] = buildMarketSparklineDomain(numericPoints, { valueKey: "y" });
  const xRange = Math.max(chartPoints.length - 1, 1);
  const yRange = domainMax - domainMin || 1;
  const coordinates = numericPoints.map((point) => ({ ...point, x: 2 + (point.index / xRange) * 96, py: 36 - ((point.y - domainMin) / yRange) * 28 }));
  const polyline = coordinates.map(({ x, py }) => `${x.toFixed(2)},${py.toFixed(2)}`).join(" ");
  const areaPath = coordinates.length ? `M ${polyline.replaceAll(" ", " L ")} L 98 40 L 2 40 Z` : "";
  const activeCoordinate = activeIndex === null ? null : coordinates[activeIndex] || null;

  const clearSelection = () => { setActiveIndex(null); setTooltipX(null); };
  const selectAtClientX = (clientX) => {
    const element = containerRef.current;
    if (!element || !numericPoints.length) return;
    const bounds = element.getBoundingClientRect();
    const ratio = bounds.width > 0 ? (clientX - bounds.left) / bounds.width : 0;
    setActiveIndex(findNearestPointIndex(numericPoints, chartPoints.length, ratio));
    setTooltipX(clampTooltipX({ chartLeft: bounds.left, chartWidth: bounds.width, pointerX: clientX - bounds.left, tooltipWidth: 224, viewportWidth: typeof window === "undefined" ? bounds.width : window.innerWidth, gutter: 8 }));
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

  if (numericPoints.length < 2) return <div className={["flex items-center justify-center text-[10px] text-[var(--text-secondary)]", plotClassName, className].join(" ")}>{emptyLabel}</div>;
  const gradientId = `market-sparkline-gradient-${chartId}`;
  return (
    <div className={["min-w-0", className].filter(Boolean).join(" ")}>
      <div
        ref={containerRef}
        data-market-sparkline
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
        onFocus={(event) => { const bounds = event.currentTarget.getBoundingClientRect(); setActiveIndex(numericPoints.length - 1); setTooltipX(clampTooltipX({ chartLeft: bounds.left, chartWidth: bounds.width, pointerX: bounds.width / 2, tooltipWidth: 224, viewportWidth: typeof window === "undefined" ? bounds.width : window.innerWidth })); }}
        onBlur={clearSelection}
        onKeyDown={(event) => { if (event.key === "ArrowRight" || event.key === "ArrowLeft") { event.preventDefault(); const step = event.key === "ArrowRight" ? 1 : -1; const base = activeIndex === null ? numericPoints.length - 1 : activeIndex; setActiveIndex(Math.max(0, Math.min(numericPoints.length - 1, base + step))); } else if (event.key === "Escape") clearSelection(); }}
      >
        <svg aria-hidden="true" viewBox="0 0 100 42" preserveAspectRatio="none" className="h-full w-full overflow-visible rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/42 max-desk:rounded-none max-desk:border-0 max-desk:bg-transparent">
          <defs><linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity="0.22"/><stop offset="100%" stopColor={color} stopOpacity="0"/></linearGradient></defs>
          <path d={areaPath} fill={`url(#${gradientId})`} />
          <polyline points={polyline} fill="none" stroke={color} strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
          {activeCoordinate ? <line data-market-sparkline-guide x1={activeCoordinate.x} x2={activeCoordinate.x} y1="4" y2="39" stroke="rgba(255,255,255,0.16)" strokeWidth="1" vectorEffect="non-scaling-stroke" /> : null}
        </svg>
        {activeCoordinate ? <span data-market-sparkline-marker aria-hidden="true" className="pointer-events-none absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border border-current bg-[rgba(2,6,23,0.82)] shadow-[0_0_8px_currentColor]" style={{ left: `${activeCoordinate.x}%`, top: `${(activeCoordinate.py / 42) * 100}%`, color }}><span className="absolute left-1/2 top-1/2 h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-current" /></span> : null}
        {activePoint && tooltipX !== null ? <MarketTrendTooltipCard data-market-sparkline-tooltip date={activePoint.date} value={activePoint.y} deltaAmount={deltaAmount} deltaPercent={deltaPercent} isCarriedForward={activePoint.isCarriedForward} sourceDate={activePoint.sourceDate} accessibleLabel={`${label} value`} className="absolute bottom-[calc(100%+0.55rem)] z-[9999] -translate-x-1/2" style={{ left: tooltipX }} /> : null}
      </div>
      {showDates ? <div data-market-sparkline-dates className="mt-1 flex items-center justify-between gap-2 text-[9px] text-[var(--text-secondary)] desk:text-[10px]"><span>{shortDate(numericPoints[0].date)}</span><span className="text-right">{shortDate(numericPoints[numericPoints.length - 1].date)}</span></div> : null}
    </div>
  );
}
