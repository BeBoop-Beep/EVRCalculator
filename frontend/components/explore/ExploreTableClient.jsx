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
 * aria-sort on the column the table is currently ordered by. Row navigation
 * stays a single real <a> per row, stretched over the row by a pseudo-element
 * rather than nesting interactive elements. Mobile is a purpose-built compact
 * row, not a shrunken table.
 *
 * COLUMN SORTING (Rankings completeness pass)
 * -------------------------------------------
 * Every quantitative header is a click target that re-orders the rows ALREADY IN
 * MEMORY. There is no fetch, no server round-trip and no recomputation behind a
 * header click — `targets` is the single optimized read this component is handed,
 * `sortTargetsByMode` puts it in canonical order once, and `sortRankingsRows`
 * returns a memoized permutation of that same array (see rankingsSort.mjs).
 *
 * Sorting is PRESENTATION. It never rewrites a score, a rank, a tier or the
 * cohort: the "#" column keeps showing the canonical Overall RIP V7 rank, so
 * under a non-default sort those numerals legitimately appear out of sequence.
 * The default view is unchanged — Overall RIP, strongest first.
 */

"use client";

import Link from "next/link";
import { useState, useMemo, useEffect, useRef, createContext, useContext } from "react";
import RankBadge from "@/components/ui/RankBadge";
import TableSearchInput from "@/components/ui/TableSearchInput";
import SetIdentity from "@/components/explore/SetIdentity";
import InfoPopover from "@/components/ui/InfoPopover";
import {
  EXPLORE_RANKING_MODES,
  getModeConfig,
  getScoreForMode,
  getScoreKind,
  isPublicScoreMode,
  getRankForMode,
  getRankedSetCountForMode,
  getTierForMode,
  formatModeScore,
  SCORE_KIND_PUBLIC,
} from "@/constants/exploreRankingConfig";
import { PUBLIC_SCORE_SCALE_NOTE, readCanonicalOverallRipV10 } from "./canonicalRipV7.mjs";
import {
  RANKINGS_DEFAULT_SORT,
  RANKINGS_SORT_COLUMNS,
  SORT_ASC,
  ariaSortFor,
  nextSortState,
  readCollectorAppealBlock,
  readModelBreakEven,
  readTypicalOpening,
  sortRankingsRows,
} from "./rankingsSort.mjs";
import { getTierTone } from "@/lib/explore/interpretationTone";
import { buildTcgSetHrefFromTarget } from "@/lib/explore/ripStatisticsRouting";
import styles from "./explore.module.css";
import { formatRankMovement } from "./rankingMovement.mjs";
import { readOptionalRankingsChase } from "./rankingsPresentation.mjs";
import { FamilySnapshot, RANKINGS_FAMILY_COLUMNS, RankingsFamilyCells, whySetRanks } from "./SetRipFamilyBreakdown.jsx";
import { RipScoreBadge, RipTierMark } from "./RipScoreBadge.jsx";

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

// Rows whose set logo skips lazy loading. Roughly one desktop viewport of rows —
// these are on screen the moment the table paints, so waiting for the lazy
// scheduler to discover them is latency for no saving. Everything past this
// stays lazy: at the dense-row thumbnail width a logo is ~2-3 kB, so six eager
// requests are ~15 kB and do not meaningfully contend with anything.
const EAGER_LOGO_ROW_LIMIT = 6;
const MOBILE_DECISION_COLUMN_IDS = ["setRip", "marketPrice", "typicalOpening", "modelBreakEven", "chanceToBeatCost", "topChase"];

function TopChaseCell({ target, compact = false }) {
  const chase = readOptionalRankingsChase(target);
  if (!chase) return <span className="text-[11px] text-[var(--text-secondary)]">{UNAVAILABLE_LABEL}</span>;
  return <span className={`block min-w-0 ${compact ? "max-w-32 text-right" : "text-left"}`}><span className="block truncate text-[12px] font-medium text-[var(--text-primary)]">{chase.name}</span><span className="block whitespace-nowrap text-[10px] tabular-nums text-[var(--text-secondary)]">{chase.marketValue !== null ? formatCurrency(chase.marketValue) : UNAVAILABLE_LABEL}{chase.oneInPacks !== null ? ` · 1 in ${Math.round(chase.oneInPacks).toLocaleString()} packs` : ""}</span></span>;
}

