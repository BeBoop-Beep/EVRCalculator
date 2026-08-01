/**
 * Top Rankings — the compact companion leaderboard beside "Best Sets to Rip
 * Right Now". It currently ranks sets by SET VALUE (the canonical checklist
 * set value), not by a RIP score, so the two modules answer different
 * questions instead of repeating one.
 *
 * It renders the SAME already-fetched targets the main Explore table receives
 * (no extra request, no duplicated client state) and reads the checklist set
 * value the targets payload is already enriched with:
 *   checklistSetValue / checklistSetValueAsOf / …PricedCardCount / …TotalCardCount
 * (snake_case aliases accepted because the payload carries both spellings).
 *
 * There is no backend rank for checklist set value, so the position shown is
 * simply this list's own descending order — a presentational index, never a
 * cohort rank, and it is described that way in the accessible caption. No
 * value is derived, converted, or filled in: a set without a checklist value
 * is omitted rather than shown as zero.
 */

"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { formatHistoryDate, getHistoryDateKey } from "./historyDateFormatting.mjs";
import { buildTcgSetHrefFromTarget } from "@/lib/explore/ripStatisticsRouting";
import styles from "./explore.module.css";
import { buildPreviousSetValueRanks, formatRankMovement, getSetValueMovement, getStableSetId } from "./rankingMovement.mjs";

const LEAD_RANK_LIMIT = 3;
const UNAVAILABLE_LABEL = "Unavailable";
const MOBILE_PREVIEW_LIMIT = 5;

const setValueFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});
const signedSetValueFormatter = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", signDisplay: "always", maximumFractionDigits: 0 });

function toNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function readSetValue(target) {
  return toNumber(target?.checklistSetValue ?? target?.checklist_set_value);
}

function readSetValueAsOf(target) {
  return getHistoryDateKey(target?.checklistSetValueAsOf ?? target?.checklist_set_value_as_of);
}

function readPricedCoverage(target) {
  return {
    priced: toNumber(target?.checklistSetValuePricedCardCount ?? target?.checklist_set_value_priced_card_count),
    total: toNumber(target?.checklistSetValueTotalCardCount ?? target?.checklist_set_value_total_card_count),
  };
}

function getInitials(name) {
  const words = String(name || "")
    .split(/\s+/)
    .filter(Boolean);
  if (words.length === 0) {
    return "PK";
  }
  return words
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase();
}

function LadderLogo({ target, name }) {
  const [failed, setFailed] = useState(false);
  const src = String(target?.logo_image_url || target?.symbol_image_url || "").trim();

  if (!src || failed) {
    return (
      <span className="flex h-6 w-6 items-center justify-center rounded bg-[rgba(255,255,255,0.05)] text-[8px] font-semibold uppercase text-[var(--text-secondary)]">
        {getInitials(name)}
      </span>
    );
  }

  return (
    <img
      src={src}
      alt=""
      className="h-6 w-6 object-contain"
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
    />
  );
}

/**
 * Order the ladder by checklist set value, highest first. Sets the snapshot
 * has no checklist value for are dropped rather than ranked at zero.
 */
function buildLadder(targets) {
  return (Array.isArray(targets) ? targets : [])
    .map((target) => ({
      target,
      value: readSetValue(target),
      asOf: readSetValueAsOf(target),
      coverage: readPricedCoverage(target),
    }))
    .filter((row) => row.value !== null)
    .sort((left, right) => {
      if (right.value !== left.value) {
        return right.value - left.value;
      }
      return String(left.target?.name || "").localeCompare(String(right.target?.name || ""));
    })
    .map((row, index) => ({ ...row, position: index + 1 }));
}

