"use client";

import Link from "next/link";
import InfoPopover from "@/components/ui/InfoPopover";
import { NEGATIVE_VALUE_COLOR, POSITIVE_VALUE_COLOR } from "@/lib/explore/interpretationTone";
import {
  MARKET_DIMENSION_LABELS,
  MARKET_OVERVIEW_GROUPS,
  MARKET_OVERVIEW_HELP,
  MARKET_PAGE_PLACEHOLDER_FAMILIES,
  changeDirection,
  describeChange,
  formatBasketValue,
  formatChangePercent,
  formatIndexValue,
  getFamilySinceTrackingChange,
  getPricePerformanceChange,
} from "@/lib/explore/marketOverviewPresentation.mjs";
import styles from "./explore.module.css";

// TWO dimensions, grouped so a reader never has to guess which question a
// column answers:
//
//   Tracked Market Value — how many dollars the tracked universe holds today,
//                          and how that total moved SINCE TRACKING BEGAN
//                          (cohort changes INCLUDED). This column is fixed.
//   Price Performance    — the chain-linked base-100 index, plus its movement
//                          over the CURRENTLY SELECTED window. That column is
//                          dynamic and follows the chart beside it.
//
// The two are never collapsed into one.
//
// THE "SINCE TRACKING" COLUMN IS FAMILY-SPECIFIC. It reads `familyChanges` —
// this market's movement from ITS OWN tracking start — via
// getFamilySinceTrackingChange. It must NEVER read the shared-comparison
// `changes`: that series' longest window is the common comparable start shared
// by the compared markets, which usually begins later, and reporting it under
// this label is what made a Sealed index of 106.18 sit beside a
// "Since Tracking" of +4.06% and look self-contradictory.
//
// The dynamic period column beside it DOES read the shared series, because it
// follows the chart's timeframe and the chart is a cross-market comparison.
//
// Both come straight from the published payload — `basketChanges` and
// `changes` respectively. Nothing here divides one basket value by another.
//
// FIVE columns, deliberately. An earlier revision printed 1D, 7D, 30D and
// Since Tracking simultaneously; inside ~42% of the page that table overflowed
// its pane and painted over the chart. Showing one window at a time — the one
// the reader selected — is both compact and unambiguous, and leaves room for
// the Graded and Sealed rows to arrive without another layout pass.
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

// Drill-down into Market Explorer.
//
// THE HEADER ACTION IS NOW A REAL BUTTON, not quiet text. Market Explorer is a
// substantial research tool and the only route into it was an 11px secondary
// link that read as a caption — most people never found it. It is filled in the
// inDex interaction green, the same green as a focused search field and a
// selected control, so it is unmistakably the primary action here.
//
// IT IS NOT A MARKETING HERO. Normal control height, normal type scale, sitting
// in the header control area beside the section title rather than as a banner
// above or a footer below the table.
//
// YELLOW IS NOT USED. Yellow is this product's scarce attention color; making
// it the generic primary-action color would spend it.
//
// The per-row links survive as SECONDARY navigation and now share the green
// family, so they read as the same affordance at a lower level rather than as
// incidental white text.
export const MARKET_EXPLORER_HREF = "/Market/Explorer";

const EXPLORER_CTA_CLASS = [
  "ml-auto inline-flex min-h-9 flex-none items-center gap-1.5 whitespace-nowrap rounded-md",
  "border border-[rgb(45,212,191)] bg-[rgba(45,212,191,0.16)] px-2.5 text-[11px] font-semibold",
  "text-[rgb(45,212,191)] transition-colors hover:bg-[rgba(45,212,191,0.26)]",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)]",
  "desk:min-h-8",
].join(" ");

const EXPLORER_ROW_LINK_CLASS = [
  "text-[11px] font-semibold text-[rgba(45,212,191,0.9)] transition-colors",
  "hover:text-[rgb(45,212,191)] focus-visible:outline-none focus-visible:ring-2",
  "focus-visible:ring-[rgba(45,212,191,0.65)]",
].join(" ");

export function marketExplorerHref(marketKey) {
  return marketKey ? `${MARKET_EXPLORER_HREF}?market=${encodeURIComponent(marketKey)}` : MARKET_EXPLORER_HREF;
}

