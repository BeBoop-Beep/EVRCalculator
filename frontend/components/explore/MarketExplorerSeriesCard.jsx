"use client";

import {
  MARKET_DIMENSION_LABELS,
  changeDirection,
  describeChange,
  formatBasketValue,
  formatChangePercent,
  formatIndexValue,
  getPricePerformanceChange,
} from "@/lib/explore/marketOverviewPresentation.mjs";
import { NEGATIVE_VALUE_COLOR, POSITIVE_VALUE_COLOR } from "@/lib/explore/interpretationTone";

// One selectable parent market.
//
// The card reports the two published dimensions side by side — Tracked Value
// (dollars in the basket) and Market Index (chain-linked price performance) —
// plus the return over the SELECTED window. All three are read from the
// snapshot; the card performs no arithmetic on a market number.
//
// Selection is identity, not performance: the swatch and the selected ring use
// the market's own color. Green/red is reserved for which way it moved.
function toneOf(direction) {
  if (direction === "positive") return POSITIVE_VALUE_COLOR;
  if (direction === "negative") return NEGATIVE_VALUE_COLOR;
  return "var(--text-secondary)";
}

export default function MarketExplorerSeriesCard({ entry, timeframe, timeframeLabel = "" }) {
  const { key, label, color, family, available } = entry;

  if (!available) {
    return (
      <div
        data-market-explorer-card={key}
        data-market-explorer-card-available="false"
        className="flex min-w-0 flex-col justify-between rounded-lg border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)]/25 px-3 py-2.5 opacity-70"
      >
        <span className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
          <span aria-hidden="true" className="inline-block h-2.5 w-2.5 flex-none rounded-[3px] opacity-40" style={{ backgroundColor: color }} />
          {label}
        </span>
        <p role="status" className="mt-2 text-xs text-[var(--text-secondary)]">
          Coming soon
        </p>
      </div>
    );
  }

  const change = getPricePerformanceChange(family, timeframe);
  const direction = changeDirection(change);
  return (
    <div
      data-market-explorer-card={key}
      data-market-explorer-card-available="true"
      className="flex min-w-0 flex-col rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 px-3 py-2.5 text-left"
    >
      <span className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
        <span aria-hidden="true" className="inline-block h-2.5 w-2.5 flex-none rounded-[3px]" style={{ backgroundColor: color }} />
        <span className="truncate text-[var(--text-primary)]">{label}</span>
      </span>

      <div className="mt-2 grid grid-cols-2 gap-x-3">
        <div>
          <div className="text-[9px] font-medium uppercase tracking-[0.07em] text-[var(--text-secondary)]">Tracked Value</div>
          <p data-market-explorer-card-metric="trackedValue" className="text-[15px] font-semibold leading-tight tabular-nums text-[var(--text-primary)]">
            {formatBasketValue(family.basketValue)}
          </p>
        </div>
        <div>
          <div className="text-[9px] font-medium uppercase tracking-[0.07em] text-[var(--text-secondary)]">Market Index</div>
          <p data-market-explorer-card-metric="index" className="text-[15px] font-semibold leading-tight tabular-nums text-[var(--text-primary)]">
            {formatIndexValue(family.indexValue)}
          </p>
        </div>
      </div>

      <p data-market-explorer-card-change={timeframe} className="mt-1.5 text-[10px] text-[var(--text-secondary)]">
        <span className="font-semibold tabular-nums" style={{ color: toneOf(direction) }}>
          <span aria-hidden="true">{formatChangePercent(change)}</span>
          <span className="sr-only">{describeChange(label, timeframeLabel, change, { dimension: MARKET_DIMENSION_LABELS.pricePerformance })}</span>
        </span>
        <span aria-hidden="true"> {timeframeLabel}</span>
      </p>
    </div>
  );
}
