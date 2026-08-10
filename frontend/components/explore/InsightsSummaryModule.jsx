"use client";

// The Insights "Insights Summary": ONE grouped surface carrying the three
// canonical public metrics, and the only place on the page whose rails are
// allowed an elevated glow.
//
// EXACTLY THREE METRICS, AND NOTHING ELSE
// ---------------------------------------
//   RIP Score        the canonical Overall RIP V7 headline (gold family)
//   Financial RIP    the canonical Financial RIP V3 score   (blue/cyan family)
//   Collector Appeal the canonical Collector Appeal V3 score (purple family)
//
// The three neutral one-line explanations are IMPORTED from OverviewRipSummary
// rather than restated here, so Overview and Insights can never drift into two
// different descriptions of the same metric.
//
// WHY THIS IS A SEPARATE COMPONENT FROM OverviewRipSummary
// --------------------------------------------------------
// Overview's summary is a quiet block inside a long scroll and must keep its
// current restraint. The Insights summary is the top of its own tab and is the
// one elevated surface in the redesign. Parameterising one component with a
// "loud" flag would put Overview one prop away from inheriting the glow; two
// components that share the copy constants and the selectors cannot.
//
// NOTHING IS COMPUTED HERE. Every score, tier, rank and denominator is lifted
// from the single resolved canonical bundle. Every visible `/100` score uses
// the backend cohort-relative score; fixed-anchor absolute model outputs never
// drive the visible number or rail. A missing value renders an em dash — never
// a zero, never a legacy score, never the other metric's value. The rail width
// is a presentation-only reading of the score already on screen; when the score
// is unavailable the rail renders as an empty track.

import React, { useMemo } from "react";

import { resolveCanonicalFinancialRip, selectFinancialRipV3Breakdown } from "./financialRipV3Selector.mjs";
import { selectCollectorAppealBreakdown } from "./collectorAppealBreakdownSelector.mjs";
import { RIP_SUMMARY_DESCRIPTIONS } from "./OverviewRipSummary.jsx";

const UNAVAILABLE_DASH = "—";

// One accent family per metric, matching the approved direction: gold for the
// headline, blue/cyan for money, purple/magenta for appeal. These are the only
// three families used on this page, and no card gets a colour of its own.
export const INSIGHTS_SUMMARY_ACCENTS = {
  overall: "250,204,21",
  financial: "56,189,248",
  collector: "192,132,252",
};

function toDisplayScore(value) {
  return value === null || value === undefined || value === "" || Number.isNaN(Number(value))
    ? null
    : Number(value).toFixed(1);
}

function toRailPercent(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return null;
  }
  return Math.max(0, Math.min(100, parsed));
}

/**
 * The rank / tier / cohort line, assembled from backend values only. Returns
 * null when the backend ranked nothing, so the card shows no empty metadata
 * strip rather than a lone separator.
 */
function formatMeta({ tier, rank, cohortSize }) {
  const parts = [];
  if (tier && tier !== UNAVAILABLE_DASH) parts.push(`${tier} Tier`);
  if (rank !== null && rank !== undefined) {
    parts.push(cohortSize ? `Rank #${rank} of ${cohortSize}` : `Rank #${rank}`);
  }
  return parts.length > 0 ? parts.join(" · ") : null;
}

/**
 * THE ELEVATED RAIL. This treatment exists on exactly three elements on the
 * page — one per summary card — and is deliberately not exported to the
 * breakdown rows, which use the quiet rail in RipMetricDisclosureRow.
 *
 * The glow is a gradual left-to-right bloom: the fill starts nearly flat and
 * gains luminance toward its leading edge, with a soft shadow in the same hue.
 * It is a single shadow at low alpha, not a neon outline, and it is absent
 * entirely when there is no value to draw. Zero is a real relative score for
 * the lowest-ranked cohort member, so 0% is available even though its fill has
 * zero width.
 */
function SummaryRail({ accent, percent }) {
  const hasValue =
    percent !== null && percent !== undefined && Number.isFinite(Number(percent));
  return (
    <div
      data-insights-summary-rail
      data-rail-emphasis="elevated"
      data-rail-available={hasValue ? "true" : "false"}
      className="relative mt-2.5 h-1.5 w-full overflow-hidden rounded-full bg-[rgba(255,255,255,0.06)]"
    >
      {hasValue ? (
        <div
          className="relative h-full rounded-full"
          style={{
            width: `${percent}%`,
            background: `linear-gradient(90deg, rgba(${accent},0.14) 0%, rgba(${accent},0.42) 45%, rgba(${accent},0.72) 78%, rgba(${accent},0.94) 100%)`,
            boxShadow: `0 0 10px 0 rgba(${accent},0.26), inset 0 1px 0 rgba(255,255,255,0.10)`,
          }}
        >
          <span
            aria-hidden="true"
            className="absolute right-0 top-1/2 h-1.5 w-1.5 -translate-y-1/2 rounded-full"
            style={{
              background: `rgba(${accent},0.95)`,
              boxShadow: `0 0 6px rgba(${accent},0.45)`,
            }}
          />
        </div>
      ) : null}
    </div>
  );
}

