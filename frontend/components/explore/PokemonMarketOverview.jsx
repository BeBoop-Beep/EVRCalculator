"use client";

import InfoPopover from "@/components/ui/InfoPopover";
import { NEGATIVE_VALUE_COLOR, POSITIVE_VALUE_COLOR } from "@/lib/explore/interpretationTone";
import {
  MARKET_DIMENSION_LABELS,
  MARKET_OVERVIEW_GROUPS,
  MARKET_OVERVIEW_HELP,
  MARKET_OVERVIEW_SUMMARY_WINDOWS,
  changeDirection,
  describeChange,
  formatBasketValue,
  formatChangePercent,
  formatIndexValue,
  getPricePerformanceChange,
  getTrackedValueChange,
} from "@/lib/explore/marketOverviewPresentation.mjs";
import styles from "./explore.module.css";

// TWO dimensions, grouped so a reader never has to guess which question a
// column answers:
//
//   Tracked Market Value — how many dollars the tracked universe holds today,
//                          and how that total moved (cohort changes INCLUDED).
//   Price Performance    — the chain-linked base-100 index and its movement,
//                          with cohort entry/exit neutralized.
//
// Both come straight from the published payload — `basketChanges` and
// `changes` respectively. Nothing here divides one basket value by another.
const PRICE_PERFORMANCE_WINDOWS = MARKET_OVERVIEW_SUMMARY_WINDOWS;
const SINCE_TRACKING = "All";
const SINCE_TRACKING_LABEL = "Since Tracking";

// The identity swatches and the change tones are deliberately different
// vocabularies: the swatch says WHICH market a row is, the tone says which way
// it moved. A green Raw row would conflate the two.
function toneOf(direction) {
  if (direction === "positive") return POSITIVE_VALUE_COLOR;
  if (direction === "negative") return NEGATIVE_VALUE_COLOR;
  return "var(--text-secondary)";
}