export default function PokemonMarketOverview({ overview, selectedWindow, selectedLabel, visibleMarketKeys, onToggleMarket, isSinceFirstAvailable = false }) {
  if (!overview || !overview.families?.length) {
    return (
      <section data-market-overview-pane className="flex min-w-0 flex-col" aria-labelledby="market-overview-heading">
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
  // The period heading is the selector's own label, so this column can never
  // claim a timeframe the chart is not drawing.
  const periodLabel = selectedLabel || selectedWindow || "";

  return (
    <section data-market-overview-pane className="flex min-w-0 flex-col" aria-labelledby="market-overview-heading">
      <div className={`${styles.divider} flex items-center gap-2 px-3 py-3 sm:px-4`}>
        <h2 id="market-overview-heading" className="text-[18px] font-semibold text-[var(--text-primary)] desk:text-[15px]">Market Overview</h2>
        <Link
          href={MARKET_EXPLORER_HREF}
          data-market-explore-link="all"
          data-market-explorer-cta
          className={EXPLORER_CTA_CLASS}
        >
          Open Market Explorer <span aria-hidden="true">&rarr;</span>
        </Link>
      </div>

      {/* Desktop: one compact finance-first table with two real column groups. */}
      <div data-market-overview-table className="hidden desk:block">
        <table className={styles.marketOverviewTable}>
          <caption className="sr-only">
            Tracked Market Value and chain-linked Price Performance for each tracked Pokémon market, with price performance shown over the selected {periodLabel} window. Tracked Value includes sets entering or leaving the tracked universe; Price Performance neutralizes them.
          </caption>
          <thead>
            <tr className={styles.marketOverviewGroupRow}>
              <td aria-hidden="true" />
              <th scope="colgroup" colSpan={2} data-market-overview-group="trackedValue" className={styles.marketOverviewGroupHead}>
                {MARKET_OVERVIEW_GROUPS.trackedValue}
              </th>
              <th scope="colgroup" colSpan={2} data-market-overview-group="pricePerformance" className={styles.marketOverviewGroupHead}>
                {MARKET_OVERVIEW_GROUPS.pricePerformance}
              </th>
            </tr>
            <tr>
              <th scope="col">Market</th>
              <th scope="col" className={styles.marketOverviewGroupStart}>
                <div className="flex flex-wrap items-center justify-end gap-x-1.5">Tracked Value<InfoPopover text={MARKET_OVERVIEW_HELP.trackedValue} /></div>
              </th>
              <th scope="col">
                <div className="flex flex-wrap items-center justify-end gap-x-1.5">{SINCE_TRACKING_LABEL}<InfoPopover text={MARKET_OVERVIEW_HELP.trackedValueChange} /></div>
              </th>
              <th scope="col" className={styles.marketOverviewGroupStart}>
                <div className="flex flex-wrap items-center justify-end gap-x-1.5">Market Index<InfoPopover text={MARKET_OVERVIEW_HELP.index} /></div>
              </th>
              <th scope="col" data-market-overview-period-heading={selectedWindow}>
                <span>{periodLabel}</span>
                {isSinceFirstAvailable ? <span data-market-overview-period-coverage className="mt-0.5 block text-[8px] font-medium text-[var(--text-secondary)]">Since first available</span> : null}
              </th>
            </tr>
          </thead>
          <tbody>
            {families.map((family) => {
              const isVisible = visibleMarketKeys?.has(family.key) !== false;
              return (
              <tr
                key={family.key}
                data-market-overview-row={family.key}
                data-market-visible={isVisible ? "true" : "false"}
                className={`group/market-row ${styles.marketOverviewInteractiveRow} ${isVisible ? "" : styles.marketOverviewRowInactive}`}
                onClick={(event) => {
                  if (event.target.closest("button, a")) return;
                  onToggleMarket?.(family.key);
                }}
              >
                <th scope="row">
                  <button
                    type="button"
                    data-market-overview-toggle={family.key}
                    aria-pressed={isVisible}
                    onClick={() => onToggleMarket?.(family.key)}
                    className={styles.marketOverviewToggle}
                  >
                    <MarketSwatch color={family.color} />{family.label}
                  </button>
                  <Link
                    href={marketExplorerHref(family.key)}
                    data-market-explore-link={family.key}
                    aria-label={`Explore ${family.label} in Market Explorer`}
                    className={`ml-1.5 align-middle opacity-0 focus-visible:opacity-100 group-hover/market-row:opacity-100 ${EXPLORER_ROW_LINK_CLASS}`}
                  >
                    <span aria-hidden="true">Explore &rarr;</span>
                  </Link>
                </th>
                <td data-market-overview-metric="trackedValue" className={styles.marketOverviewGroupStart}>{formatBasketValue(family.basketValue)}</td>
                <td data-market-overview-tracked-change={SINCE_TRACKING}>
                  <ChangeValue
                    change={getFamilySinceTrackingChange(family)}
                    marketLabel={family.label}
                    windowLabel={SINCE_TRACKING_LABEL}
                    dimension={MARKET_DIMENSION_LABELS.pricePerformance}
                  />
                </td>
                <td data-market-overview-metric="index" className={`${styles.marketOverviewIndex} ${styles.marketOverviewGroupStart}`}>{formatIndexValue(family.indexValue)}</td>
                <td data-market-overview-change={selectedWindow}>
                  <ChangeValue
                    change={getPricePerformanceChange(family, selectedWindow)}
                    marketLabel={family.label}
                    windowLabel={periodLabel}
                    dimension={MARKET_DIMENSION_LABELS.pricePerformance}
                  />
                </td>
              </tr>
              );
            })}
            {/* THE MARKET HAS THREE ASSET CLASSES; two are tracked. Graded is
                acknowledged with NO numeric cells at all — not $0, not Index
                100, not 0.00%, and no trend line — because a zeroed row is
                indistinguishable from a market that collapsed. Where a tracked
                row offers an Explore action, this one states "Unavailable"
                rather than linking somewhere with nothing to show. */}
            {MARKET_PAGE_PLACEHOLDER_FAMILIES.map((placeholder) => (
              <tr
                key={placeholder.key}
                data-market-overview-row={placeholder.key}
                data-market-overview-row-placeholder="true"
                className={styles.marketOverviewRowInactive}
              >
                <th scope="row">
                  <span className="inline-flex items-center gap-2 text-[var(--text-secondary)]">
                    <MarketSwatch color="var(--text-secondary)" />
                    {placeholder.label}
                    <InfoPopover text={placeholder.reason} />
                  </span>
                </th>
                <td colSpan={4} data-market-overview-placeholder-status={placeholder.key} className="text-right text-[var(--text-secondary)]">
                  {placeholder.status}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile: compact scan rows. */}
      <ul data-market-overview-cards className="divide-y divide-[var(--border-subtle)] desk:hidden">
        {families.map((family) => {
          const isVisible = visibleMarketKeys?.has(family.key) !== false;
          return (
          <li key={family.key} data-market-overview-card={family.key}>
            <button type="button" data-market-overview-mobile-toggle={family.key} aria-pressed={isVisible} onClick={() => onToggleMarket?.(family.key)} className={`w-full px-3 py-1.5 text-left transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[rgba(45,212,191,0.65)] sm:px-4 ${isVisible ? "opacity-100" : "opacity-45"}`}>
            <span className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
              <MarketSwatch color={family.color} />{family.label}
            </span>

            <div className="mt-1 grid grid-cols-2 gap-x-3">
              <div data-market-overview-group="trackedValue">
                <div className="text-[9px] font-medium uppercase tracking-[0.07em] text-[var(--text-secondary)]">
                  Tracked Value
                </div>
                <p data-market-overview-metric="trackedValue" className="text-[15px] font-semibold leading-tight tabular-nums text-[var(--text-primary)]">{formatBasketValue(family.basketValue)}</p>
                <p data-market-overview-tracked-change={SINCE_TRACKING} className="text-[10px] text-[var(--text-secondary)]">
                  <ChangeValue
                    change={getFamilySinceTrackingChange(family)}
                    marketLabel={family.label}
                    windowLabel={SINCE_TRACKING_LABEL}
                    dimension={MARKET_DIMENSION_LABELS.pricePerformance}
                    className="font-semibold"
                  />
                  <span aria-hidden="true"> since tracking</span>
                </p>
              </div>

              <div data-market-overview-group="pricePerformance">
                <div className="text-[9px] font-medium uppercase tracking-[0.07em] text-[var(--text-secondary)]">
                  Market Index
                </div>
                <p data-market-overview-metric="index" className="text-[15px] font-semibold leading-tight tabular-nums text-[var(--text-primary)]">{formatIndexValue(family.indexValue)}</p>
                <p data-market-overview-change={selectedWindow} className="text-[10px] text-[var(--text-secondary)]">
                  <ChangeValue
                    change={getPricePerformanceChange(family, selectedWindow)}
                    marketLabel={family.label}
                    windowLabel={periodLabel}
                    dimension={MARKET_DIMENSION_LABELS.pricePerformance}
                    className="font-semibold"
                  />
                  <span aria-hidden="true"> {periodLabel}</span>
                  {isSinceFirstAvailable ? <span data-market-overview-mobile-period-coverage aria-hidden="true"> · since first available</span> : null}
                </p>
              </div>
            </div>
            </button>
            <div className="px-3 pb-1.5 sm:px-4">
              <Link
                href={marketExplorerHref(family.key)}
                data-market-explore-link={family.key}
                aria-label={`Explore ${family.label} in Market Explorer`}
                className={`inline-flex items-center rounded ${EXPLORER_ROW_LINK_CLASS}`}
              >
                Explore <span aria-hidden="true" className="ml-1">&rarr;</span>
              </Link>
            </div>
          </li>
          );
        })}
        {MARKET_PAGE_PLACEHOLDER_FAMILIES.map((placeholder) => (
          <li
            key={placeholder.key}
            data-market-overview-card={placeholder.key}
            data-market-overview-card-placeholder="true"
            className="px-3 py-2 opacity-60 sm:px-4"
          >
            <span className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
              <MarketSwatch color="var(--text-secondary)" />
              {placeholder.label}
              <InfoPopover text={placeholder.reason} />
              <span data-market-overview-placeholder-status={placeholder.key} className="ml-auto normal-case tracking-normal">
                {placeholder.status}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