/**
 * Day-over-day RANK movement, and only for the two canonical modes.
 *
 * `previousOverallRipRank1d` / `previousFinancialRipRank1d` are produced by
 * `attach_daily_rip_rank_movements` in the backend snapshot builder, which now
 * reads the previous day's **Overall RIP V7** and **Financial RIP V3** ranks and
 * refuses to emit anything when the two snapshots were built under different
 * scoring versions. Before that fix it read the previous day's Overall RIP v4
 * and Financial RIP V2 ranks, and this function subtracted them from the current
 * V7/V3 rank — so a set whose V7 rank had not moved at all could still render
 * "↑2" purely because v4 disagreed with V7 about where it belonged.
 *
 * Every other mode is `unavailable`: no other lens has a published previous
 * rank, and inventing one from a different model is exactly the defect above.
 */
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

/**
 * A MISSING VALUE IS NOT ZERO.
 *
 * This used to be a bare `Number(value)` guarded only by `Number.isFinite`, and
 * `Number(null)`, `Number(undefined ?? "")` and `Number("")` are `0`, `NaN` and
 * `0`. So an absent pack cost printed "$0.00" and an absent probability printed
 * "0.0%" — a fabricated measurement wearing the same styling as a real one, in
 * the one place a reader cannot tell them apart. The null/undefined/"" cases are
 * rejected before the numeric coercion so the formatters below reach their
 * existing "-" branch, which is what every one of them was already written to
 * render for an unavailable metric.
 */
function toNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
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

// Average Loss is READ (not derived) in exactly ONE place — rankingsSort.mjs's
// readAverageLoss, which lifts the simulation's `expected_loss_when_losing`,
// i.e. Average Loss When Losing = E[pack_cost - value | value < pack_cost]. It
// is imported here so the number this cell prints and the number the Average
// Loss column sorts by cannot drift apart, and it is the same field the set
// page renders as "Average Loss When You Miss".