function SummaryCard({ id, label, score, meta, description, available, accent, railPercent, badges = null }) {
  return (
    <div
      data-insights-summary-metric={id}
      data-insights-summary-accent={id}
      className="min-w-0 flex-1 rounded-xl border border-[var(--border-subtle)] bg-[rgba(255,255,255,0.018)] p-3 desk:p-3.5"
    >
      <p className="text-[10px] font-semibold uppercase tracking-[0.09em] text-[var(--text-secondary)]">
        {label}
      </p>
      <div className="mt-1 flex min-w-0 flex-wrap items-end gap-x-2 gap-y-1">
        <p className="inline-flex items-end gap-1 text-2xl font-semibold leading-none tabular-nums text-[var(--text-primary)] desk:text-[28px]">
          {/* An unavailable metric prints an em dash. It never falls back to a
              legacy score, to the other metrics, or to zero. */}
          <span data-insights-summary-score>{available ? score : UNAVAILABLE_DASH}</span>
          {available ? (
            <span className="pb-0.5 text-[10px] font-medium text-[var(--text-secondary)]">/100</span>
          ) : null}
        </p>
        {available && badges ? <span className="min-w-0">{badges}</span> : null}
      </div>

      <SummaryRail accent={accent} percent={available ? railPercent : null} />

      {available && meta ? (
        <p className="mt-2 text-[11px] font-medium tabular-nums text-[var(--text-secondary)]">{meta}</p>
      ) : null}
      <p className="mt-1 text-[11px] leading-relaxed text-[var(--text-secondary)]">
        {available ? description : "Not available for this set yet."}
      </p>
    </div>
  );
}

/**
 * `canonical` is the page's ONE already-resolved bundle — the same object the
 * hero, Financial RIP and Collector Appeal read. This module resolves no
 * sources of its own, so Insights cannot show a different number from Overview
 * for the same set.
 *
 * The Overall RIP values are HANDED IN rather than re-derived. The page already
 * resolves them once through selectRipHeroScoreMode and renders them in the
 * sticky hero; resolving them a second time here would let the Insights
 * headline disagree with the header for the same set. `overallBadges` is the
 * page's existing HeroScoreBadges element, passed verbatim for the same reason.
 */
export default function InsightsSummaryModule({
  canonical,
  overallScore = null,
  overallTier = null,
  overallRank = null,
  overallCohortSize = null,
  overallBadges = null,
}) {
  const financial = useMemo(
    () => selectFinancialRipV3Breakdown(resolveCanonicalFinancialRip(canonical)),
    [canonical]
  );
  const collector = useMemo(() => selectCollectorAppealBreakdown(canonical), [canonical]);

  const overallDisplayScore = toDisplayScore(overallScore);
  const financialScore = toDisplayScore(financial.publicScore);
  const collectorScore = toDisplayScore(collector.publicScore);

  return (
    <section
      data-insights-summary
      aria-labelledby="set-detail-insights-summary-heading"
      className="mt-3 min-w-0 rounded-2xl border border-[var(--border-subtle)] bg-[rgba(255,255,255,0.012)] p-3 desk:p-4"
    >
      <h3
        id="set-detail-insights-summary-heading"
        className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--text-secondary)]"
      >
        Insights Summary
      </h3>

      {/* ONE grouped surface. Three cards in a row at 1200px+, a compact stack
          below it. Each card is min-w-0 so a long rank line wraps instead of
          forcing the page to scroll horizontally. */}
      <div
        data-insights-summary-cards
        className="mt-2.5 grid min-w-0 grid-cols-1 gap-2.5 desk:grid-cols-3 desk:gap-3"
      >
        <SummaryCard
          id="overall"
          label="RIP Score"
          // The PUBLIC Overall RIP number is the cohort-relative score. The
          // absolute blend is never promoted into this headline.
          score={overallDisplayScore}
          available={overallDisplayScore !== null}
          meta={formatMeta({ tier: overallTier, rank: overallRank, cohortSize: overallCohortSize })}
          description={RIP_SUMMARY_DESCRIPTIONS.overall}
          accent={INSIGHTS_SUMMARY_ACCENTS.overall}
          railPercent={toRailPercent(overallScore)}
          badges={overallBadges}
        />
        <SummaryCard
          id="financial"
          label="Financial RIP"
          // Financial RIP uses its backend cohort-relative public score.
          score={financialScore}
          available={financial.publicAvailable && financialScore !== null}
          meta={formatMeta({
            tier: financial.tier,
            rank: financial.rank,
            cohortSize: financial.rankedSetCount,
          })}
          description={RIP_SUMMARY_DESCRIPTIONS.financial}
          accent={INSIGHTS_SUMMARY_ACCENTS.financial}
          railPercent={toRailPercent(financial.publicScore)}
        />
        <SummaryCard
          id="collector"
          label="Collector Appeal"
          // Collector Appeal follows the same relative public-score policy.
          score={collectorScore}
          available={collector.publicAvailable && collectorScore !== null}
          meta={formatMeta({
            tier: collector.tier,
            rank: collector.rank,
            cohortSize: collector.rankedSetCount,
          })}
          description={RIP_SUMMARY_DESCRIPTIONS.collector}
          accent={INSIGHTS_SUMMARY_ACCENTS.collector}
          railPercent={toRailPercent(collector.publicScore)}
        />
      </div>
    </section>
  );
}
