"use client";

import { useState } from "react";
import MarketPriceHistoryChart from "@/components/explore/MarketPriceHistoryChart";
import MarketWindowSelector from "@/components/explore/MarketWindowSelector";
import MarketValueChange from "@/components/ui/MarketValueChange";
import { PRODUCT_MARKET_WINDOWS, finite, selectProductMarketWindow } from "./productDetailModel.mjs";

const dateLabel = (value) => value ? new Intl.DateTimeFormat("en-US", {
  month: "short", day: "numeric", year: "numeric", timeZone: "UTC",
}).format(new Date(`${String(value).slice(0, 10)}T00:00:00Z`)) : "Unavailable";

export default function SealedProductMarketPanel({ market, productName }) {
  const [windowKey, setWindowKey] = useState("30D");
  const selected = selectProductMarketWindow(market, windowKey);
  const amount = finite(selected.movement.deltaAmount);
  const direction = amount === null || Math.abs(amount) < 0.005 ? "neutral" : amount > 0 ? "positive" : "negative";
  const label = PRODUCT_MARKET_WINDOWS.find((window) => window.key === windowKey)?.label;
  return (
    <section data-product-market-panel aria-labelledby="product-market-title" className="set-glass-surface h-full min-w-0 rounded-2xl border p-4 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p id="product-market-title" className="text-xs font-semibold uppercase tracking-[.12em] text-[var(--text-secondary)]">Current Market Price</p>
          <MarketValueChange className="mt-2" value={market?.currentPrice} changeAmount={selected.movement.deltaAmount} changePercent={selected.movement.deltaPercent} unavailable={!selected.movement.available} windowLabel={label} direction={direction} variant="chart-summary" accessibleLabel={`${productName} sealed market price`} />
        </div>
        <MarketWindowSelector windows={PRODUCT_MARKET_WINDOWS} value={windowKey} onChange={setWindowKey} />
      </div>
      <div data-market-coverage-status data-partial={selected.partial ? "true" : "false"} aria-live="polite" className="mt-3 flex h-12 items-start text-xs leading-5 text-[var(--text-secondary)] sm:h-10">
        {selected.partial ? <p>{label} requested · Showing history since tracking began ({dateLabel(selected.movement.actualStartDate)}–{dateLabel(selected.movement.endDate)})</p> : <span aria-hidden="true">&nbsp;</span>}
      </div>
      <MarketPriceHistoryChart points={selected.history} valueKey="marketPrice" trendDirection={direction} seriesLabel={`${productName} sealed market price`} heightClassName="h-[clamp(300px,34vw,420px)]" emptyMessage="Price history is not available for this product yet." />
      <div className="mt-3 flex flex-wrap justify-between gap-2 text-xs text-[var(--text-secondary)]">
        <span>{selected.history[0]?.date ? dateLabel(selected.history[0].date) : "First observation unavailable"}</span>
        <span>{market?.marketDate ? `Price as of ${dateLabel(market.marketDate)}` : "Price date unavailable"}</span>
      </div>
    </section>
  );
}
