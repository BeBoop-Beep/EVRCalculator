/**
 * Client component for Explore page table with ranking mode dropdown.
 * Handles dynamic ranking mode selection and table sorting.
 *
 * SCORE PRESENTATION (Phase 2-4 — absolute / relative / rank)
 * -----------------------------------------------------------
 * Every score-bearing cell reads AUTHORITATIVE backend fields only (never a
 * frontend-derived score): the absolute 0-100 formula result, the cohort
 * relative 0-100 position, and the rank within its ranked-set cohort. The
 * default "Best Sets to Rip Right Now" mode surfaces BOTH RIP Score and
 * Financial RIP columns on desktop; every other mode shows a single
 * mode-scoped score cell. Mobile always shows both RIP Score and Financial score
 * families so Financial RIP is never hidden on small screens. Missing values
 * render an explicit "Unavailable" state — never a fabricated zero.
 *
 * PRESENTATION (Explore refinement Phase 2)
 * -----------------------------------------
 * Desktop renders a real semantic <table> — caption, <th scope="col">, and
 * aria-sort on the column the active ranking mode orders by. Sorting is still
 * driven exclusively by that mode (see sortTargetsByMode); no per-column sort
 * interaction was introduced, so the canonical rank -> relative -> absolute ->
 * name contract is untouched. Row navigation stays a single real <a> per row,
 * stretched over the row by a pseudo-element rather than nesting interactive
 * elements. Mobile is a purpose-built compact row, not a shrunken table.
 */

"use client";

import Link from "next/link";
import { useState, useMemo, useEffect, useRef, createContext, useContext } from "react";
import RankBadge from "@/components/ui/RankBadge";
import SetIdentity from "@/components/explore/SetIdentity";
import InfoPopover from "@/components/ui/InfoPopover";
import {
  EXPLORE_RANKING_MODES,
  getModeConfig,
  getAbsoluteScoreForMode,
  getRelativeScoreForMode,
  getRankForMode,
  getRankedSetCountForMode,
  getTierForMode,
  formatModeScore,
} from "@/constants/exploreRankingConfig";
import { getDangerValueStyle, getTierTone } from "@/lib/explore/interpretationTone";
import { buildTcgSetHrefFromTarget } from "@/lib/explore/ripStatisticsRouting";
import styles from "./explore.module.css";
import { formatRankMovement } from "./rankingMovement.mjs";

const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const DEFAULT_MODE = "overall";
const UNAVAILABLE_LABEL = "Unavailable";
const MOBILE_PREVIEW_LIMIT = 5;
/**
 * The ranking-mode picker is HIDDEN, not removed: every alternate lens
 * (Financial, Profit, Safety, Desirability, Chase, EV, Upside …) is planned to
 * sit behind a paid tier. Flipping this back to `true` restores the dropdown
 * exactly as it was — the modes, the sorting, and the mode-scoped columns all
 * still work, they just have no trigger while this is false.
 */
const RANKING_MODE_PICKER_ENABLED = false;
// Rows inside the top slice of the ladder get a narrow tier-tinted edge. The
// rank numeral and the tier letter say the same thing in text, so the tint is
// reinforcement and never the only signal.
const LEAD_RANK_LIMIT = 3;

function getRipMovementForMode(target, modeId, currentRank) {
  if (modeId === "overall") {
    return formatRankMovement(
      target?.previousOverallRipRank1d ?? target?.previous_overall_rip_rank_1d,
      currentRank,
      target?.overallRipRankComparisonStatus1d ?? target?.overall_rip_rank_comparison_status_1d
    );
  }
  if (modeId === "financial") {
    return formatRankMovement(
      target?.previousFinancialRipRank1d ?? target?.previous_financial_rip_rank_1d,
      currentRank,
      target?.financialRipRankComparisonStatus1d ?? target?.financial_rip_rank_comparison_status_1d
    );
  }
  return formatRankMovement(null, currentRank, "unavailable");
}

function toNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizeProbability(value) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return null;
  }
  return parsed > 1 ? parsed / 100 : parsed;
}

function formatCurrency(value) {
  const parsed = toNumber(value);
  return parsed === null ? "-" : currencyFormatter.format(parsed);
}

function formatLossCurrency(value) {
  const parsed = toNumber(value);
  return parsed === null ? "-" : `-${currencyFormatter.format(Math.abs(parsed))}`;
}

function formatPercent(value, probability = false) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return "-";
  }
  const normalized = probability ? normalizeProbability(parsed) * 100 : parsed;
  return `${normalized.toFixed(1)}%`;
}

