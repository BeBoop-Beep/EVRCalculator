"use client";

import DeltaTrendIcon from "@/components/ui/DeltaTrendIcon";
import { NEGATIVE_VALUE_COLOR, POSITIVE_VALUE_COLOR } from "@/lib/explore/interpretationTone";
import { buildMarketValueChangeModel } from "./marketValueChangeModel.mjs";

const VARIANT_CLASSES = {
  hero: { value: "text-xl font-bold sm:text-2xl", change: "text-xs sm:text-sm", gap: "mt-1" },
  "chart-summary": { value: "text-2xl font-semibold leading-none", change: "text-xs sm:text-sm", gap: "mt-1.5" },
  "table-row": { value: "text-sm font-semibold", change: "text-[11px]", gap: "mt-0.5" },
  "card-tile": { value: "text-xs font-semibold", change: "text-[10px]", gap: "mt-0.5" },
  ticker: { value: "text-xs font-semibold", change: "text-[10px]", gap: "mt-px" },
  tooltip: { value: "text-sm font-semibold", change: "text-[11px]", gap: "mt-0.5" },
};

export default function MarketValueChange({
  value,
  changeAmount,
  changePercent,
  windowLabel,
  direction = null,
  unavailable = false,
  loading = false,
  alignment = "left",
  variant = "table-row",
  accessibleLabel = "Market value",
  className = "",
}) {
  const classes = VARIANT_CLASSES[variant] || VARIANT_CLASSES["table-row"];
  const model = buildMarketValueChangeModel({
    value,
    changeAmount,
    changePercent,
    windowLabel,
    direction,
    unavailable,
    accessibleLabel,
  });
  const aligned = alignment === "right" ? "items-end text-right" : alignment === "center" ? "items-center text-center" : "items-start text-left";
  const toneStyle =
    model.direction === "positive"
      ? { color: POSITIVE_VALUE_COLOR }
      : model.direction === "negative"
      ? { color: NEGATIVE_VALUE_COLOR }
      : { color: "var(--text-secondary)" };

  if (loading) {
    return (
      <div className={["flex animate-pulse flex-col gap-1", aligned, className].filter(Boolean).join(" ")} aria-label={`Loading ${accessibleLabel}`}>
        <span className="h-4 w-16 rounded bg-[rgba(148,163,184,0.12)]" />
        <span className="h-3 w-28 rounded bg-[rgba(148,163,184,0.09)]" />
      </div>
    );
  }

  return (
    <div
      className={["flex min-w-0 flex-col tabular-nums", aligned, className].filter(Boolean).join(" ")}
      aria-label={model.accessibleText}
    >
      <span className={["max-w-full whitespace-nowrap text-[var(--text-primary)]", classes.value].join(" ")}>{model.valueText}</span>
      {model.hasReliableChange ? (
        <span className={["inline-flex max-w-full flex-wrap items-center gap-x-1 whitespace-nowrap font-semibold", classes.gap, classes.change].join(" ")} style={toneStyle}>
          {model.direction === "neutral" ? (
            <span aria-hidden="true">\u2014</span>
          ) : (
            <DeltaTrendIcon
              direction={model.direction === "positive" ? "up" : "down"}
              size={variant === "hero" || variant === "chart-summary" ? "md" : "sm"}
              title={model.directionText}
            />
          )}
          <span aria-hidden="true">{model.amountText} ({model.percentText})</span>
          {model.windowLabel ? <span aria-hidden="true" className="whitespace-nowrap">\u00b7 {model.windowLabel}</span> : null}
          {model.direction === "neutral" ? <span className="sr-only">No change</span> : null}
        </span>
      ) : (
        <span className={["font-medium text-[var(--text-secondary)]", classes.gap, classes.change].join(" ")}>{model.changeText}</span>
      )}
    </div>
  );
}
