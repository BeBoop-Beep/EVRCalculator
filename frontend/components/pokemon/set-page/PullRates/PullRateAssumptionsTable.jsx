"use client";

// React is imported explicitly (rather than relying on the automatic JSX
// runtime) so this component can be rendered directly by the node:test +
// react-test-renderer suite, matching MoversTickerViewport.jsx.
import React from "react";
import {
  formatCardCount,
  formatOddsDenominator,
  formatPullFrequency,
  formatRarityLabel,
} from "./pullRateFormatting.mjs";
import { selectPullRateRows } from "./pullRateRowsSelector.mjs";

// The whole Pull Rate Assumptions section: one compact, always-visible
// quick-reference table. Every available rarity/slot row renders immediately —
// there is no accordion, no group-heading row, and no second table shell, so
// there is no collapsed duplicate of the advanced rows in the DOM.
//
// Card Pool stays in the table: it is the eligible-card count that the
// specific-card odds are derived from, so the odds column is hard to read
// without it. The value is rendered straight from the normalized payload —
// this component never counts cards or recomputes a pool size, and never
// computes a pull rate. All four columns format through the existing shared
// helpers in pullRateFormatting.mjs.
export default function PullRateAssumptionsTable({ pullRateAssumptions }) {
  const rows = selectPullRateRows(pullRateAssumptions);

  if (rows.length === 0) {
    return <p className="text-sm text-[var(--text-secondary)]">Pull-rate assumptions are not available for this set yet.</p>;
  }

  return (
    <div className="w-full max-w-full min-w-0 overflow-x-auto rounded-xl border border-[var(--border-subtle)] bg-transparent">
      <table className="w-full min-w-full table-fixed text-left">
        <colgroup>
          {/* Card Pool is the narrowest column — it is a short numeric value. */}
          <col className="w-[38%]" />
          <col className="w-[14%]" />
          <col className="w-[24%]" />
          <col className="w-[24%]" />
        </colgroup>
        <thead className="set-glass-table-header">
          <tr>
            <th className="px-2 py-1.5 text-left text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)] sm:px-3 sm:py-2">Rarity / Slot</th>
            <th className="px-2 py-1.5 text-left text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)] sm:px-3 sm:py-2">Card Pool</th>
            <th className="px-2 py-1.5 text-left text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)] sm:px-3 sm:py-2">Pull Frequency</th>
            <th className="px-2 py-1.5 text-left text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)] sm:px-3 sm:py-2">Specific Card Odds</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--border-subtle)]">
          {rows.map(({ key, row, groupKey }) => (
            <tr key={key}>
              <td className="min-w-0 break-words px-2 py-1.5 text-xs text-[var(--text-primary)] whitespace-normal sm:px-3 sm:py-2 sm:text-sm">
                {formatRarityLabel(row.rarity)}
              </td>
              <td className="min-w-0 px-2 py-1.5 text-xs tabular-nums text-[var(--text-secondary)] whitespace-nowrap sm:px-3 sm:py-2 sm:text-sm">
                {formatCardCount(row.cardCount ?? row.card_count ?? row.eligibleCardCount ?? row.eligible_card_count)}
              </td>
              <td className="min-w-0 break-words px-2 py-1.5 text-xs text-[var(--text-secondary)] whitespace-normal sm:px-3 sm:py-2 sm:text-sm">
                {formatPullFrequency(row, groupKey)}
              </td>
              <td className="min-w-0 break-words px-2 py-1.5 text-xs text-[var(--accent)] whitespace-normal sm:px-3 sm:py-2 sm:text-sm">
                {formatOddsDenominator(row.specificCardOddsDenominator ?? row.specific_card_odds_denominator)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