function formatRelative(value) {
  const parsed = toNumber(value);
  return parsed === null ? null : parsed.toFixed(1);
}

/**
 * Cohort size is stated once per module (the "N ranked sets" line), so the
 * per-cell rank stays a bare "#4" unless a caller explicitly asks for the
 * cohort — that keeps "of 21" from repeating on every row of every column.
 */
function formatRankText(rank, cohort, { compact = false, withCohort = true } = {}) {
  const parsedRank = toNumber(rank);
  if (parsedRank === null) {
    return null;
  }
  const parsedCohort = toNumber(cohort);
  if (parsedCohort === null || !withCohort) {
    return `#${parsedRank}`;
  }
  return compact ? `#${parsedRank}/${parsedCohort}` : `#${parsedRank} of ${parsedCohort}`;
}

function estimateAverageLoss(target) {
  const packCost = toNumber(target?.pack_cost);
  const meanValue = toNumber(target?.mean_value);
  if (packCost === null || meanValue === null) {
    return null;
  }
  return packCost - meanValue;
}

function buildRipLink(target) {
  return buildTcgSetHrefFromTarget(target, { tab: "insights", section: "rip-score" });
}

// NO INTERPRETATION BADGE. The leaderboard row used to carry a verdict pill
// derived from `leaderboard_label` / `canonical_recommendation_header`, toned by
// `recommendation_severity`. Those three fields are output of the retired
// Profit/Safety/Stability interpretation engine, which scores neither Financial
// RIP V3 nor Collector Appeal V3, so the pill was current-looking copy about a
// superseded model. It is removed rather than replaced: the row already states
// tier, rank, RIP Score and Financial RIP, and inventing replacement advice here
// would be a second, unscored opinion.

/**
 * Read the authoritative absolute / relative / rank / cohort quartet for one
 * mode from a target. Never derives a score; only reads backend fields.
 */
function readModeScore(target, modeId) {
  return {
    absolute: getAbsoluteScoreForMode(target, modeId),
    relative: getRelativeScoreForMode(target, modeId),
    rank: getRankForMode(target, modeId),
    cohort: getRankedSetCountForMode(target, modeId),
  };
}

/**
 * The mode whose rank the table's leading "#" column already shows. A score
 * cell for that same mode omits its own "#rank" line, because the two would
 * always print the same number on the same row. Every other column keeps its
 * rank — Financial RIP genuinely ranks a set differently from RIP Score.
 */
const RankColumnModeContext = createContext(null);

// Tooltip explaining what the displayed score means.
const RELATIVE_SCORE_TOOLTIP =
  "Relative scores standardize each set against the current eligible cohort on a 0–100 scale.";

/**
 * Desktop score cell.
 *
 * The RELATIVE score is the public number and the ONLY score shown; "#rank" is
 * the small supporting line beneath it. The raw formula output (the "model
 * score") is intentionally not displayed — it is an internal quantity that
 * meant nothing to readers next to the standardized score. It is still read
 * from the backend because ratio-only and legacy-relative modes expose no
 * relative field and fall back to it as their single displayed score. A null
 * primary renders an explicit Unavailable state, never a fabricated zero.
 */
function ScoreCell({ target, modeId }) {
  const config = getModeConfig(modeId);
  const rankColumnMode = useContext(RankColumnModeContext);
  const { absolute, relative, rank, cohort } = readModeScore(target, modeId);

  const hasRelative = relative !== null;
  const primaryText = hasRelative
    ? formatRelative(relative)
    : absolute === null
    ? null
    : formatModeScore(absolute, config?.scoreFormat);

  if (primaryText === null) {
    return (
      <span className="text-[11px] font-medium text-[var(--text-secondary)]">{UNAVAILABLE_LABEL}</span>
    );
  }

  const rankText =
    rankColumnMode === modeId ? null : formatRankText(rank, cohort, { withCohort: false });

  return (
    <div className="flex min-w-0 flex-col items-end leading-tight" title={hasRelative ? RELATIVE_SCORE_TOOLTIP : undefined}>
      <span className="text-[14px] font-semibold text-[var(--text-primary)]">{primaryText}</span>
      {rankText !== null ? (
        <span className="mt-0.5 truncate text-[10px] text-[var(--text-secondary)]">{rankText}</span>
      ) : null}
    </div>
  );
}

