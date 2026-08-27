"use client";

import { useState } from "react";
import MarketMobileChart from "@/components/pokemon/set-page/Market/MarketMobileChart";
import MarketValueChange from "@/components/ui/MarketValueChange";
import { ASSET_MARKET_WINDOWS, finite, movementTone, selectAssetMarketWindow } from "./assetMarketModel.mjs";

const money = (value) => finite(value) === null ? "Unavailable" : finite(value).toLocaleString("en-US", { style: "currency", currency: "USD" });
const dateLabel = (value) => value ? new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`)) : "Unavailable";

export default function AssetMarketPanel({ market }) {
  const [windowKey, setWindowKey] = useState("30D");
  const selected = selectAssetMarketWindow(market, windowKey);
  const tone = movementTone(selected.movement);
  return (
    <section aria-labelledby="market-price-title" className="set-glass-surface min-w-0 rounded-2xl border p-4 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p id="market-price-title" className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">Current Market Price</p>
          <p className="mt-2 text-4xl font-semibold tracking-tight tabular-nums text-[var(--text-primary)] sm:text-5xl">{money(market?.currentPrice)}</p>
          <div className="mt-2 min-h-6">
            {selected.movement?.available ? <MarketValueChange changeAmount={selected.movement.deltaAmount} changePercent={selected.movement.deltaPercent} windowLabel={ASSET_MARKET_WINDOWS.find(([key]) => key === windowKey)?.[1]} direction={tone} content="change" variant="chart-summary" accessibleLabel="Raw card market price" /> : <span className="text-sm text-[var(--text-secondary)]">Change unavailable for this period</span>}
          </div>
        </div>
        <div role="radiogroup" aria-label="Asset mode" className="inline-flex rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-1 text-xs font-semibold">
          <button role="radio" aria-checked="true" className="min-h-10 rounded-md bg-[color-mix(in_srgb,var(--accent)_18%,transparent)] px-4 text-[var(--accent)] ring-1 ring-inset ring-[color-mix(in_srgb,var(--accent)_45%,transparent)]">Raw</button>
          <button type="button" role="radio" aria-checked="false" aria-disabled="true" disabled title="Graded market data is coming soon" className="min-h-10 cursor-not-allowed rounded-md px-3 text-[var(--text-secondary)] opacity-60">Graded · Coming Soon</button>
        </div>
      </div>
      <div role="radiogroup" aria-label="Price history timeframe" className="mt-6 grid grid-cols-4 gap-1 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-1 sm:grid-cols-7">
        {ASSET_MARKET_WINDOWS.map(([key, label]) => <button key={key} type="button" role="radio" aria-checked={windowKey === key} onClick={() => setWindowKey(key)} className={`min-h-11 rounded-lg px-2 text-xs font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] ${windowKey === key ? "bg-[color-mix(in_srgb,var(--accent)_18%,transparent)] text-[var(--accent)] ring-1 ring-inset ring-[color-mix(in_srgb,var(--accent)_40%,transparent)]" : "text-[var(--text-secondary)] hover:bg-white/5 hover:text-[var(--text-primary)]"}`}>{label}</button>)}
      </div>
      {selected.partial ? <p className="mt-3 text-xs text-[var(--text-secondary)]">{ASSET_MARKET_WINDOWS.find(([key]) => key === windowKey)?.[1]} requested · Showing history since tracking began ({dateLabel(selected.movement.startDate)}–{dateLabel(selected.movement.endDate)})</p> : null}
      <div className="mt-4">
        <MarketMobileChart points={selected.history} valueKey="marketPrice" trendDirection={tone} seriesLabel="Raw card market price" heightClassName="h-[clamp(220px,34vw,360px)]" emptyMessage="Price history is not available for this card and printing yet." />
      </div>
      <div className="mt-3 flex flex-wrap justify-between gap-2 text-xs text-[var(--text-secondary)]"><span>{selected.history[0]?.date ? dateLabel(selected.history[0].date) : "First observation unavailable"}</span><span>{market?.marketDate ? `Price as of ${dateLabel(market.marketDate)}` : "Price date unavailable"}</span></div>
    </section>
  );
}
