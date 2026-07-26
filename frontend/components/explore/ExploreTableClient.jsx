/**
 * Client component for Explore page table with ranking mode dropdown.
 * Handles dynamic ranking mode selection and table sorting.
 *
 * SCORE PRESENTATION (Phase 2-4 — absolute / relative / rank)
 * -----------------------------------------------------------
 * Every score-bearing cell reads AUTHORITATIVE backend fields only (never a
 * frontend-derived score): the absolute 0-100 formula result, the cohort
 * relative 0-100 position, and the rank within its ranked-set cohort. The
 * default "Best Sets to Rip Right Now" mode surfaces BOTH Overall RIP and
 * Financial RIP columns on desktop; every other mode shows a single
 * mode-scoped score cell. Mobile always shows both Overall and Financial score
 * families so Financial RIP is never hidden on small screens. Missing values
 * render an explicit "Unavailable" state — never a fabricated zero.
 */

"use client";

import Link from "next/link";
import { useState, useMemo, useEffect, useRef } from "react";
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
import { getDangerValueStyle } from "@/lib/explore/interpretationTone";
import { buildTcgSetHrefFromTarget } from "@/lib/explore/ripStatisticsRouting";

const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const DEFAULT_MODE = "overall";
const UNAVAILABLE_LABEL = "Unavailable";

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