export default function ExploreTopRankings({ targets = [], loadError = false }) {
  const ladder = useMemo(() => buildLadder(targets), [targets]);
  const previousRanks = useMemo(() => buildPreviousSetValueRanks(targets), [targets]);
  const [showAllMobileRows, setShowAllMobileRows] = useState(false);

  // Rows are priced per set, so the snapshot dates can differ. The newest date
  // is the module's headline; anything older is called out on its own row
  // rather than letting one stale set hide behind a single global date.
  const latestAsOf = useMemo(
    () => ladder.reduce((latest, row) => (row.asOf && row.asOf > latest ? row.asOf : latest), ""),
    [ladder]
  );
  const mobilePreviewResetKey = useMemo(
    () => ladder.map(({ target }) => `${target?.target_type}:${target?.target_id}`).join("|"),
    [ladder]
  );
  const hiddenMobileCount = Math.max(0, ladder.length - MOBILE_PREVIEW_LIMIT);

  useEffect(() => {
    setShowAllMobileRows(false);
  }, [mobilePreviewResetKey]);

  return (
    <section className={`${styles.surfaceQuiet} flex min-w-0 flex-col`} aria-labelledby="explore-top-rankings-heading">
      <div className={`${styles.divider} flex items-center gap-2 px-3 py-3 desk:py-2.5 sm:px-4`}>
        <h2
          id="explore-top-rankings-heading"
          className="text-[18px] font-semibold leading-[1.25] text-[var(--text-primary)] desk:text-[15px] desk:leading-normal"
        >
          Top Rankings
        </h2>
        <span className="ml-auto whitespace-nowrap text-[10px] font-semibold uppercase tracking-[0.09em] text-[var(--text-secondary)]">
          Set Value
        </span>
      </div>

      {ladder.length > 0 ? (
        <div className={ladder.length > 9 ? styles.scrollShell : undefined}>
          <ol
            className={`${styles.ladderScroll} index-scrollbar`}
            aria-label="Sets ordered by checklist set value, highest first"
          >
            {ladder.map(({ target, value, asOf, coverage, position }, index) => {
              const isMobileCollapsedRow = !showAllMobileRows && hiddenMobileCount > 0 && index >= MOBILE_PREVIEW_LIMIT;
              const name = String(target?.name || target?.target_id || "Unknown Set");
              const isLead = position <= LEAD_RANK_LIMIT;
              const isStale = Boolean(asOf && latestAsOf && asOf < latestAsOf);
              const staleLabel = isStale ? formatHistoryDate(asOf, { month: "short", day: "numeric" }) : null;
              const stableId = getStableSetId(target);
              const comparisonStatus = target?.setValueComparisonStatus7d ?? target?.set_value_comparison_status_7d;
              const rankMovement = formatRankMovement(previousRanks.get(stableId), position, comparisonStatus, "7d");
              const valueMovement = getSetValueMovement(target);
              const valueMovementText = valueMovement
                ? `${signedSetValueFormatter.format(valueMovement.amount)} · ${valueMovement.percent >= 0 ? "+" : ""}${valueMovement.percent.toFixed(1)}% 7D`
                : comparisonStatus === "new" ? "NEW · 7D" : "N/A · 7D";
              const valueMovementLabel = valueMovement
                ? `Set value ${valueMovement.amount >= 0 ? "increased" : "decreased"} by ${Math.abs(valueMovement.amount).toFixed(0)} dollars, or ${Math.abs(valueMovement.percent).toFixed(1)} percent, over 7 days`
                : comparisonStatus === "new" ? "No comparable set value 7 days ago" : "Seven-day set value history unavailable";
              // Partial checklist pricing is common enough that showing the
              // ratio on every affected row reads as clutter rather than as a
              // caveat, so it lives in the row's detail text. A stale snapshot
              // date is the genuine exception and stays visible inline.
              const detail = [
                `Checklist set value ${value === null ? UNAVAILABLE_LABEL : setValueFormatter.format(value)}`,
                asOf ? `as of ${formatHistoryDate(asOf, { month: "short", day: "numeric", year: "numeric" })}` : null,
                coverage.priced !== null && coverage.total !== null
                  ? `${coverage.priced} of ${coverage.total} cards priced`
                  : null,
              ]
                .filter(Boolean)
                .join(" · ");

              return (
                <li key={`${target.target_type}:${target.target_id}`} className={isMobileCollapsedRow ? "hidden desk:list-item" : undefined}>
                  <Link
                    // A set-value row belongs on Overview, where the set value
                    // and its trend live — not on the Insights RIP breakdown.
                    href={buildTcgSetHrefFromTarget(target, { tab: "overview" })}
                    className={styles.ladderRow}
                    title={detail}
                    style={{ "--ex-rank-strength": isLead ? 0.7 : 0.22 }}
                  >
                    <span className="flex flex-col items-end leading-tight">
                    <span
                      className={`text-right text-[12px] font-semibold tabular-nums desk:text-[13px] ${
                        isLead ? "text-[var(--text-primary)]" : "text-[var(--text-secondary)]"
                      }`}
                    >
                      {position}
                    </span>
                    <span className="text-[9px] font-medium tabular-nums text-[var(--text-secondary)]" aria-label={rankMovement.label}>{rankMovement.text}</span>
                    </span>
                    <LadderLogo target={target} name={name} />
                    <span className="min-w-0 truncate text-[13px] font-medium text-[var(--text-primary)] desk:text-sm">{name}</span>
                    <span className="flex min-w-0 flex-col items-end leading-tight">
                      <span className="flex items-baseline gap-1.5">
                      <span className="text-[13px] font-semibold tabular-nums text-[var(--text-primary)] desk:text-sm">
                        {value === null ? UNAVAILABLE_LABEL : setValueFormatter.format(value)}
                      </span>
                      {staleLabel ? (
                        <span className="text-[10px] tabular-nums text-[var(--text-secondary)] desk:text-[11px]">
                          <span className="sr-only">priced </span>
                          {staleLabel}
                        </span>
                      ) : null}
                      </span>
                      <span className="max-w-full truncate text-[9px] tabular-nums text-[var(--text-secondary)] desk:text-[10px]" aria-label={valueMovementLabel}>
                        {valueMovementText}
                      </span>
                    </span>
                  </Link>
                </li>
              );
            })}
            {hiddenMobileCount > 0 ? (
              <li className="pt-1 desk:hidden">
                <button
                  type="button"
                  onClick={() => setShowAllMobileRows((open) => !open)}
                  aria-expanded={showAllMobileRows}
                  aria-label={showAllMobileRows ? "Show fewer top rankings" : `Show ${hiddenMobileCount} more top rankings`}
                  className="inline-flex min-h-11 items-center gap-1.5 rounded-md px-1 py-0.5 text-[12px] font-medium text-[var(--text-primary)] transition-colors hover:text-[var(--accent)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
                >
                  <span>{showAllMobileRows ? "Show less" : `Show ${hiddenMobileCount} more`}</span>
                  <svg
                    viewBox="0 0 20 20"
                    fill="none"
                    aria-hidden="true"
                    className={`h-3.5 w-3.5 flex-none transition-transform duration-200 ${showAllMobileRows ? "rotate-180" : ""}`}
                  >
                    <path d="M5 7.5L10 12.5L15 7.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
              </li>
            ) : null}
          </ol>
        </div>
      ) : loadError ? (
        <p role="alert" className="px-4 py-6 text-sm text-[var(--text-secondary)]">
          Top Rankings are temporarily unavailable — the ranking service could not be reached.
        </p>
      ) : (
        <p className="px-4 py-6 text-sm text-[var(--text-secondary)]">
          Ranked sets appear here once the latest set value snapshot is available.
        </p>
      )}
    </section>
  );
}
