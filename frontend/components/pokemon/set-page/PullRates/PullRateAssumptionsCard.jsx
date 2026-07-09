"use client";

import InfoPopover from "@/components/ui/InfoPopover";
import {
  formatCardCount,
  formatGroupLabel,
  formatOddsDenominator,
  formatPullFrequency,
  formatRarityLabel,
  buildGroupsForRender,
} from "./pullRateFormatting.mjs";

const HEADER_INFO_TEXT = (
  <div className="space-y-1.5 text-left">
    <p className="font-semibold text-[var(--text-primary)]">Pull Rate Assumptions</p>
    <p className="text-[var(--text-secondary)]">
      These are modeled estimates, not official Pokemon odds. This section explains inDex pack-structure assumptions, hit-rarity assumptions, and special-pack rules sourced from set config data.
    </p>
  </div>
);

export function PullRateTable({ groups }) {
  return (
    <div className="w-full max-w-full min-w-0 overflow-x-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/45">
      <table className="w-full min-w-full table-fixed divide-y divide-[var(--border-subtle)] text-left">
        <colgroup>
          <col className="w-[34%]" />
          <col className="w-[16%]" />
          <col className="w-[24%]" />
          <col className="w-[26%]" />
        </colgroup>
        <thead className="bg-[var(--surface-page)]/70">
          <tr>
            <th className="px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Rarity / Slot</th>
            <th className="px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Card Pool</th>
            <th className="px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Pull Frequency</th>
            <th className="px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Specific Card Odds</th>
          </tr>
        </thead>
        {groups.map((group) => (
          <tbody key={`group:${group.key || group.label}`} className="divide-y divide-[var(--border-subtle)]">
            <tr className="bg-[var(--surface-page)]/30">
              <th colSpan={4} className="px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
                {group.label || formatGroupLabel(group.key)}
              </th>
            </tr>
            {group.rows.map((row) => (
              <tr key={`${group.key || group.label}:${row.rarity}:${row.slotLabel || ""}`}>
                <td className="min-w-0 px-3 py-2 text-sm text-[var(--text-primary)] whitespace-normal">{formatRarityLabel(row.rarity)}</td>
                <td className="min-w-0 px-3 py-2 text-sm text-[var(--text-secondary)] whitespace-normal">{formatCardCount(row.cardCount ?? row.card_count ?? row.eligibleCardCount ?? row.eligible_card_count)}</td>
                <td className="min-w-0 px-3 py-2 text-sm text-[var(--text-secondary)] whitespace-normal">{formatPullFrequency(row, group.key)}</td>
                <td className="min-w-0 px-3 py-2 text-sm text-[var(--accent)] whitespace-normal">{formatOddsDenominator(row.specificCardOddsDenominator ?? row.specific_card_odds_denominator)}</td>
              </tr>
            ))}
          </tbody>
        ))}
      </table>
    </div>
  );
}

export function PullRateMobileRows({ groups }) {
  return (
    <div className="space-y-2">
      {groups.map((group) => (
        <div key={`group:${group.key || group.label}`} className="space-y-2">
          <p className="px-1 text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{group.label || formatGroupLabel(group.key)}</p>
          {group.rows.map((row) => (
            <div
              key={`${group.key || group.label}:${row.rarity}:${row.slotLabel || ""}:mobile`}
              className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/45 p-3"
            >
              <p className="text-sm font-semibold text-[var(--text-primary)]">{formatRarityLabel(row.rarity)}</p>
              <div className="mt-2 grid grid-cols-1 gap-1.5 text-xs">
                <p className="text-[var(--text-secondary)]"><span className="font-semibold uppercase tracking-[0.06em]">Card Pool:</span> {formatCardCount(row.cardCount ?? row.card_count ?? row.eligibleCardCount ?? row.eligible_card_count)}</p>
                <p className="text-[var(--text-secondary)]"><span className="font-semibold uppercase tracking-[0.06em]">Pull Frequency:</span> {formatPullFrequency(row, group.key)}</p>
                <p className="text-[var(--accent)]"><span className="font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">Specific Card Odds:</span> {formatOddsDenominator(row.specificCardOddsDenominator ?? row.specific_card_odds_denominator)}</p>
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

export { buildGroupsForRender };

export default function PullRateAssumptionsCard({ pullRateAssumptions, embedded = false }) {
  const groups = buildGroupsForRender(pullRateAssumptions);
  const hasRows = groups.some((group) => Array.isArray(group.rows) && group.rows.length > 0);

  if (embedded) {
    return hasRows ? (
      <PullRateTable groups={groups} />
    ) : (
      <p className="text-sm text-[var(--text-secondary)]">Pull-rate assumptions are not available for this set yet.</p>
    );
  }

  return (
    <details className="group rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-5 sm:p-6">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-left transition-colors hover:text-white">
        <div>
          <div className="flex min-w-0 items-center gap-2">
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">Pull Rate Assumptions</h2>
            <InfoPopover text={HEADER_INFO_TEXT} />
          </div>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">Modeled rarity odds and inDEx-derived specific-card odds used by this simulation.</p>
        </div>

        <div className="flex items-center gap-2">
          <svg
            aria-hidden="true"
            viewBox="0 0 20 20"
            className="h-5 w-5 flex-none text-[var(--text-secondary)] transition-transform duration-150 group-open:rotate-180"
            fill="currentColor"
          >
            <path d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.12l3.71-3.89a.75.75 0 1 1 1.08 1.04l-4.25 4.45a.75.75 0 0 1-1.08 0L5.21 8.27a.75.75 0 0 1 .02-1.06Z" />
          </svg>
        </div>
      </summary>

      <div className="mt-4 space-y-3">
        <p className="text-sm text-[var(--text-secondary)]">
          These are modeled estimates, not official Pokemon odds. This full-pack model is sourced from set config assumptions and inDEx-derived rarity counts when available.
        </p>

        {hasRows ? (
          <>
            <div className="hidden md:block">
              <PullRateTable groups={groups} />
            </div>
            <div className="md:hidden">
              <PullRateMobileRows groups={groups} />
            </div>
          </>
        ) : (
          <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/45 px-3 py-2.5">
            <p className="text-sm text-[var(--text-secondary)]">Pull-rate assumptions are not available for this set yet.</p>
          </div>
        )}
      </div>
    </details>
  );
}