function buildRipLink(target) {
  return buildTcgSetHrefFromTarget(target, { tab: "overview" });
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
 * Read the ONE score a mode declares, plus its rank and cohort denominator.
 *
 * There is a single score field per mode now (see exploreRankingConfig), so
 * this can no longer hand a caller two differently-scaled candidates and let it
 * choose. `kind` travels with the value so the cell formats and suffixes it
 * correctly instead of assuming every column is a 0-100 public score.
 */
/**
 * Collector Appeal is a COLUMN, not a ranking mode.
 *
 * It is deliberately absent from `exploreRankingConfig`: the canonical public
 * Collector Appeal V3 block reaches the frontend only through the packaged
 * `publicRipContractV8`, and `canonicalRipV7.mjs` is the one reader allowed to
 * resolve it (see its module note — reading `openingExperience.collectorAppeal`
 * directly would be a second projection of the model in JavaScript, and the
 * flat `collector_appeal_score` on the same row is a retired CA7-era value
 * ranked against a different population). Routing it through this id lets the
 * existing score cell render it with the same one-field-by-kind contract, the
 * same `/10` treatment and the same Unavailable state as the other two public
 * scores, without inventing a mode that could then power a public ranking.
 */
const COLLECTOR_APPEAL_COLUMN = "collectorAppeal";

function readModeScore(target, modeId) {
  if (modeId === COLLECTOR_APPEAL_COLUMN) {
    const block = readCollectorAppealBlock(target);
    return {
      value: block.publicScore,
      kind: SCORE_KIND_PUBLIC,
      isPublic: true,
      rank: block.rank,
      cohort: block.cohortSize,
    };
  }

  return {
    value: getScoreForMode(target, modeId),
    kind: getScoreKind(modeId),
    isPublic: isPublicScoreMode(modeId),
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

const RELATIVE_SCORE_TOOLTIP =
  "Relative scores standardize each set against the current eligible cohort on a 0–10 scale.";

/**
 * Desktop score cell.
 *
 * ONE FIELD, FORMATTED BY ITS DECLARED KIND.
 *
 * This cell used to read a relative field and an absolute field and render
 * whichever existed — so the same column, with the same styling, held a
 * cohort-relative 0-100 public score for RIP Score and Financial RIP, and a
 * fixed-anchor or ratio value for every other mode, with nothing on screen
 * distinguishing them. `readModeScore` now returns one value and its `kind`.
 *
 * Only a `publicScore` mode gets the `/10` suffix and the scale tooltip;
 * a ratio prints `1.4x`; a plain index prints a bare number. A null value
 * renders an explicit Unavailable state, never a fabricated zero and never a
 * substitute from another scale.
 */
function ScoreCell({ target, modeId }) {
  const rankColumnMode = useContext(RankColumnModeContext);
  const { value, kind, isPublic, rank, cohort } = readModeScore(target, modeId);

  if (value === null) {
    return (
      <span className="text-[11px] font-medium text-[var(--text-secondary)]">{UNAVAILABLE_LABEL}</span>
    );
  }

  const rankText =
    rankColumnMode === modeId ? null : formatRankText(rank, cohort, { withCohort: false });

  return (
    <div
      className="flex min-w-0 flex-col items-end leading-tight"
      title={isPublic ? PUBLIC_SCORE_SCALE_NOTE : undefined}
    >
      <span className="text-[14px] font-semibold text-[var(--text-primary)]">
        {formatModeScore(value, kind)}
        {isPublic ? (
          <span className="pl-0.5 text-[10px] font-medium text-[var(--text-secondary)]">/10</span>
        ) : null}
      </span>
      {rankText !== null ? (
        <span className="mt-0.5 truncate text-[10px] text-[var(--text-secondary)]">{rankText}</span>
      ) : null}
    </div>
  );
}

/**
 * Mobile score block: labelled family (RIP Score / Financial RIP). Same
 * one-field-by-kind contract as the desktop cell, same suffix rule, same
 * unavailable state. Financial is never hidden on mobile. No border per metric:
 * the label carries the meaning, the shared row carries the frame.
 */
function MobileScoreBlock({ target, modeId, label }) {
  const rankColumnMode = useContext(RankColumnModeContext);
  const { value, kind, isPublic, rank, cohort } = readModeScore(target, modeId);

  const rankText =
    rankColumnMode === modeId ? null : formatRankText(rank, cohort, { compact: true, withCohort: false });

  return (
    <div className="min-w-0" title={isPublic ? PUBLIC_SCORE_SCALE_NOTE : undefined}>
      <div className="text-[9px] font-semibold uppercase tracking-[0.09em] text-[var(--text-secondary)]">{label}</div>
      {value === null ? (
        <div className="mt-0.5 text-[11px] font-medium text-[var(--text-secondary)]">{UNAVAILABLE_LABEL}</div>
      ) : (
        <div className="mt-0.5 flex flex-wrap items-baseline gap-x-1 text-[10px] text-[var(--text-secondary)]">
          <span className="text-[13px] font-semibold text-[var(--text-primary)]">
            {formatModeScore(value, kind)}
            {isPublic ? <span className="pl-0.5 text-[9px] font-medium text-[var(--text-secondary)]">/10</span> : null}
          </span>
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
 * Contract: canonical rank → the mode's one score field → name. Nulls always
 * sort last within each tier. The rank and score fields come from the SAME mode
 * config, so the displayed rank/cohort and the sort key describe one cohort and
 * one score version.
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

    // One score field per mode, so there is one tiebreak rather than a
    // relative-then-absolute chain that mixed two scales in one ordering.
    const scoreCmp = compareScoreDesc(
      getScoreForMode(left, modeId),
      getScoreForMode(right, modeId)
    );
    if (scoreCmp !== 0) {
      return scoreCmp;
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
      <span className={`${isLead ? "text-sm font-bold" : "text-xs font-semibold text-[var(--text-secondary)]"} tabular-nums`} style={tone ? { color: tone.textColor } : undefined}>
        #{rank}
      </span>
      {movement?.text && movement.text !== "N/A" ? <span className="text-[9px] font-medium tabular-nums text-[var(--text-secondary)]" aria-label={movement.label}>{movement.text}</span> : null}
    </span>
  );
}


function RankingInsight({ setRip }) {
  const explanation = whySetRanks(setRip);
  const heading = explanation.startsWith("Elite") ? "Elite across formats" : explanation.startsWith("Strong") ? "Strong family depth" : "Standout family strength";
  return <div data-ranking-insight className="flex max-w-[15rem] items-start gap-2.5"><span aria-hidden="true" className="mt-1 h-2.5 w-2.5 flex-none rotate-45 border border-[var(--ex-rank-accent,var(--accent))]" /><span><strong className="block text-xs leading-tight text-[var(--text-primary)]">{heading}</strong><span className="mt-1 block text-[10.5px] leading-[1.35] text-[var(--text-secondary)]">{explanation}</span></span></div>;
}

/**
 * A quantitative column heading that is also its own sort control.
 *
 * The <th> remains the semantic header and carries `aria-sort`; the <button>
 * inside it is the click/tap/Enter/Space target, which is what makes the sort
 * operable from the keyboard without inventing a separate control. The direction
 * caret is drawn by the `[aria-sort]` rule in explore.module.css — the same
 * indicator the table already used — so no new visual language is introduced.
 */
function SortableHeader({ columnId, label, sort, onSort, note, infoText = null, rowSpan }) {
  const ariaSort = ariaSortFor(sort, columnId);
  const isActive = Boolean(ariaSort);
  return (
    <th
      scope="col"
      className={styles.numeric}
      aria-sort={ariaSort}
      title={isActive ? note : `Sort by ${label}`}
      rowSpan={rowSpan}
    >
      <button
        type="button"
        className={styles.sortButton}
        onClick={() => onSort(columnId)}
        aria-label={
          isActive
            ? `${label}, sorted ${ariaSort}. Activate to reverse the sort direction.`
            : `Sort by ${label}, highest first.`
        }
      >
        <span>{label}</span>
      </button>
      {infoText ? <span className="ml-1 inline-flex normal-case"><InfoPopover text={infoText} /></span> : null}
    </th>
  );
}

export default function ExploreTableClient({ targets = [], loadError = false }) {
  const [selectedMode, setSelectedMode] = useState(DEFAULT_MODE);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [showAllMobileRows, setShowAllMobileRows] = useState(false);
  const [expandedMobileSet, setExpandedMobileSet] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  // Presentation-only column sort. `RANKINGS_DEFAULT_SORT` is Overall RIP
  // descending, which sortRankingsRows resolves to the canonical order itself,
  // so the first paint is byte-for-byte the leaderboard it has always been.
  const [sort, setSort] = useState(RANKINGS_DEFAULT_SORT);
  const [sortMenuOpen, setSortMenuOpen] = useState(false);
  const dropdownContainerRef = useRef(null);
  const sortMenuContainerRef = useRef(null);

  const currentModeConfig = EXPLORE_RANKING_MODES[selectedMode];
  // ONE canonical ordering pass over the already-fetched targets. Nothing below
  // re-reads the network, and a header click only re-runs the memo on the line
  // after this one.
  const canonicalTargets = useMemo(() => [...targets].sort((left, right) => {
    const leftRank = readCanonicalOverallRipV10(left).rank;
    const rightRank = readCanonicalOverallRipV10(right).rank;
    if (leftRank !== null && rightRank !== null && leftRank !== rightRank) return leftRank - rightRank;
    if (leftRank !== null) return -1;
    if (rightRank !== null) return 1;
    return String(left?.name || "").localeCompare(String(right?.name || ""));
  }), [targets]);
  const sortedTargets = useMemo(() => sortRankingsRows(canonicalTargets, sort), [canonicalTargets, sort]);
  const displayedTargets = useMemo(() => {
    const query = searchQuery.trim().toLocaleLowerCase();
    return query ? sortedTargets.filter((target) => String(target?.name || "").toLocaleLowerCase().includes(query)) : sortedTargets;
  }, [sortedTargets, searchQuery]);
  // The row's position in the CANONICAL order, used only as the "#" fallback for
  // a target the backend gave no rank. Taking it from the canonical array rather
  // than from the rendered index keeps that fallback meaning "where this set
  // sits on the leaderboard" instead of "where it happens to sit in this sort".
  const canonicalIndexByTarget = useMemo(
    () => new Map(canonicalTargets.map((target, index) => [target, index])),
    [canonicalTargets]
  );
  // Keyed off the CANONICAL order, so re-sorting a column does not collapse an
  // expanded mobile list — only a genuinely different cohort does.
  const mobilePreviewResetKey = useMemo(
    () => `${selectedMode}:${canonicalTargets.map((target) => `${target?.target_type}:${target?.target_id}`).join("|")}`,
    [selectedMode, canonicalTargets]
  );
  useEffect(() => {
    setShowAllMobileRows(false);
  }, [mobilePreviewResetKey]);
  // Only the row lists that actually overflow get the bottom fade, so a short
  // list never looks like it has been cut off.
  const isScrollable = displayedTargets.length > 6;
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

  useEffect(() => {
    if (!sortMenuOpen) {
      return undefined;
    }

    function handlePointerDown(event) {
      if (sortMenuContainerRef.current && !sortMenuContainerRef.current.contains(event.target)) {
        setSortMenuOpen(false);
      }
    }

    function handleKeyDown(event) {
      if (event.key === "Escape") {
        setSortMenuOpen(false);
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [sortMenuOpen]);

  // A header click is the ONLY thing this does: swap a small piece of local
  // state. No fetch, no router navigation, no revalidation.
  function handleSort(columnId) {
    setSort((current) => nextSortState(current, columnId));
  }

  function selectMobileSort(columnId) {
    setSort({ column: columnId, direction: RANKINGS_DEFAULT_SORT.direction });
    setSortMenuOpen(false);
  }

  const modeTitle = currentModeConfig?.title || "Best Sets to Rip Right Now";
  const tierLabel = currentModeConfig?.tierLabel || "Tier";
  const scoreLabel = currentModeConfig?.scoreLabel || "Score";
  const activeSortColumn = RANKINGS_SORT_COLUMNS[sort.column] || RANKINGS_SORT_COLUMNS.setRip;
  const activeSortLabel = activeSortColumn.label;
  const sortDirectionNote = sort.direction === SORT_ASC ? "lowest first" : "highest first";
  const sortNote = `Ordered by ${activeSortLabel}, ${sortDirectionNote}. Select any metric column heading to sort by it; select it again to reverse the direction.`;
  const visibleMobileTargets =
    showAllMobileRows || displayedTargets.length <= MOBILE_PREVIEW_LIMIT
      ? displayedTargets
      : displayedTargets.slice(0, MOBILE_PREVIEW_LIMIT);
  const hiddenMobileCount = Math.max(0, displayedTargets.length - visibleMobileTargets.length);

  return (
    <RankColumnModeContext.Provider value={selectedMode}>
    <section className={`${styles.surface} set-glass-surface flex min-w-0 flex-col`} aria-label="Compare all sets">
      <div className={`${styles.divider} px-3 py-3 sm:px-4 md:hidden`}>
        <div className="flex items-center justify-between gap-3">
          <h2 className="min-w-0 text-[18px] font-semibold leading-tight text-[var(--text-primary)]">Compare all sets</h2>
          <div className="relative flex-none" ref={sortMenuContainerRef}>
            <button
              type="button"
              onClick={() => setSortMenuOpen((open) => !open)}
              aria-expanded={sortMenuOpen}
              aria-haspopup="listbox"
              aria-label="Choose which metric the rankings are sorted by"
              className="inline-flex h-11 items-center justify-center rounded-full border border-[var(--border-subtle)] px-3 leading-none text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-hover)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
            >
              <span className="text-xs font-semibold">Metric</span>
            </button>
            {sortMenuOpen ? (
              <div className="fixed inset-x-3 bottom-20 z-30 max-h-[min(28rem,calc(100dvh-7rem))] overflow-y-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] shadow-[0_12px_30px_rgba(0,0,0,0.42)] sm:absolute sm:inset-x-auto sm:bottom-auto sm:right-0 sm:top-full sm:mt-2 sm:w-64" role="listbox">
                <div className="p-1.5">
                  {MOBILE_DECISION_COLUMN_IDS.map((columnId) => RANKINGS_SORT_COLUMNS[columnId]).map((column) => (
                    <button key={column.id} type="button" role="option" aria-selected={sort.column === column.id} onClick={() => selectMobileSort(column.id)} className={`flex min-h-11 w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-[13px] transition-colors ${sort.column === column.id ? "bg-[var(--surface-page)] text-[var(--text-primary)]" : "text-[var(--text-secondary)] hover:bg-[var(--surface-page)]/70 hover:text-[var(--text-primary)]"}`}>
                      <span>{column.label}</span>
                      {sort.column === column.id ? <span aria-hidden="true" className="font-bold text-[var(--accent)]">✓</span> : null}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </div>
        <p className="mt-2 text-xs font-semibold text-[var(--text-secondary)]"><span className="text-[var(--text-primary)]">{activeSortLabel}</span><span aria-hidden="true" className="px-2">•</span><span className="tabular-nums">{displayedTargets.length}</span> shown · {canonicalTargets.length} ranked</p>
        <TableSearchInput value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="Search sets..." ariaLabel="Search sets" containerClassName="mt-3" />
      </div>
      {/* One compact control row: title menu, definition, hint, cohort size. */}
      <div className={`${styles.divider} hidden gap-3 px-3 py-3 desk:py-2.5 sm:px-4 md:grid md:grid-cols-[minmax(0,1fr)_16rem_minmax(0,1fr)] md:items-center`}>
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

        <TableSearchInput value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="Search sets..." ariaLabel="Search sets" containerClassName="md:justify-self-center" />

        <div className="flex items-center justify-end gap-3 text-right">
          {/*
            The desktop sort control IS the column heading. Mobile has no header
            row to click, so the same sort state gets the module's existing
            menu affordance — the identical trigger + listbox pattern already
            used by the (currently hidden) ranking-mode picker above, not a new
            control system and not a filter bar. Selecting the active metric
            flips its direction, exactly as clicking its header does.
          */}
          <div className="relative hidden">
            <button
              type="button"
              onClick={() => setSortMenuOpen((open) => !open)}
              aria-expanded={sortMenuOpen}
              aria-haspopup="listbox"
              className="inline-flex min-h-11 max-w-[11rem] items-center gap-1 rounded-md px-1 py-0.5 text-[11px] font-medium text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
            >
              <span className="truncate">
                Sort: <span className="text-[var(--text-primary)]">{activeSortLabel}</span>
              </span>
              <span aria-hidden="true" className="flex-none text-[8px]">
                {sort.direction === SORT_ASC ? "▲" : "▼"}
              </span>
              <span className="sr-only">
                , {sortDirectionNote}. Change how the rankings are sorted.
              </span>
            </button>
            {sortMenuOpen ? (
              <div
                className="fixed inset-x-3 bottom-20 z-30 max-h-[min(28rem,calc(100dvh-7rem))] overflow-y-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] shadow-[0_12px_30px_rgba(0,0,0,0.42)] sm:absolute sm:inset-x-auto sm:bottom-auto sm:right-0 sm:top-full sm:mt-2 sm:w-64"
                role="listbox"
              >
                <div className="p-1.5">
                  {Object.values(RANKINGS_SORT_COLUMNS).map((column) => {
                    const columnAriaSort = ariaSortFor(sort, column.id);
                    return (
                      <button
                        key={column.id}
                        type="button"
                        role="option"
                        aria-selected={Boolean(columnAriaSort)}
                        onClick={() => {
                          handleSort(column.id);
                          setSortMenuOpen(false);
                        }}
                        className={`flex min-h-11 w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-[13px] transition-colors ${
                          columnAriaSort
                            ? "bg-[var(--surface-page)] text-[var(--text-primary)]"
                            : "text-[var(--text-secondary)] hover:bg-[var(--surface-page)]/70 hover:text-[var(--text-primary)]"
                        }`}
                      >
                        <span className="truncate">{column.label}</span>
                        {columnAriaSort ? (
                          <span aria-hidden="true" className="flex-none text-[9px]">
                            {columnAriaSort === "ascending" ? "▲" : "▼"}
                          </span>
                        ) : null}
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : null}
          </div>
          <span className="hidden text-[11px] text-[var(--text-secondary)] lg:inline">
            Select a set for the full rip breakdown.
          </span>
          <span className="whitespace-nowrap text-[10px] font-semibold uppercase tracking-[0.09em] text-[var(--text-secondary)]">
            <span className="tabular-nums text-[var(--text-primary)]">{displayedTargets.length}</span> shown · {canonicalTargets.length} ranked
          </span>
        </div>
      </div>

      {/* Table/Grid */}
      {displayedTargets.length > 0 ? (
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
                <col style={{ width: "3%" }} />
                <col style={{ width: "15%" }} />
                <col style={{ width: "7%" }} />
                <col style={{ width: "4%" }} />
                {RANKINGS_FAMILY_COLUMNS.map((column) => <col key={column.key} style={{ width: "5.7%" }} />)}
                <col style={{ width: "14%" }} />
              </colgroup>
              <thead className={styles.head}>
                <tr>
                  <th scope="col" className={styles.numeric}>
                    <span aria-hidden="true">#</span>
                    <span className="sr-only">Rank</span>
                  </th>
                  <th scope="col">Set</th>
                  <SortableHeader columnId="setRip" label="Set RIP Score" sort={sort} onSort={handleSort} note={sortNote} />
                  <th scope="col">Tier</th>
                  {RANKINGS_FAMILY_COLUMNS.map((column) => <th key={column.key} scope="col" aria-label={column.fullLabel} title={column.fullLabel} className="px-1.5 text-center leading-tight"><span className="inline-flex items-center justify-center gap-1">{column.label}{column.info ? <InfoPopover text={column.info} /> : null}</span></th>)}
                  <th scope="col">Format Strength</th>
                </tr>
              </thead>
              <tbody>
                {displayedTargets.map((target, index) => {
                  const canonicalOverall = readCanonicalOverallRipV10(target);
                  const tier = canonicalOverall.tier;
                  const modeRank = canonicalOverall.rank;
                  const isLead = modeRank <= LEAD_RANK_LIMIT;
                  const tone = tier ? getTierTone(tier) : null;
                  const rankMovement = formatRankMovement(null, modeRank, "unavailable");

                  return (
                    <tr
                      key={`${target.target_type}:${target.target_id}`}
                      className={`${styles.row} ${isLead ? styles.rowLead : ""}`}
                      style={tone ? { "--ex-rank-accent": tone.accentColor } : undefined}
                    >
                      <td className={styles.numeric}>
                        {modeRank === null ? <span className="text-xs text-[var(--text-secondary)]">Unavailable</span> : <RankMarker rank={modeRank} tier={tier} isLead={isLead} movement={rankMovement} />}
                      </td>
                      <td>
                        <Link href={buildRipLink(target)} className={styles.rowLink}>
                          <SetIdentity variant="compact" target={target} eager={index < EAGER_LOGO_ROW_LIMIT} />
                          <span className="mt-0.5 block text-[10px] text-[var(--text-secondary)]">{target?.setRipV1?.participatingFamilyCount ?? 0} scored families</span>
                        </Link>
                      </td>
                      <td className={styles.numeric}><RipScoreBadge score={canonicalOverall.publicScore} tier={tier} /></td>
                      <td className="text-center"><RipTierMark tier={tier} /></td>
                      <RankingsFamilyCells setRip={target?.setRipV1} />
                      <td className="align-middle"><RankingInsight setRip={target?.setRipV1} /></td>
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
              const canonicalOverall = readCanonicalOverallRipV10(target);
              const activeRank = canonicalOverall.rank;
              const tier = canonicalOverall.tier;
              const tierTone = tier ? getTierTone(tier) : null;
              const rowKey = `${target.target_type}:${target.target_id}`;
              const expanded = expandedMobileSet === rowKey;

              return (
                <article
                  key={rowKey}
                  className={styles.mobileRow}
                  style={tierTone ? { "--ex-rank-accent": tierTone.accentColor } : undefined}
                >
                  <button type="button" className="grid w-full grid-cols-[2rem_minmax(0,1fr)_auto_auto] items-center gap-2.5 text-left" aria-expanded={expanded} onClick={() => setExpandedMobileSet(expanded ? null : rowKey)}>
                    <span className="text-right text-sm font-bold tabular-nums text-[var(--text-primary)]">
                      {activeRank === null ? "—" : `#${activeRank}`}
                    </span>
                    <div className="min-w-0">
                      <SetIdentity variant="mobileRanking" target={target} eager={index < EAGER_LOGO_ROW_LIMIT} />
                    </div>
                    <div className="flex flex-none items-center gap-2"><RipScoreBadge score={canonicalOverall.publicScore} tier={tier} compact /><RipTierMark tier={tier} /></div>
                    <span aria-hidden="true" className={`text-sm transition-transform ${expanded ? "rotate-180" : ""}`}>⌄</span>
                  </button>
                  {expanded ? (
                    <div className="mt-2 border-t border-[var(--border-subtle)] pt-1">
                      <FamilySnapshot setRip={target?.setRipV1} layout="modules" compact />
                      <p className="pt-2 text-[9px] font-bold uppercase tracking-[0.12em] text-[var(--text-secondary)]">Format Strength</p>
                      <RankingInsight setRip={target?.setRipV1} />
                      <Link href={buildRipLink(target)} className="mt-2 inline-flex min-h-10 items-center text-xs font-semibold text-[var(--accent)]">View full Set RIP breakdown →</Link>
                    </div>
                  ) : null}
                </article>
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