/**
 * Mobile score block: labelled family (Overall / Financial). Preserves the same
 * hierarchy as desktop — RELATIVE score prominent, "#rank" as the small
 * supporting value, no model score. Financial is never hidden on mobile. No
 * border per metric: the label carries the meaning, the shared row carries the
 * frame.
 */
function MobileScoreBlock({ target, modeId, label }) {
  const config = getModeConfig(modeId);
  const rankColumnMode = useContext(RankColumnModeContext);
  const { absolute, relative, rank, cohort } = readModeScore(target, modeId);

  const hasRelative = relative !== null;
  const primaryText = hasRelative
    ? formatRelative(relative)
    : absolute === null
    ? null
    : formatModeScore(absolute, config?.scoreFormat);
  const rankText =
    rankColumnMode === modeId ? null : formatRankText(rank, cohort, { compact: true, withCohort: false });

  return (
    <div className="min-w-0" title={hasRelative ? RELATIVE_SCORE_TOOLTIP : undefined}>
      <div className="text-[9px] font-semibold uppercase tracking-[0.09em] text-[var(--text-secondary)]">{label}</div>
      {primaryText === null ? (
        <div className="mt-0.5 text-[11px] font-medium text-[var(--text-secondary)]">{UNAVAILABLE_LABEL}</div>
      ) : (
        <div className="mt-0.5 flex flex-wrap items-baseline gap-x-1 text-[10px] text-[var(--text-secondary)]">
          <span className="text-[13px] font-semibold text-[var(--text-primary)]">{primaryText}</span>
          {rankText !== null ? <span>{rankText}</span> : null}
        </div>
      )}
    </div>
  );
}

/**
 * Sort targets by the selected ranking mode.
 *
 * Contract (Phase 2): canonical rank → relative score → absolute score → name.
 * Nulls always sort last within each tier. The rank, relative, and absolute
 * fields all come from the SAME mode config, so the displayed rank/cohort and
 * the sort key describe one cohort and one score version.
 */
function compareRankAsc(left, right) {
  if (left !== null && right !== null) {
    return left === right ? 0 : left - right;
  }
  if (left !== null) {
    return -1;
  }
  if (right !== null) {
    return 1;
  }
  return 0;
}

function compareScoreDesc(left, right) {
  if (left !== null && right !== null) {
    return left === right ? 0 : right - left;
  }
  if (left !== null) {
    return -1;
  }
  if (right !== null) {
    return 1;
  }
  return 0;
}

function sortTargetsByMode(targets, modeId) {
  const mode = EXPLORE_RANKING_MODES[modeId] || EXPLORE_RANKING_MODES.overall;
  const hasRankField = Boolean(mode?.rankField);

  return [...targets].sort((left, right) => {
    if (hasRankField) {
      const rankCmp = compareRankAsc(getRankForMode(left, modeId), getRankForMode(right, modeId));
      if (rankCmp !== 0) {
        return rankCmp;
      }
    }

    const relativeCmp = compareScoreDesc(
      getRelativeScoreForMode(left, modeId),
      getRelativeScoreForMode(right, modeId)
    );
    if (relativeCmp !== 0) {
      return relativeCmp;
    }

    const absoluteCmp = compareScoreDesc(
      getAbsoluteScoreForMode(left, modeId),
      getAbsoluteScoreForMode(right, modeId)
    );
    if (absoluteCmp !== 0) {
      return absoluteCmp;
    }

    return String(left?.name || "").localeCompare(String(right?.name || ""));
  });
}

/**
 * The row's ladder position for the active mode. Falls back to the render
 * order only for display, never for ordering — sortTargetsByMode already put
 * the rows in canonical order, so the fallback index and the canonical rank
 * agree whenever the backend supplies a rank.
 */
function RankMarker({ rank, tier, isLead, movement }) {
  const tone = isLead && tier ? getTierTone(tier) : null;
  return (
    <span className="inline-flex flex-col items-end leading-tight">
      <span className={`text-[12px] font-semibold tabular-nums ${isLead ? "" : "text-[var(--text-secondary)]"}`} style={tone ? { color: tone.textColor } : undefined}>
        {rank}
      </span>
      <span className="text-[9px] font-medium tabular-nums text-[var(--text-secondary)]" aria-label={movement.label}>{movement.text}</span>
    </span>
  );
}

