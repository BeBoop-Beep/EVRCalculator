"use client";

import InfoPopover from "@/components/ui/InfoPopover";
import {
  MARKET_DIMENSION_LABELS,
  MARKET_OVERVIEW_HELP,
  changeDirection,
  describeChange,
  formatBasketValue,
  formatChangePercent,
  formatIndexValue,
  formatMarketDate,
  getFamilyChange,
  getPricePerformanceChange,
} from "@/lib/explore/marketOverviewPresentation.mjs";
import { MARKET_EXPLORER_DETAIL_WINDOWS } from "@/lib/explore/marketExplorerState.mjs";
import { NEGATIVE_VALUE_COLOR, POSITIVE_VALUE_COLOR } from "@/lib/explore/interpretationTone";
import styles from "./explore.module.css";

// The selected-market detail strip — parent markets and Sealed submarkets in
// the same table, because a submarket is a market.
//
// THE SEMANTIC LOCK. Each column declares which published series it reads:
//   dimension "comparison" -> `changes`, the shared cross-market domain.
//   dimension "family"     -> `familyChanges`, this market's own tracking start.
// Only the family column may be labelled "Since Tracking". Reading the shared
// series under that label is the exact defect this split exists to prevent.
//
// Every cell is a backend change object; an unavailable window prints a dash
// rather than borrowing a neighbouring window's number.
function toneOf(direction) {
  if (direction === "positive") return POSITIVE_VALUE_COLOR;
  if (direction === "negative") return NEGATIVE_VALUE_COLOR;
  return "var(--text-secondary)";
}

const changeFor = (series, window) => (window.dimension === "family"
  ? getFamilyChange(series, window.key)
  : getPricePerformanceChange(series, window.key));

function ChangeValue({ change, marketLabel, windowLabel }) {
  const direction = changeDirection(change);
  const glyph = direction === "positive" ? "▲" : direction === "negative" ? "▼" : direction === "neutral" ? "—" : "";
  return (
    <span className="inline-flex items-baseline gap-1 tabular-nums" style={{ color: toneOf(direction) }}>
      {glyph ? <span aria-hidden="true" className="text-[0.75em] leading-none">{glyph}</span> : null}
      <span aria-hidden="true">{formatChangePercent(change)}</span>
      <span className="sr-only">{describeChange(marketLabel, windowLabel, change, { dimension: MARKET_DIMENSION_LABELS.pricePerformance })}</span>
    </span>
  );
}

