"use client";

// The Overview "RIP Summary": three canonical metrics, one grouped surface.
//
// WHAT IT REPLACES
// ----------------
// The Overview's quick explanation used to be the Decision Signals card, which
// scored Profit, Safety, Stability, Opening Experience and Chase Potential —
// five lenses of the retired Financial RIP V2 / interpretation-engine model. It
// was removed, and Overview has since had no compact answer to "how does this
// set score". This module is that answer, stated in the CURRENT model's terms.
//
// EXACTLY THREE METRICS
// ---------------------
//   RIP Score        the canonical Overall RIP V7 headline
//   Financial RIP    the canonical Financial RIP V3 score
//   Collector Appeal the canonical Collector Appeal V3 score
//
// No Profit, no Safety, no Stability, no Opening Experience, no Chase
// Potential, no weights, no formula, no contribution, no version label and no
// interpretation copy. Each metric gets one plain sentence saying what it
// measures, and nothing that reads as advice.
//
// ONE PUBLIC SCORE SCALE
// ----------------------
// RIP Score, Financial RIP and Collector Appeal all show their canonical
// `publicScore`: the backend cohort-relative 0-100 value, on `/100`, to one
// decimal. Their fixed-anchor model scores remain in the payload for
// formula/audit use and are never substituted into a public headline. Rank,
// tier and cohort remain backend-provided in every case.
//
// The same three numbers appear in the "Why It Ranks" block further down this
// same tab (RipDecisionPage) and in the Insights summary on the next tab. All
// three surfaces read this same canonical bundle through the same selectors, so
// they cannot disagree.
//
// NOTHING IS COMPUTED HERE. Every number is lifted from the resolved canonical
// bundle, and a missing relative score renders as an explicit unavailable state
// — never a zero, never a legacy score, never an absolute score on another
// scale.

import React, { useMemo } from "react";

import InfoPopover from "@/components/ui/InfoPopover";
import {
  PUBLIC_SCORE_SCALE_NOTE,
  readCanonicalBlock,
  resolveCanonicalRipV7,
} from "./canonicalRipV7.mjs";
import { resolveCanonicalFinancialRip, selectFinancialRipV3Breakdown } from "./financialRipV3Selector.mjs";
import { selectCollectorAppealBreakdown } from "./collectorAppealBreakdownSelector.mjs";

const UNAVAILABLE_DASH = "—";

// One neutral sentence each. Factual about WHAT is measured; silent on whether
// the number is good.
export const RIP_SUMMARY_DESCRIPTIONS = {
  overall: "Financial opening performance with collector appeal.",
  financial: "Monetary pack outcomes compared with pack cost.",
  collector: "Roster desirability and how often the pack can deliver it.",
};

function toDisplayScore(value) {
  return value === null || value === undefined || value === "" || Number.isNaN(Number(value))
    ? null
    : Number(value).toFixed(1);
}

/**
 * The rank / tier / cohort line, assembled from backend values only. Returns
 * null when the backend ranked nothing, so the row shows no empty metadata
 * strip rather than a lone separator.
 */
function formatMeta({ tier, rank, cohortSize }) {
  const parts = [];
  if (tier) parts.push(`${tier} Tier`);
  if (rank !== null && rank !== undefined) {
    parts.push(cohortSize ? `Rank #${rank} of ${cohortSize}` : `Rank #${rank}`);
  }
  return parts.length > 0 ? parts.join(" · ") : null;
}

function SummaryMetric({ id, label, score, meta, description, available }) {
  return (
    <div data-rip-summary-metric={id} className="min-w-0 flex-1">
      <p className="text-[10px] font-semibold uppercase tracking-[0.09em] text-[var(--text-secondary)]">
        {label}
      </p>
      <p className="mt-1 inline-flex items-end gap-1 text-2xl font-semibold leading-none tabular-nums text-[var(--text-primary)]">
        {/* An unavailable metric prints an em dash. It never falls back to a
            legacy score, to the other metrics, or to zero. */}
        <span data-rip-summary-score>{available ? score : UNAVAILABLE_DASH}</span>
        {available ? (
          <span className="pb-0.5 text-[10px] font-medium text-[var(--text-secondary)]">/100</span>
        ) : null}
      </p>
      {available && meta ? (
        <p className="mt-1 text-[11px] font-medium tabular-nums text-[var(--text-secondary)]">{meta}</p>
      ) : null}
      <p className="mt-1 text-[11px] leading-relaxed text-[var(--text-secondary)]">
        {available ? description : "Not available for this set yet."}
      </p>
    </div>
  );
}

