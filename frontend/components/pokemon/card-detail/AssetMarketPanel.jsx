"use client";

import { useState } from "react";
import MarketPriceHistoryChart from "@/components/explore/MarketPriceHistoryChart";
import MarketValueChange from "@/components/ui/MarketValueChange";
import MarketWindowSelector from "@/components/explore/MarketWindowSelector";
import {
  ASSET_MARKET_WINDOWS,
  movementTone,
  selectAssetMarketWindow,
} from "./assetMarketModel.mjs";

const dateLabel = (value) =>
  value
    ? new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        timeZone: "UTC",
      }).format(new Date(`${value}T00:00:00Z`))
    : "Unavailable";

export default function AssetMarketPanel({ market }) {
  const [windowKey, setWindowKey] = useState("30D");
  const selected = selectAssetMarketWindow(market, windowKey);
  const tone = movementTone(selected.movement);
  return (
    <section
      data-asset-market-panel
      aria-labelledby="market-price-title"
      className="set-glass-surface h-full min-w-0 rounded-2xl border p-4 sm:p-6"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p
            id="market-price-title"
            className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]"
          >
            Current Market Price
          </p>
          <MarketValueChange
            className="mt-2"
            value={market?.currentPrice}
            changeAmount={selected.movement?.deltaAmount}
            changePercent={selected.movement?.deltaPercent}
            unavailable={!selected.movement?.available}
            windowLabel={ASSET_MARKET_WINDOWS.find(([key]) => key === windowKey)?.[1]}
            direction={tone}
            variant="chart-summary"
            accessibleLabel="Raw card market price"
          />
        </div>
        <div className="flex flex-col items-end gap-2">
          <div
            role="radiogroup"
            aria-label="Asset mode"
            className="inline-flex rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-1 text-xs font-semibold"
          >
            <button
              role="radio"
              aria-checked="true"
              className="min-h-10 rounded-md bg-[color-mix(in_srgb,var(--accent)_18%,transparent)] px-4 text-[var(--accent)] ring-1 ring-inset ring-[color-mix(in_srgb,var(--accent)_45%,transparent)]"
            >
              Raw
            </button>
            <button
              type="button"
              role="radio"
              aria-checked="false"
              aria-disabled="true"
              disabled
              title="Graded market data is coming soon"
              className="min-h-10 cursor-not-allowed rounded-md px-3 text-[var(--text-secondary)] opacity-60"
            >
              Graded · Coming Soon
            </button>
          </div>
          <MarketWindowSelector
            windows={ASSET_MARKET_WINDOWS.map(([key, label]) => ({
              key,
              label,
            }))}
            value={windowKey}
            onChange={setWindowKey}
          />
        </div>
      </div>
      <div
        data-market-coverage-status
        data-partial={selected.partial ? "true" : "false"}
        aria-live="polite"
        className="mt-3 flex h-12 items-start text-xs leading-5 text-[var(--text-secondary)] sm:h-10"
      >
      {selected.partial ? (
        <p>
          {ASSET_MARKET_WINDOWS.find(([key]) => key === windowKey)?.[1]}{" "}
          requested · Showing history since tracking began (
          {dateLabel(selected.movement.startDate)}–
          {dateLabel(selected.movement.endDate)})
        </p>
      ) : <span aria-hidden="true">&nbsp;</span>}
      </div>
      <div>
        <MarketPriceHistoryChart
          points={selected.history}
          valueKey="marketPrice"
          trendDirection={tone}
          seriesLabel="Raw card market price"
          heightClassName="h-[clamp(300px,34vw,420px)]"
          emptyMessage="Price history is not available for this card and printing yet."
        />
      </div>
      <div className="mt-3 flex flex-wrap justify-between gap-2 text-xs text-[var(--text-secondary)]">
        <span>
          {selected.history[0]?.date
            ? dateLabel(selected.history[0].date)
            : "First observation unavailable"}
        </span>
        <span>
          {market?.marketDate
            ? `Price as of ${dateLabel(market.marketDate)}`
            : "Price date unavailable"}
        </span>
      </div>
    </section>
  );
}