export default function MarketExplorerDetails({ series = [] }) {
  const active = series.filter((entry) => entry.available !== false);

  return (
    <section data-market-explorer-details className="flex min-w-0 flex-col" aria-labelledby="market-explorer-details-heading">
      <div className={`${styles.divider} flex flex-wrap items-center gap-x-2 gap-y-1 px-3 py-3 sm:px-4`}>
        <h2 id="market-explorer-details-heading" className="text-[16px] font-semibold text-[var(--text-primary)]">
          Selected Market Detail
        </h2>
        <span className="inline-flex items-center gap-1 text-[11px] text-[var(--text-secondary)]">
          Tracked Value<InfoPopover text={MARKET_OVERVIEW_HELP.trackedValue} />
        </span>
        <span className="inline-flex items-center gap-1 text-[11px] text-[var(--text-secondary)]">
          Market Index<InfoPopover text={MARKET_OVERVIEW_HELP.index} />
        </span>
      </div>

      {active.length === 0 ? (
        <p role="status" className="px-4 py-6 text-sm text-[var(--text-secondary)]">
          Select a market to see its detail.
        </p>
      ) : (
        <>
          <div data-market-explorer-details-table className="hidden overflow-x-auto desk:block">
            <table className={styles.marketOverviewTable}>
              <caption className="sr-only">
                Tracked Value, Market Index, shared-comparison movements and each market&apos;s own Since Tracking movement, for every selected market and submarket.
              </caption>
              <thead>
                <tr>
                  <th scope="col">Market</th>
                  <th scope="col">Tracked Value</th>
                  <th scope="col">Market Index</th>
                  {MARKET_EXPLORER_DETAIL_WINDOWS.map((window) => (
                    <th
                      key={window.key}
                      scope="col"
                      data-market-explorer-detail-heading={window.key}
                      data-market-explorer-detail-dimension={window.dimension}
                    >
                      <div className="flex flex-wrap items-center justify-end gap-x-1.5">
                        {window.label}
                        {window.dimension === "family"
                          ? <InfoPopover text={MARKET_OVERVIEW_HELP.sinceTracking} />
                          : null}
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {active.map((entry) => (
                  <tr
                    key={entry.key}
                    data-market-explorer-detail-row={entry.key}
                    data-market-explorer-detail-group={entry.group || "card"}
                  >
                    <th scope="row">
                      <span className="inline-flex items-center gap-2">
                        <span aria-hidden="true" className="inline-block h-2.5 w-2.5 flex-none rounded-[3px]" style={{ backgroundColor: entry.color }} />
                        {/* Submarkets read as children of their parent rather
                            than as five more top-level markets. */}
                        {entry.isParent === false ? <span aria-hidden="true" className="opacity-50">↳</span> : null}
                        {entry.label}
                        {entry.definition ? <InfoPopover text={entry.definition} /> : null}
                      </span>
                    </th>
                    <td data-market-explorer-detail-metric="trackedValue">{formatBasketValue(entry.basketValue)}</td>
                    <td data-market-explorer-detail-metric="index" className={styles.marketOverviewIndex}>{formatIndexValue(entry.indexValue)}</td>
                    {MARKET_EXPLORER_DETAIL_WINDOWS.map((window) => (
                      <td key={window.key} data-market-explorer-detail-change={window.key}>
                        <ChangeValue
                          change={changeFor(entry, window)}
                          marketLabel={entry.label}
                          windowLabel={window.label}
                        />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile: one stacked card per market, same values, no side scroll. */}
          <ul data-market-explorer-details-cards className="divide-y divide-[var(--border-subtle)] desk:hidden">
            {active.map((entry) => (
              <li key={entry.key} data-market-explorer-detail-card={entry.key} className="px-3 py-3 sm:px-4">
                <span className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
                  <span aria-hidden="true" className="inline-block h-2.5 w-2.5 flex-none rounded-[3px]" style={{ backgroundColor: entry.color }} />
                  <span className="text-[var(--text-primary)]">{entry.label}</span>
                  {entry.productCount ? <span className="ml-auto normal-case tracking-normal">{entry.productCount} products</span> : null}
                </span>
                <div className="mt-1.5 grid grid-cols-2 gap-x-3">
                  <div>
                    <div className="text-[9px] font-medium uppercase tracking-[0.07em] text-[var(--text-secondary)]">Tracked Value</div>
                    <p data-market-explorer-detail-metric="trackedValue" className="text-[15px] font-semibold leading-tight tabular-nums text-[var(--text-primary)]">{formatBasketValue(entry.basketValue)}</p>
                  </div>
                  <div>
                    <div className="text-[9px] font-medium uppercase tracking-[0.07em] text-[var(--text-secondary)]">Market Index</div>
                    <p data-market-explorer-detail-metric="index" className="text-[15px] font-semibold leading-tight tabular-nums text-[var(--text-primary)]">{formatIndexValue(entry.indexValue)}</p>
                  </div>
                </div>
                <dl className="mt-2 grid grid-cols-3 gap-x-3 gap-y-1.5 tab:grid-cols-5">
                  {MARKET_EXPLORER_DETAIL_WINDOWS.map((window) => (
                    <div key={window.key} data-market-explorer-detail-change={window.key} className="min-w-0">
                      <dt className="text-[9px] font-medium uppercase tracking-[0.07em] text-[var(--text-secondary)]">{window.label}</dt>
                      <dd className="text-[11px] font-semibold leading-tight">
                        <ChangeValue
                          change={changeFor(entry, window)}
                          marketLabel={entry.label}
                          windowLabel={window.label}
                        />
                      </dd>
                    </div>
                  ))}
                </dl>
                {entry.historyStartDate ? (
                  <p className="mt-1.5 text-[10px] text-[var(--text-secondary)]">
                    Tracking since {formatMarketDate(entry.historyStartDate)}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
