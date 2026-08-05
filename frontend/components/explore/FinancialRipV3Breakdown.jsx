"use client";

// The Financial RIP breakdown surface: six canonical V3 component cards and the
// unweighted Depth and Robustness panel.
//
// SCOPE
// -----
// No restyle: this reuses the existing visual language verbatim - the same
// `set-glass-surface`, CSS custom properties, border radii, type scale and
// `max-desk:` mobile-feed treatment as the surrounding sections. Nothing here
// introduces a new colour, radius or font size.
//
// LABELLING
// ---------
// "Financial RIP" means Financial RIP V3, and there is nothing else to choose
// between. The former `Current V3 / Legacy V2` toggle is gone: it presented the
// retired 60/25/15 Profit/Safety/Stability model as a live alternative on a
// public page, and its "90% of Overall RIP" subheading published a composition
// weight the page has no reason to state. Legacy V2 is still computed and still
// persisted on the backend for audit and rollback; it is simply not a public
// presentation any more. No version number appears in user-facing copy.

import { useMemo } from "react";

import {
  resolveCanonicalFinancialRip,
  selectDepthAndRobustness,
  selectFinancialRipV3Breakdown,
} from "./financialRipV3Selector.mjs";

function MetricRow({ label, value }) {
  return (
    <div className="flex min-w-0 items-baseline justify-between gap-3">
      <dt className="min-w-0 text-xs text-[var(--text-secondary)]">{label}</dt>
      {/* `tabular-nums` so a column of dollar values does not jitter between
          sets. Missing data arrives from the selector as an em dash and is
          rendered as such — never as 0. */}
      <dd className="flex-none text-xs font-semibold tabular-nums text-[var(--text-primary)]">{value}</dd>
    </div>
  );
}

function V3ComponentCard({ row }) {
  return (
    <article
      data-v3-component={row.key}
      className="set-glass-surface min-w-0 rounded-xl border p-3.5 max-desk:rounded-none max-desk:border-0 max-desk:border-b max-desk:bg-transparent max-desk:px-0 max-desk:shadow-none max-desk:[backdrop-filter:none]"
    >
      <div className="flex min-w-0 items-start justify-between gap-3">
        <h4 className="min-w-0 text-sm font-semibold text-[var(--text-primary)]">{row.title}</h4>
        <p className="flex-none items-end text-lg font-semibold leading-none tabular-nums text-[var(--text-primary)]">
          {row.scoreLabel}
          <span className="pl-0.5 text-[10px] font-medium text-[var(--text-secondary)]">/100</span>
        </p>
      </div>

      {row.rankValue !== null && row.rankValue !== undefined ? (
        <p className="mt-1 text-[11px] font-medium text-[var(--text-secondary)]">
          Rank #{row.rankValue}
          {row.cohortSize ? ` of ${row.cohortSize}` : ""}
          {row.rankTier ? ` · Tier ${row.rankTier}` : ""}
        </p>
      ) : (
        <p className="mt-1 text-[11px] font-medium text-[var(--text-secondary)]">{row.rankDiagnostic}</p>
      )}

      <p className="mt-2 text-xs leading-relaxed text-[var(--text-secondary)]">{row.interpretation}</p>

      <dl className="mt-2.5 space-y-1.5 border-t border-[var(--border-subtle)] pt-2.5">
        {row.metrics.map((metric) => (
          <MetricRow key={metric.label} label={metric.label} value={metric.value} />
        ))}
      </dl>
    </article>
  );
}

function DepthAndRobustnessPanel({ diagnostic }) {
  if (!diagnostic.available) {
    return (
      <section
        data-depth-and-robustness
        className="mt-4 min-w-0 rounded-xl border border-dashed border-[var(--border-subtle)] p-3.5"
      >
        <h3 className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
          Depth and Robustness
        </h3>
        <p className="mt-1.5 text-xs text-[var(--text-secondary)]">
          {diagnostic.statusReason || "Not available for this set yet."}
        </p>
      </section>
    );
  }

  return (
    <section
      data-depth-and-robustness
      className="mt-4 min-w-0 rounded-xl border border-[var(--border-subtle)] p-3.5"
    >
      <div className="flex min-w-0 flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h3 className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
          Depth and Robustness
        </h3>
        {/* Said in the UI, not only in the code: this panel is a diagnostic, so
            a reader does not count it as a seventh scored component. */}
        <p className="text-[11px] text-[var(--text-secondary)]">
          Context only — not part of the Financial RIP score
        </p>
      </div>
      {diagnostic.concentrationLabel ? (
        <p className="mt-1.5 text-sm font-semibold text-[var(--text-primary)]">
          {diagnostic.concentrationLabel}
        </p>
      ) : null}
      <dl className="mt-2.5 grid gap-x-6 gap-y-1.5 desk:grid-cols-2">
        {diagnostic.rows.map((row) => (
          <MetricRow key={row.key} label={row.label} value={row.value} />
        ))}
      </dl>
    </section>
  );
}

export default function FinancialRipV3Breakdown({ publicRipContractV7, overallRipV7, financialRipV3, requestTimeout = false }) {
  // One canonical resolution, shared with every other V7 surface. The caller
  // may pass the packaged contract, the top-level V3 object, or both.
  const canonical = useMemo(
    () => resolveCanonicalFinancialRip({ publicRipContractV7, overallRipV7, financialRipV3 }),
    [financialRipV3, overallRipV7, publicRipContractV7]
  );
  const v3 = useMemo(
    () => selectFinancialRipV3Breakdown(canonical, { requestTimeout }),
    [canonical, requestTimeout]
  );
  const depth = useMemo(() => selectDepthAndRobustness(canonical), [canonical]);

  return (
    <section data-financial-rip-breakdown="v3" className="min-w-0">
      <div className="min-w-0">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">Financial RIP</h3>
        <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
          Built from the simulated pack-value distribution and the pack price.
        </p>
      </div>

      {v3.diagnostics.status === "ready" ? (
        <>
          <div className="mt-3 grid min-w-0 gap-3 desk:grid-cols-2 xl:grid-cols-3">
            {v3.rows.map((row) => (
              <V3ComponentCard key={row.key} row={row} />
            ))}
          </div>
          <DepthAndRobustnessPanel diagnostic={depth} />
        </>
      ) : (
        // A precise unavailable state. It does NOT render Financial RIP V2
        // numbers under this heading, and it does not render zeros.
        <div
          data-v3-unavailable
          className="mt-3 min-w-0 rounded-xl border border-dashed border-[var(--border-subtle)] p-4"
        >
          <p className="text-sm font-medium text-[var(--text-primary)]">
            {v3.diagnostics.status === "loading"
              ? "Loading Financial RIP…"
              : "Financial RIP is not available for this set yet."}
          </p>
          {v3.diagnostics.statusDetail ? (
            <p className="mt-1.5 text-xs leading-relaxed text-[var(--text-secondary)]">
              {v3.diagnostics.statusDetail}
            </p>
          ) : null}
        </div>
      )}
    </section>
  );
}
