"use client";

import InfoPopover from "@/components/ui/InfoPopover";
import { NEGATIVE_VALUE_COLOR, POSITIVE_VALUE_COLOR } from "@/lib/explore/interpretationTone";
import {
  MARKET_OVERVIEW_HELP,
  MARKET_OVERVIEW_SUMMARY_WINDOWS,
  changeDirection,
  describeChange,
  formatBasketValue,
  formatChangePercent,
  formatIndexValue,
  getMarketChange,
} from "@/lib/explore/marketOverviewPresentation.mjs";
import styles from "./explore.module.css";

// The two identity swatches and the change tones are deliberately different
// vocabularies: the swatch says WHICH market a row is, the tone says which way
// it moved. A green Raw row would conflate the two.
function toneOf(direction) {
  if (direction === "positive") return POSITIVE_VALUE_COLOR;
  if (direction === "negative") return NEGATIVE_VALUE_COLOR;
  return "var(--text-secondary)";
}

function ChangeValue({ change, marketLabel, windowLabel, className = "" }) {
  const direction = changeDirection(change);
  const glyph = direction === "positive" ? "▲" : direction === "negative" ? "▼" : direction === "neutral" ? "—" : "";
  return (
    <span className={["inline-flex items-baseline gap-1 tabular-nums", className].filter(Boolean).join(" ")} style={{ color: toneOf(direction) }}>
      {glyph ? <span aria-hidden="true" className="text-[0.75em] leading-none">{glyph}</span> : null}
      <span aria-hidden="true">{formatChangePercent(change)}</span>
      <span className="sr-only">{describeChange(marketLabel, windowLabel, change)}</span>
    </span>
  );
}

function MarketSwatch({ color }) {
  return <span aria-hidden="true" className="inline-block h-2.5 w-2.5 flex-none rounded-[3px]" style={{ backgroundColor: color }} />;
}

export default function PokemonMarketOverview({ overview }) {
  if (!overview || !overview.families?.length) {
    return (
      <section className={`${styles.surfaceQuiet} set-glass-surface`} aria-labelledby="market-overview-heading">
        <div className={`${styles.divider} px-3 py-3 sm:px-4`}>
          <h2 id="market-overview-heading" className="text-[18px] font-semibold text-[var(--text-primary)] desk:text-[15px]">Market Overview</h2>
        </div>
        <p role="status" className="px-4 py-6 text-sm text-[var(--text-secondary)]">
          Market Overview is temporarily unavailable.
        </p>
      </section>
    );
  }

  const families = overview.families;

  return (
    <section className={`${styles.surfaceQuiet} set-glass-surface`} aria-labelledby="market-overview-heading">
      <div className={`${styles.divider} flex items-center gap-2 px-3 py-3 sm:px-4`}>
        <h2 id="market-overview-heading" className="text-[18px] font-semibold text-[var(--text-primary)] desk:text-[15px]">Market Overview</h2>
      </div>

      {/* Desktop: one finance-first table so the two markets compare row-to-row. */}
      <div data-market-overview-table className="hidden desk:block">
        <table className={styles.marketOverviewTable}>
          <caption className="sr-only">Basket value, index and reported changes for each tracked Pokémon market.</caption>
          <thead>
            <tr>
              <th scope="col">Market</th>
              <th scope="col">
                <div className="flex items-center justify-end gap-1.5">Basket Value<InfoPopover text={MARKET_OVERVIEW_HELP.basketValue} /></div>
              </th>
              <th scope="col">
                <div className="flex items-center justify-end gap-1.5">Index<InfoPopover text={MARKET_OVERVIEW_HELP.index} /></div>
              </th>
              {MARKET_OVERVIEW_SUMMARY_WINDOWS.map((entry) => <th key={entry.key} scope="col">{entry.label}</th>)}
            </tr>
          </thead>
          <tbody>
            {families.map((family) => (
              <tr key={family.key} data-market-overview-row={family.key}>
                <th scope="row">
                  <span className="inline-flex items-center gap-2"><MarketSwatch color={family.color} />{family.label}</span>
                </th>
                <td data-market-overview-metric="basketValue">{formatBasketValue(family.basketValue)}</td>
                <td data-market-overview-metric="index" className={styles.marketOverviewIndex}>{formatIndexValue(family.indexValue)}</td>
                {MARKET_OVERVIEW_SUMMARY_WINDOWS.map((entry) => (
                  <td key={entry.key} data-market-overview-change={entry.key}>
                    <ChangeValue change={getMarketChange(family, entry.key)} marketLabel={family.label} windowLabel={entry.label} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile: stacked cards, never a horizontally scrolling table. */}
      <ul data-market-overview-cards className="divide-y divide-[var(--border-subtle)] desk:hidden">
        {families.map((family) => {
          const thirtyDay = getMarketChange(family, "30D");
          const sinceTracking = getMarketChange(family, "All");
          return (
            <li key={family.key} data-market-overview-card={family.key} className="px-3 py-3.5 sm:px-4">
              <p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.09em] text-[var(--text-secondary)]">
                <MarketSwatch color={family.color} />{family.label}
              </p>
              <div className="mt-2.5 grid grid-cols-2 gap-x-3 gap-y-2.5">
                <div>
                  <p data-market-overview-metric="basketValue" className="text-[19px] font-semibold leading-tight tabular-nums text-[var(--text-primary)]">{formatBasketValue(family.basketValue)}</p>
                  <div className="mt-0.5 flex items-center gap-1 text-[10px] font-medium uppercase tracking-[0.08em] text-[var(--text-secondary)]">Basket Value<InfoPopover text={MARKET_OVERVIEW_HELP.basketValue} /></div>
                </div>
                <div>
                  <p data-market-overview-metric="index" className="text-[19px] font-semibold leading-tight tabular-nums text-[var(--text-primary)]">{formatIndexValue(family.indexValue)}</p>
                  <div className="mt-0.5 flex items-center gap-1 text-[10px] font-medium uppercase tracking-[0.08em] text-[var(--text-secondary)]">Market Index<InfoPopover text={MARKET_OVERVIEW_HELP.index} /></div>
                </div>
                <div data-market-overview-change="30D">
                  <p className="text-[10px] font-medium uppercase tracking-[0.08em] text-[var(--text-secondary)]">30D</p>
                  <ChangeValue change={thirtyDay} marketLabel={family.label} windowLabel="30D" className="mt-0.5 text-sm font-semibold" />
                </div>
                <div data-market-overview-change="All">
                  <p className="text-[10px] font-medium uppercase tracking-[0.08em] text-[var(--text-secondary)]">Since Tracking</p>
                  <ChangeValue change={sinceTracking} marketLabel={family.label} windowLabel="Since Tracking" className="mt-0.5 text-sm font-semibold" />
                </div>
              </div>
              <p className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[var(--text-secondary)]">
                {["1D", "7D"].map((key) => (
                  <span key={key} data-market-overview-change={key} className="inline-flex items-center gap-1">
                    <span className="font-medium uppercase tracking-[0.08em]">{key}</span>
                    <ChangeValue change={getMarketChange(family, key)} marketLabel={family.label} windowLabel={key} className="font-semibold" />
                  </span>
                ))}
              </p>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
