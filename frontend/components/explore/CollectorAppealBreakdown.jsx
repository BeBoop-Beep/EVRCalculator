"use client";

// The canonical Collector Appeal V3 section: one score, three parallel factors.
//
// SCOPE
// -----
// No restyle: this reuses the existing visual language verbatim -
// `set-glass-surface`, the same CSS custom properties, the same radii, the same
// type scale and the same `max-desk:` mobile-feed treatment as the surrounding
// sections. It introduces no new colour, radius or font size.
//
// WHAT IT SHOWS
// -------------
//   Collector Appeal, explained by Roster Desirability, Desirable Outcome
//   Frequency and Dual-Path Depth — three factors, side by side.
//
// WHAT IT NO LONGER SHOWS, AND WHY
// --------------------------------
//   - "How Overall RIP is built" and "Overall RIP = 80% Financial RIP + 20%
//     Collector Appeal". The split was wrong (the canonical model is 90/10) and
//     the section was reading Collector Appeal V2 to fill it.
//   - The per-term weight pills and "Contributes N points". Collector Appeal
//     V3's arithmetic is a one-line weighted sum, so a published weight vector
//     or a published contribution IS the formula. The backend withholds both
//     (`weightsDisclosed: false`) and this surface must not reconstruct them.
//   - The sequential chain Set Desirability -> Collector Appeal -> RIP Score
//     Contribution. The three factors combine in one step; arrows claimed a
//     pipeline the model does not have.
//
// THE ONE COPY RULE THIS FILE ENFORCES
// ------------------------------------
// Desirable Outcome Frequency is never presented as a financial result. It sits
// under Collector Appeal, it is labelled by its own name, and it carries the
// disclaimer that a desirable outcome can still be worth less than the pack
// price. Financial RIP's six components are untouched and stay exactly six -
// F is NOT a seventh financial component.

import { useMemo } from "react";

import {
  FINANCIAL_VS_COLLECTOR_NOTE,
  selectCollectorAppealBreakdown,
} from "./collectorAppealBreakdownSelector.mjs";

function MetricRow({ label, value }) {
  return (
    <div className="flex min-w-0 items-baseline justify-between gap-3">
      <dt className="min-w-0 text-xs text-[var(--text-secondary)]">{label}</dt>
      <dd className="flex-none text-xs font-semibold tabular-nums text-[var(--text-primary)]">{value}</dd>
    </div>
  );
}

function AppealFactorCard({ row }) {
  return (
    <article
      data-collector-appeal-factor={row.key}
      className="set-glass-surface min-w-0 rounded-xl border p-3.5 max-desk:rounded-none max-desk:border-0 max-desk:border-b max-desk:bg-transparent max-desk:px-0 max-desk:shadow-none max-desk:[backdrop-filter:none]"
    >
      <div className="flex min-w-0 items-start justify-between gap-3">
        <h4 className="min-w-0 text-sm font-semibold text-[var(--text-primary)]">{row.title}</h4>
        {/* Missing data arrives from the selector as an em dash and renders as
            such — never as 0, and never as another factor's value. */}
        <p className="flex-none text-lg font-semibold leading-none tabular-nums text-[var(--text-primary)]">
          {row.value}
        </p>
      </div>
      <p className="mt-2 text-xs leading-relaxed text-[var(--text-secondary)]">{row.interpretation}</p>
      {row.disclaimer ? (
        // Rendered next to the number, not buried in a tooltip: this is the one
        // sentence that stops a probability under an appeal heading from being
        // read as a promise about money.
        <p
          data-desirable-outcome-disclaimer
          className="mt-1.5 text-[11px] italic leading-relaxed text-[var(--text-secondary)]"
        >
          {row.disclaimer}
        </p>
      ) : null}
      {row.metrics.length > 0 ? (
        <dl className="mt-2.5 space-y-1.5 border-t border-[var(--border-subtle)] pt-2.5">
          {row.metrics.map((metric) => (
            <MetricRow key={metric.label} label={metric.label} value={metric.value} />
          ))}
        </dl>
      ) : null}
      {!row.available && row.statusReason ? (
        <p className="mt-2 text-[11px] text-[var(--text-secondary)]">{row.statusReason}</p>
      ) : null}
    </article>
  );
}

// `canonical` is the ALREADY-RESOLVED bundle from resolveCanonicalRipV7, owned
// by the set page and shared with the hero, the Overview summary and Financial
// RIP. This component deliberately takes no raw sources: when it resolved its
// own `publicRipContractV7`/`overallRipV7` props it could land on a different
// source than the hero did, which is the exact split this pass removes.
export default function CollectorAppealBreakdown({ canonical }) {
  const appeal = useMemo(() => selectCollectorAppealBreakdown(canonical), [canonical]);

  return (
    <section data-collector-appeal-v3 className="min-w-0">
      <div className="flex min-w-0 flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">Collector Appeal</h3>
        {appeal.available ? (
          <p className="text-[11px] tabular-nums text-[var(--text-secondary)]">
            {appeal.scoreLabel}/100
            {appeal.tier ? ` · ${appeal.tier} Tier` : ""}
            {appeal.rank !== null ? ` · Rank #${appeal.rank}` : ""}
            {appeal.rankedSetCount ? ` of ${appeal.rankedSetCount}` : ""}
          </p>
        ) : null}
      </div>
      <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
        How desirable the modeled cards are, and how often the pack can deliver one.
      </p>

      {appeal.available ? (
        // Three parallel factors. A grid, not a flow: no arrows, no numbered
        // stages, nothing that reads as one factor feeding the next.
        <div className="mt-3 grid min-w-0 gap-3 desk:grid-cols-3">
          {appeal.rows.map((row) => (
            <AppealFactorCard key={row.key} row={row} />
          ))}
        </div>
      ) : (
        // A precise unavailable state. It does NOT render Collector Appeal V2,
        // legacy CA7 or Roster Desirability in its place, and it does not
        // render zeros.
        <div
          data-collector-appeal-unavailable
          className="mt-3 min-w-0 rounded-xl border border-dashed border-[var(--border-subtle)] p-4"
        >
          <p className="text-sm font-medium text-[var(--text-primary)]">
            Collector Appeal is not available for this set yet.
          </p>
          {appeal.statusReason ? (
            <p className="mt-1.5 text-xs leading-relaxed text-[var(--text-secondary)]">
              {appeal.statusReason}
            </p>
          ) : null}
        </div>
      )}

      {/* Not rendered as a zero score. An unmodeled subject type is absent
          from the model, which is a different statement from "not desirable". */}
      <p data-collector-appeal-subject-scope className="mt-2.5 text-[11px] leading-relaxed text-[var(--text-secondary)]">
        {appeal.subjectScope.note}
      </p>

      {/* The distinction, stated once and near both numbers. */}
      <p data-financial-collector-distinction className="mt-1.5 text-[11px] leading-relaxed text-[var(--text-secondary)]">
        {FINANCIAL_VS_COLLECTOR_NOTE}
      </p>
    </section>
  );
}