function ChangeValue({ change, marketLabel, windowLabel, dimension, className = "" }) {
  const direction = changeDirection(change);
  const glyph = direction === "positive" ? "▲" : direction === "negative" ? "▼" : direction === "neutral" ? "—" : "";
  return (
    <span className={["inline-flex items-baseline gap-1 tabular-nums", className].filter(Boolean).join(" ")} style={{ color: toneOf(direction) }}>
      {glyph ? <span aria-hidden="true" className="text-[0.75em] leading-none">{glyph}</span> : null}
      <span aria-hidden="true">{formatChangePercent(change)}</span>
      <span className="sr-only">{describeChange(marketLabel, windowLabel, change, { dimension })}</span>
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

      {/* Desktop: one finance-first table with two real column groups. */}
      <div data-market-overview-table className="hidden desk:block">
        <table className={styles.marketOverviewTable}>
          <caption className="sr-only">
            Tracked Market Value and chain-linked Price Performance for each tracked Pokémon market. Tracked Value includes sets entering or leaving the tracked universe; Price Performance neutralizes them.
          </caption>
          <thead>
            <tr className={styles.marketOverviewGroupRow}>
              <td aria-hidden="true" />
              <th scope="colgroup" colSpan={2} data-market-overview-group="trackedValue" className={styles.marketOverviewGroupHead}>
                {MARKET_OVERVIEW_GROUPS.trackedValue}
              </th>
              <th scope="colgroup" colSpan={1 + PRICE_PERFORMANCE_WINDOWS.length} data-market-overview-group="pricePerformance" className={styles.marketOverviewGroupHead}>
                {MARKET_OVERVIEW_GROUPS.pricePerformance}
              </th>
            </tr>
            <tr>
              <th scope="col">Market</th>
              <th scope="col" className={styles.marketOverviewGroupStart}>
                <div className="flex items-center justify-end gap-1.5">Tracked Value<InfoPopover text={MARKET_OVERVIEW_HELP.trackedValue} /></div>
              </th>
              <th scope="col">
                <div className="flex items-center justify-end gap-1.5">{SINCE_TRACKING_LABEL}<InfoPopover text={MARKET_OVERVIEW_HELP.trackedValueChange} /></div>
              </th>
              <th scope="col" className={styles.marketOverviewGroupStart}>
                <div className="flex items-center justify-end gap-1.5">Market Index<InfoPopover text={MARKET_OVERVIEW_HELP.index} /></div>
              </th>
              {PRICE_PERFORMANCE_WINDOWS.map((entry) => <th key={entry.key} scope="col">{entry.label}</th>)}
            </tr>
          </thead>
          <tbody>
            {families.map((family) => (
              <tr key={family.key} data-market-overview-row={family.key}>
                <th scope="row">
                  <span className="inline-flex items-center gap-2"><MarketSwatch color={family.color} />{family.label}</span>
                </th>
                <td data-market-overview-metric="trackedValue" className={styles.marketOverviewGroupStart}>{formatBasketValue(family.basketValue)}</td>
                <td data-market-overview-tracked-change={SINCE_TRACKING}>
                  <ChangeValue
                    change={getTrackedValueChange(family, SINCE_TRACKING)}
                    marketLabel={family.label}
                    windowLabel={SINCE_TRACKING_LABEL}
                    dimension={MARKET_DIMENSION_LABELS.trackedValue}
                  />
                </td>
                <td data-market-overview-metric="index" className={`${styles.marketOverviewIndex} ${styles.marketOverviewGroupStart}`}>{formatIndexValue(family.indexValue)}</td>
                {PRICE_PERFORMANCE_WINDOWS.map((entry) => (
                  <td key={entry.key} data-market-overview-change={entry.key}>
                    <ChangeValue
                      change={getPricePerformanceChange(family, entry.key)}
                      marketLabel={family.label}
                      windowLabel={entry.label}
                      dimension={MARKET_DIMENSION_LABELS.pricePerformance}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile: stacked cards, never a horizontally scrolling table. Each card
          tells both stories, in the order the desktop groups do. */}
      <ul data-market-overview-cards className="divide-y divide-[var(--border-subtle)] desk:hidden">
        {families.map((family) => (
          <li key={family.key} data-market-overview-card={family.key} className="px-3 py-3.5 sm:px-4">
            <p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.09em] text-[var(--text-secondary)]">
              <MarketSwatch color={family.color} />{family.label}
            </p>

            <div className="mt-2.5 grid grid-cols-2 gap-x-3 gap-y-3">
              <div data-market-overview-group="trackedValue">
                <div className="flex items-center gap-1 text-[10px] font-medium uppercase tracking-[0.08em] text-[var(--text-secondary)]">
                  Tracked Value<InfoPopover text={MARKET_OVERVIEW_HELP.trackedValue} />
                </div>
                <p data-market-overview-metric="trackedValue" className="mt-0.5 text-[19px] font-semibold leading-tight tabular-nums text-[var(--text-primary)]">{formatBasketValue(family.basketValue)}</p>
                <p data-market-overview-tracked-change={SINCE_TRACKING} className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
                  <ChangeValue
                    change={getTrackedValueChange(family, SINCE_TRACKING)}
                    marketLabel={family.label}
                    windowLabel={SINCE_TRACKING_LABEL}
                    dimension={MARKET_DIMENSION_LABELS.trackedValue}
                    className="font-semibold"
                  />
                  <span aria-hidden="true"> since tracking</span>
                </p>
              </div>

              <div data-market-overview-group="pricePerformance">
                <div className="flex items-center gap-1 text-[10px] font-medium uppercase tracking-[0.08em] text-[var(--text-secondary)]">
                  Market Index<InfoPopover text={MARKET_OVERVIEW_HELP.index} />
                </div>
                <p data-market-overview-metric="index" className="mt-0.5 text-[19px] font-semibold leading-tight tabular-nums text-[var(--text-primary)]">{formatIndexValue(family.indexValue)}</p>
                <p data-market-overview-change={SINCE_TRACKING} className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
                  <ChangeValue
                    change={getPricePerformanceChange(family, SINCE_TRACKING)}
                    marketLabel={family.label}
                    windowLabel={SINCE_TRACKING_LABEL}
                    dimension={MARKET_DIMENSION_LABELS.pricePerformance}
                    className="font-semibold"
                  />
                  <span aria-hidden="true"> price performance</span>
                </p>
              </div>
            </div>

            <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[var(--text-secondary)]">
              <span aria-hidden="true" className="font-medium uppercase tracking-[0.08em]">Price performance</span>
              {["1D", "7D", "30D"].map((key) => (
                <span key={key} data-market-overview-change={key} className="inline-flex items-center gap-1">
                  <span aria-hidden="true" className="font-medium uppercase tracking-[0.08em]">{key}</span>
                  <ChangeValue
                    change={getPricePerformanceChange(family, key)}
                    marketLabel={family.label}
                    windowLabel={key}
                    dimension={MARKET_DIMENSION_LABELS.pricePerformance}
                    className="font-semibold"
                  />
                </span>
              ))}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
