"use client";

// The Financial RIP V3 breakdown surface: six component cards, the unweighted
// Depth and Robustness panel, and the Current V3 / Legacy V2 model toggle.
//
// SCOPE
// -----
// This is an ADDITIVE surface. It does not restyle the page, does not touch the
// hero, and reuses the existing visual language verbatim: `set-glass-surface`,
// the same CSS custom properties, the same border radii, the same type scale,
// and the same `max-desk:` mobile-feed treatment the surrounding sections use.
// Nothing here introduces a new colour, a new radius or a new font size.
//
// LABELLING
// ---------
// After the V3 cutover, "Financial RIP" means V3. The legacy model is labelled
// `Legacy V2` everywhere it appears and is never called just "Financial RIP".
// The toggle deliberately does not present the two as co-equal: one is
// `Current V3` and is the default, the other is explicitly legacy.

import { useMemo, useState } from "react";

import {
  selectDepthAndRobustness,
  selectFinancialRipV3Breakdown,
} from "./financialRipV3Selector.mjs";
import { selectRipScoreBreakdown } from "./ripScoreBreakdownSelector.mjs";

export const FINANCIAL_RIP_MODEL_MODES = {
  V3: "current_v3",
  V2: "legacy_v2",
};

function ModelToggle({ value, onChange, legacyAvailable }) {
  const options = [
    { id: FINANCIAL_RIP_MODEL_MODES.V3, label: "Current V3", enabled: true },
    { id: FINANCIAL_RIP_MODEL_MODES.V2, label: "Legacy V2", enabled: legacyAvailable },
  ];
  return (
    <div
      role="radiogroup"
      aria-label="Financial RIP model"
      className="inline-flex flex-none items-center gap-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 p-0.5"
    >
      {options.map((option) => {
        const active = value === option.id;
        return (
          <button
            key={option.id}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={!option.enabled}
            onClick={() => option.enabled && onChange(option.id)}
            className={`rounded-md px-2.5 py-1 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]/55 ${
              active
                ? "bg-[var(--surface-hover)] text-[var(--text-primary)]"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            } ${option.enabled ? "" : "cursor-not-allowed opacity-40"}`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

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

function LegacyV2Cards({ rows }) {
  return (
    <div className="grid min-w-0 gap-3 desk:grid-cols-3">
      {rows.map((row) => (
        <article
          key={row.key}
          data-v2-pillar={row.key}
          className="set-glass-surface min-w-0 rounded-xl border p-3.5 max-desk:rounded-none max-desk:border-0 max-desk:border-b max-desk:bg-transparent max-desk:px-0 max-desk:shadow-none max-desk:[backdrop-filter:none]"
        >
          <div className="flex min-w-0 items-start justify-between gap-3">
            <h4 className="min-w-0 text-sm font-semibold text-[var(--text-primary)]">{row.title}</h4>
            <p className="flex-none text-lg font-semibold leading-none tabular-nums text-[var(--text-primary)]">
              {row.score === null || row.score === undefined ? "—" : row.score.toFixed(1)}
              <span className="pl-0.5 text-[10px] font-medium text-[var(--text-secondary)]">/100</span>
            </p>
          </div>
          <p className="mt-1 text-[11px] font-medium text-[var(--text-secondary)]">
            {row.rankValue !== null && row.rankValue !== undefined
              ? `Rank #${row.rankValue}${row.cohortSize ? ` of ${row.cohortSize}` : ""}${
                  row.rankTier ? ` · Tier ${row.rankTier}` : ""
                }`
              : row.rankDiagnostic}
          </p>
        </article>
      ))}
    </div>
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

export default function FinancialRipV3Breakdown({
  financialRipV3,
  legacyRip,
  trends = {},
  requestTimeout = false,
  defaultMode = FINANCIAL_RIP_MODEL_MODES.V3,
}) {
  const [mode, setMode] = useState(defaultMode);

  const v3 = useMemo(
    () => selectFinancialRipV3Breakdown(financialRipV3, { requestTimeout }),
    [financialRipV3, requestTimeout]
  );
  const depth = useMemo(() => selectDepthAndRobustness(financialRipV3), [financialRipV3]);
  const v2 = useMemo(
    () => selectRipScoreBreakdown(legacyRip, trends, { requestTimeout }),
    [legacyRip, trends, requestTimeout]
  );

  const legacyAvailable = v2.rows.some((row) => row.score !== null && row.score !== undefined);
  const showingV3 = mode === FINANCIAL_RIP_MODEL_MODES.V3;

  return (
    <section data-financial-rip-breakdown={showingV3 ? "v3" : "v2"} className="min-w-0">
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-x-3 gap-y-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">
            {showingV3 ? "Financial RIP" : "Legacy Financial RIP V2"}
          </h3>
          <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
            {showingV3
              ? "90% of Overall RIP. Built from the simulated pack-value distribution and the pack price."
              : "Retired model, kept for comparison. Not used by the current Overall RIP."}
          </p>
        </div>
        <ModelToggle value={mode} onChange={setMode} legacyAvailable={legacyAvailable} />
      </div>

      {showingV3 ? (
        v3.diagnostics.status === "ready" ? (
          <>
            <div className="mt-3 grid min-w-0 gap-3 desk:grid-cols-2 xl:grid-cols-3">
              {v3.rows.map((row) => (
                <V3ComponentCard key={row.key} row={row} />
              ))}
            </div>
            <DepthAndRobustnessPanel diagnostic={depth} />
          </>
        ) : (
          // A precise unavailable state. It does NOT render V2 numbers under the
          // V3 heading, and it does not render zeros.
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
            {legacyAvailable ? (
              <p className="mt-2 text-xs text-[var(--text-secondary)]">
                A Legacy V2 score exists for this set. It is a different model and is not shown
                here in its place — switch to Legacy V2 to see it.
              </p>
            ) : null}
          </div>
        )
      ) : (
        <div className="mt-3 min-w-0">
          <LegacyV2Cards rows={v2.rows} />
        </div>
      )}
    </section>
  );
}
