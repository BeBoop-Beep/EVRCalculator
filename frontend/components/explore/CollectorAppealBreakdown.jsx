"use client";

// The canonical Overall RIP composition (80/20) and the Collector Appeal
// breakdown (D / F / P).
//
// SCOPE
// -----
// Additive. No restyle: this reuses the existing visual language verbatim -
// `set-glass-surface`, the same CSS custom properties, the same radii, the same
// type scale and the same `max-desk:` mobile-feed treatment as the surrounding
// sections. It introduces no new colour, radius or font size.
//
// WHAT IT SHOWS
// -------------
//   Overall RIP = 80% Financial RIP + 20% Collector Appeal
//   Collector Appeal = Roster Desirability, Desirable Outcome Frequency,
//                      Dual-Path Depth
//
// Both source scores and both contributions are rendered, because a composition
// a reader cannot check is decoration.
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
  formatWeightPercent,
  selectCollectorAppealBreakdown,
  selectOverallRipComposition,
} from "./collectorAppealBreakdownSelector.mjs";

function MetricRow({ label, value }) {
  return (
    <div className="flex min-w-0 items-baseline justify-between gap-3">
      <dt className="min-w-0 text-xs text-[var(--text-secondary)]">{label}</dt>
      <dd className="flex-none text-xs font-semibold tabular-nums text-[var(--text-primary)]">{value}</dd>
    </div>
  );
}

function CompositionRow({ row }) {
  return (
    <article
      data-overall-composition-term={row.key}
      className="set-glass-surface min-w-0 rounded-xl border p-3.5 max-desk:rounded-none max-desk:border-0 max-desk:border-b max-desk:bg-transparent max-desk:px-0 max-desk:shadow-none max-desk:[backdrop-filter:none]"
    >
      <div className="flex min-w-0 items-start justify-between gap-3">
        <h4 className="min-w-0 text-sm font-semibold text-[var(--text-primary)]">{row.title}</h4>
        {/* The weight IS shown here, unlike on the six financial component
            cards: this block's entire subject is how the two halves combine,
            so hiding the split would remove the point of the section. */}
        <span className="flex-none rounded-md bg-[var(--surface-page)]/55 px-2 py-0.5 text-[11px] font-semibold tabular-nums text-[var(--text-secondary)]">
          {formatWeightPercent(row.weight)}
        </span>
      </div>
      <p className="mt-1.5 inline-flex items-end gap-1 text-2xl font-semibold leading-none tabular-nums text-[var(--text-primary)]">
        {row.score === null ? "—" : row.score.toFixed(1)}
        <span className="pb-0.5 text-[11px] font-medium text-[var(--text-secondary)]">/100</span>
      </p>
      <p className="mt-1 text-[11px] tabular-nums text-[var(--text-secondary)]">
        Contributes {row.contribution === null ? "—" : row.contribution.toFixed(2)} points
      </p>
      <p className="mt-2 text-xs leading-relaxed text-[var(--text-secondary)]">{row.interpretation}</p>
    </article>
  );
}

function AppealInputCard({ row }) {
  return (
    <article
      data-collector-appeal-input={row.key}
      className="set-glass-surface min-w-0 rounded-xl border p-3.5 max-desk:rounded-none max-desk:border-0 max-desk:border-b max-desk:bg-transparent max-desk:px-0 max-desk:shadow-none max-desk:[backdrop-filter:none]"
    >
      <div className="flex min-w-0 items-start justify-between gap-3">
        <h4 className="min-w-0 text-sm font-semibold text-[var(--text-primary)]">{row.title}</h4>
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

export default function CollectorAppealBreakdown({
  publicRipContractV6,
  overallRipV6,
  openingExperience,
}) {
  const sources = { publicRipContractV6, overallRipV6, openingExperience };
  const composition = useMemo(() => selectOverallRipComposition(sources), [
    publicRipContractV6,
    overallRipV6,
    openingExperience,
  ]);
  const appeal = useMemo(() => selectCollectorAppealBreakdown(sources), [
    publicRipContractV6,
    overallRipV6,
    openingExperience,
  ]);

  return (
    <section data-overall-rip-composition-v6 className="min-w-0">
      <div className="min-w-0">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">How Overall RIP is built</h3>
        <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
          Overall RIP = 80% Financial RIP + 20% Collector Appeal
        </p>
      </div>

      {composition.available ? (
        <div className="mt-3 grid min-w-0 gap-3 desk:grid-cols-2">
          {composition.rows.map((row) => (
            <CompositionRow key={row.key} row={row} />
          ))}
        </div>
      ) : (
        <div className="mt-3 min-w-0 rounded-xl border border-dashed border-[var(--border-subtle)] p-4">
          <p className="text-sm font-medium text-[var(--text-primary)]">
            Overall RIP is not available for this set yet.
          </p>
          {composition.statusReason ? (
            <p className="mt-1.5 text-xs leading-relaxed text-[var(--text-secondary)]">
              {composition.statusReason}
            </p>
          ) : null}
        </div>
      )}

      {/* The distinction, stated once and near both numbers. */}
      <p data-financial-collector-distinction className="mt-3 text-[11px] leading-relaxed text-[var(--text-secondary)]">
        {FINANCIAL_VS_COLLECTOR_NOTE}
      </p>

      <div className="mt-5 min-w-0">
        <div className="flex min-w-0 flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">Collector Appeal</h3>
          {appeal.available ? (
            <p className="text-[11px] tabular-nums text-[var(--text-secondary)]">
              {appeal.scoreLabel}/100
              {appeal.rank !== null ? ` · Rank #${appeal.rank}` : ""}
              {appeal.rankedSetCount ? ` of ${appeal.rankedSetCount}` : ""}
            </p>
          ) : null}
        </div>

        {appeal.available ? (
          <div className="mt-3 grid min-w-0 gap-3 desk:grid-cols-3">
            {appeal.rows.map((row) => (
              <AppealInputCard key={row.key} row={row} />
            ))}
          </div>
        ) : (
          <div className="mt-3 min-w-0 rounded-xl border border-dashed border-[var(--border-subtle)] p-4">
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
      </div>
    </section>
  );
}