export default function ExploreTableClient({ targets = [], loadError = false }) {
  const [selectedMode, setSelectedMode] = useState(DEFAULT_MODE);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [showAllMobileRows, setShowAllMobileRows] = useState(false);
  const dropdownContainerRef = useRef(null);

  const currentModeConfig = EXPLORE_RANKING_MODES[selectedMode];
  const sortedTargets = useMemo(() => sortTargetsByMode(targets, selectedMode), [targets, selectedMode]);
  const mobilePreviewResetKey = useMemo(
    () => `${selectedMode}:${sortedTargets.map((target) => `${target?.target_type}:${target?.target_id}`).join("|")}`,
    [selectedMode, sortedTargets]
  );
  useEffect(() => {
    setShowAllMobileRows(false);
  }, [mobilePreviewResetKey]);
  // Only the row lists that actually overflow get the bottom fade, so a short
  // list never looks like it has been cut off.
  const isScrollable = sortedTargets.length > 6;
  const leaderboardScrollClass = "index-scrollbar";
  // The relative-vs-model explanation lives here as well as on the cell
  // titles: the stretched row link sits above the cells, so the module
  // popover is the reliable keyboard- and touch-accessible route to it.
  const modeInfoText = `${
    currentModeConfig?.tooltip ||
    currentModeConfig?.description ||
    "Sets ranked by the strongest overall opening profile."
  } ${RELATIVE_SCORE_TOOLTIP}`;

  // The default Overall mode surfaces RIP Score AND Financial RIP side by
  // side; every other mode collapses to a single mode-scoped score column.
  const isOverallMode = selectedMode === DEFAULT_MODE;

  useEffect(() => {
    if (!dropdownOpen) {
      return undefined;
    }

    function handlePointerDown(event) {
      if (dropdownContainerRef.current && !dropdownContainerRef.current.contains(event.target)) {
        setDropdownOpen(false);
      }
    }

    function handleKeyDown(event) {
      if (event.key === "Escape") {
        setDropdownOpen(false);
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [dropdownOpen]);

  const modeTitle = currentModeConfig?.title || "Best Sets to Rip Right Now";
  const tierLabel = currentModeConfig?.tierLabel || "Tier";
  const scoreLabel = currentModeConfig?.scoreLabel || "Score";
  const sortNote = RANKING_MODE_PICKER_ENABLED
    ? `Ordered by ${isOverallMode ? "RIP Score" : scoreLabel}, best first. Change the ranking with the ${modeTitle} menu.`
    : `Ordered by ${isOverallMode ? "RIP Score" : scoreLabel}, best first.`;
  const visibleMobileTargets =
    showAllMobileRows || sortedTargets.length <= MOBILE_PREVIEW_LIMIT
      ? sortedTargets
      : sortedTargets.slice(0, MOBILE_PREVIEW_LIMIT);
  const hiddenMobileCount = Math.max(0, sortedTargets.length - visibleMobileTargets.length);

  return (
    <RankColumnModeContext.Provider value={selectedMode}>
    <section className={`${styles.surface} set-glass-surface flex min-w-0 flex-col`} aria-labelledby="explore-best-sets-heading">
      {/* One compact control row: title menu, definition, hint, cohort size. */}
      <div className={`${styles.divider} flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-3 desk:py-2.5 sm:px-4`}>
        <div className="flex min-w-0 items-center gap-1.5">
          <div className="relative min-w-0" ref={dropdownContainerRef}>
            <h2
              id="explore-best-sets-heading"
              className={
                RANKING_MODE_PICKER_ENABLED
                  ? "min-w-0"
                  : "min-w-0 truncate text-[18px] font-semibold leading-[1.25] text-[var(--text-primary)] desk:text-[15px] desk:leading-normal"
              }
            >
              {RANKING_MODE_PICKER_ENABLED ? (
                <button
                  type="button"
                  onClick={() => setDropdownOpen((open) => !open)}
                  aria-expanded={dropdownOpen}
                  aria-haspopup="listbox"
                  className="group inline-flex max-w-full items-center gap-1.5 rounded-md px-1 py-0.5 text-left text-[18px] font-semibold leading-[1.25] text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-hover)]/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] desk:text-[15px] desk:leading-normal"
                >
                  <span className="truncate">{modeTitle}</span>
                  <svg
                    viewBox="0 0 20 20"
                    fill="none"
                    aria-hidden="true"
                    className={`h-3.5 w-3.5 flex-none opacity-70 transition-transform duration-200 ${dropdownOpen ? "rotate-180" : ""}`}
                  >
                    <path d="M5 7.5L10 12.5L15 7.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  <span className="sr-only">Change ranking</span>
                </button>
              ) : (
                modeTitle
              )}
            </h2>

            {/* Dropdown menu */}
            {RANKING_MODE_PICKER_ENABLED && dropdownOpen && (
              <div
                className="absolute left-0 top-full z-30 mt-2 max-h-80 w-[min(24rem,calc(100vw-2.5rem))] overflow-y-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] shadow-[0_12px_30px_rgba(0,0,0,0.42)] index-scrollbar"
                role="listbox"
              >
                <div className="p-1.5">
                  {Object.entries(EXPLORE_RANKING_MODES).map(([modeId, mode]) => (
                    <button
                      key={modeId}
                      type="button"
                      role="option"
                      aria-selected={selectedMode === modeId}
                      onClick={() => {
                        setSelectedMode(modeId);
                        setDropdownOpen(false);
                      }}
                      className={`w-full rounded-lg px-3 py-2.5 text-left text-sm transition-colors ${
                        selectedMode === modeId
                          ? "bg-[var(--surface-page)] text-[var(--text-primary)]"
                          : "text-[var(--text-secondary)] hover:bg-[var(--surface-page)]/70 hover:text-[var(--text-primary)]"
                      }`}
                    >
                      <div className="font-medium">{mode.title || mode.label}</div>
                      <div className="mt-0.5 text-xs text-[var(--text-secondary)]">{mode.tooltip || mode.description}</div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
          <InfoPopover text={modeInfoText} />
        </div>

        <div className="ml-auto flex items-center gap-3">
          <span className="hidden text-[11px] text-[var(--text-secondary)] lg:inline">
            Select a set for the full rip breakdown.
          </span>
          <span className="whitespace-nowrap text-[10px] font-semibold uppercase tracking-[0.09em] text-[var(--text-secondary)]">
            <span className="tabular-nums text-[var(--text-primary)]">{sortedTargets.length}</span> ranked sets
          </span>
        </div>
      </div>

      {/* Table/Grid */}
      {sortedTargets.length > 0 ? (
        <>
          {/* Desktop table */}
          <div className={`hidden md:block ${isScrollable ? styles.scrollShell : ""}`}>
          <div className={`${styles.scrollBox} ${leaderboardScrollClass}`}>
            <table className={styles.table}>
              <caption className="sr-only">
                {modeTitle}. {sortNote}
              </caption>
              {/*
                Percentage widths on the data columns (rather than fixed rem)
                so the numeric columns grow with the table instead of dumping
                every extra pixel into the Set column when the module is full
                width. Set stays auto and absorbs what is left.
              */}
              <colgroup>
                <col style={{ width: "2.6rem" }} />
                <col />
                <col style={{ width: "9.5%" }} />
                <col style={{ width: "12%" }} />
                {isOverallMode ? <col style={{ width: "12%" }} /> : null}
                <col style={{ width: "11%" }} />
                <col style={{ width: "13%" }} />
                <col style={{ width: "12%" }} />
              </colgroup>
              <thead className={styles.head}>
                <tr>
                  <th scope="col" className={styles.numeric}>
                    <span aria-hidden="true">#</span>
                    <span className="sr-only">Rank</span>
                  </th>
                  <th scope="col">Set</th>
                  <th scope="col">{tierLabel}</th>
                  {isOverallMode ? (
                    <>
                      <th scope="col" className={styles.numeric} aria-sort="descending" title={sortNote}>
                        <span>RIP Score</span>
                      </th>
                      <th scope="col" className={styles.numeric}>
                        <span>Financial RIP</span>
                      </th>
                    </>
                  ) : (
                    <th scope="col" className={styles.numeric} aria-sort="descending" title={sortNote}>
                      <span>{scoreLabel}</span>
                    </th>
                  )}
                  <th scope="col" className={styles.numeric}>
                    Average Loss
                  </th>
                  <th scope="col" className={styles.numeric}>
                    Market Pack Price
                  </th>
                  <th scope="col" className={styles.numeric}>
                    Chance to Beat Cost
                  </th>
                </tr>
              </thead>
              <tbody>
                {sortedTargets.map((target, index) => {
                  const averageLoss = estimateAverageLoss(target);
                  const tier = (getTierForMode(target, selectedMode) || "").toString().toUpperCase() || null;
                  const modeRank = getRankForMode(target, selectedMode) ?? index + 1;
                  const isLead = modeRank <= LEAD_RANK_LIMIT;
                  const tone = isLead && tier ? getTierTone(tier) : null;
                  const rankMovement = getRipMovementForMode(target, selectedMode, modeRank);

                  return (
                    <tr
                      key={`${target.target_type}:${target.target_id}`}
                      className={`${styles.row} ${isLead ? styles.rowLead : ""}`}
                      style={tone ? { "--ex-rank-accent": tone.accentColor } : undefined}
                    >
                      <td className={styles.numeric}>
                        <RankMarker rank={modeRank} tier={tier} isLead={isLead} movement={rankMovement} />
                      </td>
                      <td>
                        <Link href={buildRipLink(target)} className={styles.rowLink}>
                          <SetIdentity variant="compact" target={target} />
                        </Link>
                      </td>
                      <td>
                        <RankBadge rank={tier} title={tierLabel} format="tier" />
                      </td>
                      {isOverallMode ? (
                        <>
                          <td className={styles.numeric}>
                            <ScoreCell target={target} modeId="overall" />
                          </td>
                          <td className={styles.numeric}>
                            <ScoreCell target={target} modeId="financial" />
                          </td>
                        </>
                      ) : (
                        <td className={styles.numeric}>
                          <ScoreCell target={target} modeId={selectedMode} />
                        </td>
                      )}
                      <td className={`${styles.numeric} text-[13px] font-semibold`} style={getDangerValueStyle()}>
                        {formatLossCurrency(averageLoss)}
                      </td>
                      <td className={`${styles.numeric} text-[13px] text-[var(--text-primary)]`}>
                        {formatCurrency(target?.pack_cost)}
                      </td>
                      <td className={`${styles.numeric} text-[13px] text-[var(--text-primary)]`}>
                        {formatPercent(target?.prob_profit, true)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          </div>

          {/* Mobile rows — a compact purpose-built layout, not a shrunken table. */}
          <div className="md:hidden">
            <div className="space-y-2 px-3 py-2 sm:px-4">
            {visibleMobileTargets.map((target, index) => {
              const tier = (getTierForMode(target, selectedMode) || "").toString().toUpperCase() || null;
              const modeRank = getRankForMode(target, selectedMode) ?? index + 1;
              const isLead = modeRank <= LEAD_RANK_LIMIT;
              const averageLoss = estimateAverageLoss(target);
              const rankMovement = getRipMovementForMode(target, selectedMode, modeRank);

              return (
                <Link
                  key={`${target.target_type}:${target.target_id}`}
                  href={buildRipLink(target)}
                  className={styles.mobileRow}
                >
                  <div className="flex items-center gap-2.5">
                    <span className="w-5 flex-none text-right">
                      <RankMarker rank={modeRank} tier={tier} isLead={isLead} movement={rankMovement} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <SetIdentity variant="compact" target={target} />
                    </div>
                    <RankBadge rank={tier} title={tierLabel} format="tier" />
                  </div>
                  <div className="mt-2 flex items-start gap-4 pl-[1.95rem]">
                    <MobileScoreBlock target={target} modeId="overall" label="Overall" />
                    <MobileScoreBlock target={target} modeId="financial" label="Financial" />
                    <div className="min-w-0">
                      <div className="text-[9px] font-semibold uppercase tracking-[0.09em] text-[var(--text-secondary)]">
                        Avg loss
                      </div>
                      <div className="mt-0.5 text-[13px] font-semibold" style={getDangerValueStyle()}>
                        {formatLossCurrency(averageLoss)}
                      </div>
                    </div>
                    <div className="min-w-0">
                      <div className="text-[9px] font-semibold uppercase tracking-[0.09em] text-[var(--text-secondary)]">Market price</div>
                      <div className="mt-0.5 text-[13px] text-[var(--text-primary)]">{formatCurrency(target?.pack_cost)}</div>
                    </div>
                  </div>
                </Link>
              );
            })}
            {hiddenMobileCount > 0 ? (
              <button
                type="button"
                onClick={() => setShowAllMobileRows((open) => !open)}
                aria-expanded={showAllMobileRows}
                aria-label={showAllMobileRows ? "Show fewer ranked sets" : `Show ${hiddenMobileCount} more ranked sets`}
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
            ) : null}
            </div>
          </div>
        </>
      ) : loadError ? (
        <p role="alert" className="px-4 py-6 text-sm text-[var(--text-secondary)]">
          Rankings are temporarily unavailable — the ranking service could not be reached. Please refresh in a moment.
        </p>
      ) : (
        <p className="px-4 py-6 text-sm text-[var(--text-secondary)]">
          Ranking snapshots are still loading. Open any set in RIP Statistics once data is available.
        </p>
      )}
    </section>
    </RankColumnModeContext.Provider>
  );
}
