"use client";

import MarketValueChange from "@/components/ui/MarketValueChange";
import ChartTooltipShell from "@/components/explore/ChartTooltipShell";

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
    <ChartTooltipShell
      {...props}
      className={["max-w-[min(14rem,calc(100vw-1rem))]", className].filter(Boolean).join(" ")}
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
    </ChartTooltipShell>
  );
}
