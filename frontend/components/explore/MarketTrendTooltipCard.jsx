"use client";

import MarketValueChange from "@/components/ui/MarketValueChange";

const formatLongDate = (value) => value
  ? new Date(`${String(value).slice(0, 10)}T00:00:00`).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    })
  : "";

const formatShortDate = (value) => value
  ? new Date(`${String(value).slice(0, 10)}T00:00:00`).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    })
  : "";

const numberOrNull = (value) => {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

export default function MarketTrendTooltipCard({
  date,
  value,
  deltaAmount,
  deltaPercent,
  isCarriedForward = false,
  sourceDate = null,
  className = "",
  style,
  accessibleLabel = "Market value at selected date",
  ...props
}) {
  return (
    <div
      {...props}
      className={[
        "pointer-events-none z-50 min-w-[9rem] max-w-[min(14rem,calc(100vw-1rem))] rounded-lg border border-[var(--border-subtle)] bg-[rgba(2,6,23,0.96)] px-2.5 py-2 text-left shadow-[0_14px_32px_rgba(0,0,0,0.38)]",
        className,
      ].filter(Boolean).join(" ")}
      style={style}
    >
      <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{formatLongDate(date)}</p>
      <MarketValueChange
        className="mt-1"
        value={value}
        changeAmount={numberOrNull(deltaAmount)}
        changePercent={numberOrNull(deltaPercent)}
        variant="tooltip"
        accessibleLabel={accessibleLabel}
      />
      {isCarriedForward && sourceDate ? (
        <p className="mt-0.5 text-[10px] text-[var(--text-secondary)]">Carried forward from {formatShortDate(sourceDate)}</p>
      ) : null}
    </div>
  );
}