function formatRankText(rank, cohort, { compact = false } = {}) {
  const parsedRank = toNumber(rank);
  if (parsedRank === null) {
    return null;
  }
  const parsedCohort = toNumber(cohort);
  if (parsedCohort === null) {
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

function getLeaderboardRecommendationLabel(target) {
  return (
    target?.leaderboard_label ||
    shortenCanonicalLabel(target?.canonical_recommendation_header) ||
    null
  );
}

function getExploreRankingBadgeLabel(label) {
  return String(label || "").replace(/\s+PROFILE$/i, "").trim();
}

function shortenCanonicalLabel(value) {
  const text = String(value || "").trim();
  if (!text) {
    return null;
  }
  for (const separator of [",", " - ", " — "]) {
    if (text.includes(separator)) {
      const [head] = text.split(separator, 1);
      return head.trim() || text;
    }
  }
  return text;
}

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

// Tooltip explaining the relative-vs-model distinction the cells present.
const RELATIVE_SCORE_TOOLTIP =
  "Relative scores standardize each set against the current eligible cohort on a 0–100 scale. " +
  "Model scores are the underlying formula outputs used before standardization.";

/**
 * Desktop score cell.
 *
 * The RELATIVE score is the public number and is rendered prominently. The raw
 * formula output (the "model score") is the small supporting line beneath,
 * alongside "#rank of n". Ratio-only and legacy-relative modes expose no
 * separate relative field, so their single score stays the prominent value and
 * no "Model score" line is shown. A null primary renders an explicit
 * Unavailable state (never a fabricated zero) rather than promoting the model
 * score in place of a missing relative one.
 */
function ScoreCell({ target, modeId }) {
  const config = getModeConfig(modeId);
  const { absolute, relative, rank, cohort } = readModeScore(target, modeId);

  const hasRelative = relative !== null;
  const primaryText = hasRelative
    ? formatRelative(relative)
    : absolute === null
    ? null
    : formatModeScore(absolute, config?.scoreFormat);

  if (primaryText === null) {
    return (
      <span className="text-sm font-medium text-[var(--text-secondary)]">{UNAVAILABLE_LABEL}</span>
    );
  }

  const rankText = formatRankText(rank, cohort);
  const metaParts = [];
  if (rankText !== null) {
    metaParts.push(rankText);
  }
  if (hasRelative && absolute !== null) {
    metaParts.push(`Model ${formatModeScore(absolute, config?.scoreFormat)}`);
  }

  return (
    <div className="flex min-w-0 flex-col leading-tight" title={hasRelative ? RELATIVE_SCORE_TOOLTIP : undefined}>
      <span className="text-sm font-semibold text-[var(--text-primary)]">{primaryText}</span>
      {metaParts.length > 0 ? (
        <span className="mt-0.5 truncate text-[11px] text-[var(--text-secondary)]">{metaParts.join(" · ")}</span>
      ) : null}
    </div>
  );
}

/**
 * Mobile score block: labelled family (Overall / Financial). Preserves the same
 * hierarchy as desktop — RELATIVE score prominent, "#rank/n" and the model
 * score as the small supporting line. Financial is never hidden on mobile.
 */
function MobileScoreBlock({ target, modeId, label }) {
  const config = getModeConfig(modeId);
  const { absolute, relative, rank, cohort } = readModeScore(target, modeId);

  const hasRelative = relative !== null;
  const primaryText = hasRelative
    ? formatRelative(relative)
    : absolute === null
    ? null
    : formatModeScore(absolute, config?.scoreFormat);
  const rankText = formatRankText(rank, cohort, { compact: true });

  return (
    <div
      className="min-w-0 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/45 px-2.5 py-1.5"
      title={hasRelative ? RELATIVE_SCORE_TOOLTIP : undefined}
    >
      <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{label}</div>
      {primaryText === null ? (
        <div className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{UNAVAILABLE_LABEL}</div>
      ) : (
        <div className="mt-0.5 flex flex-wrap items-baseline gap-x-1.5 text-[11px] text-[var(--text-secondary)]">
          <span className="text-sm font-semibold text-[var(--text-primary)]">{primaryText}</span>
          {rankText !== null ? <span>· {rankText}</span> : null}
          {hasRelative && absolute !== null ? (
            <span>· Model {formatModeScore(absolute, config?.scoreFormat)}</span>
          ) : null}
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

export default function ExploreTableClient({ targets = [], loadError = false }) {
  const [selectedMode, setSelectedMode] = useState(DEFAULT_MODE);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownContainerRef = useRef(null);

  const currentModeConfig = EXPLORE_RANKING_MODES[selectedMode];
  const sortedTargets = useMemo(() => sortTargetsByMode(targets, selectedMode), [targets, selectedMode]);
  const isScrollable = sortedTargets.length > 5;
  const leaderboardScrollClass = "index-scrollbar";
  const modeInfoText =
    currentModeConfig?.tooltip ||
    currentModeConfig?.description ||
    "Sets ranked by the strongest overall opening profile.";

  // The default Overall mode surfaces Overall RIP AND Financial RIP side by
  // side; every other mode collapses to a single mode-scoped score column.
  const isOverallMode = selectedMode === DEFAULT_MODE;
  const desktopGridClass = isOverallMode
    ? "grid grid-cols-[minmax(0,2fr)_0.7fr_1.05fr_1.05fr_0.85fr_0.9fr] gap-3"
    : "grid grid-cols-[minmax(0,2.3fr)_0.9fr_1.05fr_1fr_1.05fr] gap-3";

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

  return (
    <section className="rounded-2xl border border-[var(--border-subtle)] bg-[linear-gradient(180deg,rgba(16,26,40,0.95)_0%,rgba(10,16,28,0.95)_100%)] p-4 lg:p-6">
      {/* Header section */}
      <div className="border-b border-[var(--border-subtle)] pb-4">
        <div className="flex flex-col gap-2 md:grid md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] md:items-center">
          <div className="flex min-w-0 items-center justify-between gap-3 md:col-start-1 md:justify-start">
            <div className="flex min-w-0 items-center gap-2">
            <div className="relative min-w-0" ref={dropdownContainerRef}>
              <button
                type="button"
                onClick={() => setDropdownOpen((open) => !open)}
                aria-expanded={dropdownOpen}
                aria-haspopup="listbox"
                className="group inline-flex max-w-full items-center gap-1.5 rounded-lg px-1 py-1 text-left text-lg font-semibold text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-hover)]/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--surface-page)]"
              >
                <span className="truncate">{currentModeConfig?.title || "Best Sets to Rip Right Now"}</span>
                <svg
                  viewBox="0 0 20 20"
                  fill="none"
                  aria-hidden="true"
                  className={`h-3.5 w-3.5 flex-none opacity-70 transition-transform duration-200 ${dropdownOpen ? "rotate-180" : ""}`}
                >
                  <path d="M5 7.5L10 12.5L15 7.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>

              {/* Dropdown menu */}
              {dropdownOpen && (
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

            <div className="flex justify-end md:hidden">
              <div className="inline-flex items-center whitespace-nowrap rounded-xl border border-[var(--border-subtle)] bg-[rgba(8,14,24,0.72)] px-2.5 py-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
                {sortedTargets.length} RANKED SETS
              </div>
            </div>
          </div>

          <div className="mt-1 flex items-center justify-center md:col-start-2 md:mt-0">
            <div className="inline-flex items-center justify-center gap-1.5 text-center text-xs text-[var(--text-secondary)]">
            <svg
              viewBox="0 0 20 20"
              fill="none"
              aria-hidden="true"
              className="h-3.5 w-3.5 flex-none opacity-70"
            >
              <path
                d="M4.75 2.75L9.8 14.2L11.95 9.95L16.2 7.8L4.75 2.75Z"
                stroke="currentColor"
                strokeWidth="1.4"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <path d="M14.4 2.9V4.7" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
              <path d="M13.5 3.8H15.3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
              <path d="M16.2 5.8V6.9" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
              <path d="M15.65 6.35H16.75" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
            </svg>
            <span>Tap a set to see the full rip breakdown.</span>
            </div>
          </div>

          <div className="hidden md:flex md:col-start-3 md:justify-end">
            <div className="inline-flex items-center rounded-xl border border-[var(--border-subtle)] bg-[rgba(8,14,24,0.72)] px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
              {sortedTargets.length} RANKED SETS
            </div>
          </div>
        </div>
      </div>

      {/* Table/Grid */}
      {sortedTargets.length > 0 ? (
        <>
          {/* Desktop table */}
          <div className="mt-4 hidden md:block">
            <div className={`${desktopGridClass} px-3 pb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]`}>
              <span>Set</span>
              <span>{currentModeConfig?.tierLabel || "Tier"}</span>
              {isOverallMode ? (
                <>
                  <span>Overall RIP</span>
                  <span>Financial RIP</span>
                </>
              ) : (
                <span>{currentModeConfig?.scoreLabel || "Score"}</span>
              )}
              <span>Average Loss</span>
              <span>Chance to Beat Cost</span>
            </div>

            <div className={isScrollable ? `max-h-[34rem] space-y-2 overflow-y-auto pr-1 ${leaderboardScrollClass}` : "space-y-2"}>
              {sortedTargets.map((target) => {
                const averageLoss = estimateAverageLoss(target);
                const tier = (getTierForMode(target, selectedMode) || "").toString().toUpperCase() || null;
                const recommendationLabel = getLeaderboardRecommendationLabel(target);
                const displayRecommendationLabel = getExploreRankingBadgeLabel(recommendationLabel);

                return (
                  <Link
                    key={`${target.target_type}:${target.target_id}`}
                    href={buildRipLink(target)}
                    className={`${desktopGridClass} items-center rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/65 px-4 py-3.5 transition-colors hover:bg-[var(--surface-hover)]`}
                  >
                    <div className="min-w-0">
                      <SetIdentity
                        target={target}
                        interpretationLabel={displayRecommendationLabel}
                        tier={tier}
                        recommendationSeverity={target?.recommendation_severity || null}
                      />
                    </div>
                    <div className="flex items-start">
                      <RankBadge
                        rank={tier}
                        title={currentModeConfig?.tierLabel || "Tier"}
                        size="supporting"
                        format="tier"
                      />
                    </div>
                    {isOverallMode ? (
                      <>
                        <ScoreCell target={target} modeId="overall" />
                        <ScoreCell target={target} modeId="financial" />
                      </>
                    ) : (
                      <ScoreCell target={target} modeId={selectedMode} />
                    )}
                    <span className="text-sm font-semibold" style={getDangerValueStyle()}>
                      {formatLossCurrency(averageLoss)}
                    </span>
                    <span className="text-sm text-[var(--text-primary)]">{formatPercent(target?.prob_profit, true)}</span>
                  </Link>
                );
              })}
            </div>
          </div>

          {/* Mobile cards */}
          <div className={isScrollable ? `mt-4 grid max-h-[38rem] grid-cols-1 gap-2 overflow-y-auto pr-1 md:hidden ${leaderboardScrollClass}` : "mt-4 grid grid-cols-1 gap-2 md:hidden"}>
            {sortedTargets.map((target) => {
              const recommendationLabel = getLeaderboardRecommendationLabel(target);
              const displayRecommendationLabel = getExploreRankingBadgeLabel(recommendationLabel);
              const tier = (getTierForMode(target, selectedMode) || "").toString().toUpperCase() || null;

              return (
                <Link
                  key={`${target.target_type}:${target.target_id}`}
                  href={buildRipLink(target)}
                  className="flex flex-col gap-2.5 rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/65 p-3 transition-colors hover:bg-[var(--surface-hover)]"
                >
                  <div className="flex items-start gap-3">
                    <SetIdentity
                      target={target}
                      interpretationLabel={displayRecommendationLabel}
                      tier={tier}
                      recommendationSeverity={target?.recommendation_severity || null}
                      interpretationBadgeClassName="inline-flex max-w-full min-w-0 items-center whitespace-nowrap truncate px-3 py-1 text-[10px] leading-none tracking-[0.08em] sm:px-2.5 sm:py-1 sm:text-[11px]"
                    />
                    <div className="flex flex-none items-center self-start pt-1">
                      <RankBadge
                        rank={tier}
                        title={currentModeConfig?.tierLabel || "Tier"}
                        size="supporting"
                        format="tier"
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <MobileScoreBlock target={target} modeId="overall" label="Overall" />
                    <MobileScoreBlock target={target} modeId="financial" label="Financial" />
                  </div>
                </Link>
              );
            })}
          </div>
        </>
      ) : loadError ? (
        <p
          role="alert"
          className="mt-4 rounded-xl border border-dashed border-[var(--color-danger,#f87171)]/60 bg-[var(--surface-page)]/45 px-4 py-5 text-sm text-[var(--text-secondary)]"
        >
          Rankings are temporarily unavailable — the ranking service could not be reached. Please refresh in a moment.
        </p>
      ) : (
        <p className="mt-4 rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)]/45 px-4 py-5 text-sm text-[var(--text-secondary)]">
          Ranking snapshots are still loading. Open any set in RIP Statistics once data is available.
        </p>
      )}
    </section>
  );
}