/**
 * `canonical` is the page's ONE already-resolved bundle, the same object the
 * hero, the Insights headline, Financial RIP and Collector Appeal read. This
 * module resolves no sources of its own, so Overview cannot show a different
 * number from Insights for the same set.
 *
 * `onViewAnalysis` is the page's own set-detail navigation handler. It is a
 * CALLBACK rather than an <a href>: this is same-set tab navigation, which the
 * set page routes through handleSetDetailNavSelect (tab state + router.push +
 * scroll) — a plain link would bypass that and reload the whole page.
 */
export default function OverviewRipSummary({ canonical, onViewAnalysis = null }) {
  const overall = useMemo(
    () => readCanonicalBlock(resolveCanonicalRipV7(canonical).overall),
    [canonical]
  );
  const financial = useMemo(
    () => selectFinancialRipV3Breakdown(resolveCanonicalFinancialRip(canonical)),
    [canonical]
  );
  const collector = useMemo(() => selectCollectorAppealBreakdown(canonical), [canonical]);

  const financialScore = toDisplayScore(financial.publicScore);
  const collectorScore = toDisplayScore(collector.publicScore);

  return (
    <section
      data-rip-summary
      aria-labelledby="set-detail-rip-summary-heading"
      className="set-glass-surface min-w-0 rounded-2xl border p-4 max-desk:rounded-none max-desk:border-0 max-desk:bg-transparent max-desk:p-0 max-desk:shadow-none max-desk:[backdrop-filter:none]"
    >
      <div className="flex min-w-0 flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <div className="flex min-w-0 items-center gap-1.5">
          <h2
            id="set-detail-rip-summary-heading"
            className="text-sm font-semibold text-[var(--text-primary)]"
          >
            RIP Summary
          </h2>
          {/* The scale, in product language, behind the existing InfoPopover
              pattern. The normalization formula itself belongs in Research —
              never in a metric label. */}
          <InfoPopover text={PUBLIC_SCORE_SCALE_NOTE} />
        </div>
        {/* One restrained action, not a button per metric. */}
        {onViewAnalysis ? (
          <button
            type="button"
            onClick={onViewAnalysis}
            data-rip-summary-analysis-link
            className="rounded text-[11px] font-medium text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
          >
            View analysis
          </button>
        ) : null}
      </div>

      {/* ONE grouped surface. Three columns of a single card on desktop, and a
          compact stack of rows below it — not three nested glass cards, which
          is what made the retired Decision Signals block dominate Overview. */}
      <div className="mt-3 flex min-w-0 flex-col gap-3 desk:flex-row desk:gap-6 desk:divide-x desk:divide-[var(--border-subtle)]">
        <SummaryMetric
          id="overall"
          label="Overall RIP"
          // THE canonical public value. The fixed-anchor 90/10 blend is never
          // promoted into this headline.
          score={toDisplayScore(overall.publicScore)}
          available={overall.available}
          meta={formatMeta({ tier: overall.tier, rank: overall.rank, cohortSize: overall.cohortSize })}
          description={RIP_SUMMARY_DESCRIPTIONS.overall}
        />
        <div className="min-w-0 flex-1 desk:pl-6">
          <SummaryMetric
            id="financial"
            label="Financial RIP"
            // Financial RIP uses the backend relative 0-100 score, matching
            // the public scoring language used by Overall RIP.
            score={financialScore}
            available={financial.publicAvailable && financialScore !== null}
            meta={formatMeta({
              tier: financial.tier && financial.tier !== UNAVAILABLE_DASH ? financial.tier : null,
              rank: financial.rank,
              cohortSize: financial.rankedSetCount,
            })}
            description={RIP_SUMMARY_DESCRIPTIONS.financial}
          />
        </div>
        <div className="min-w-0 flex-1 desk:pl-6">
          <SummaryMetric
            id="collector"
            label="Collector Appeal"
            // Collector Appeal follows the same relative public score policy.
            score={collectorScore}
            available={collector.publicAvailable && collectorScore !== null}
            meta={formatMeta({
              tier: collector.tier,
              rank: collector.rank,
              cohortSize: collector.rankedSetCount,
            })}
            description={RIP_SUMMARY_DESCRIPTIONS.collector}
          />
        </div>
      </div>
    </section>
  );
}
