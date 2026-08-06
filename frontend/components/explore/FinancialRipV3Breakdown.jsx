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

import React, { useMemo, useState } from "react";

import RipMetricDisclosureRow from "./RipMetricDisclosureRow.jsx";
import useRipDisclosureSection from "./useRipDisclosureSection.js";
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

/**
 * The rank/tier line, pre-formatted from BACKEND fields only. When the backend
 * ranked this component the line states the rank, its cohort and the tier; when
 * it did not, the backend's own diagnostic is printed instead of a blank.
 */
function formatComponentMeta(row) {
  if (row.rankValue === null || row.rankValue === undefined) {
    return row.rankDiagnostic || null;
  }
  return [
    `Rank #${row.rankValue}`,
    row.cohortSize ? ` of ${row.cohortSize}` : "",
    row.rankTier ? ` · Tier ${row.rankTier}` : "",
  ].join("");
}

// DEPTH AND ROBUSTNESS — CONTEXT, NEVER A SEVENTH COMPONENT.
//
// It sits BELOW the six scored rows, behind its own collapsed disclosure, and
// says in the UI (not only in this comment) that it is not part of the score.
// It deliberately does not use RipMetricDisclosureRow: that component renders a
// scored metric row, and borrowing it here would put this panel in the same
// visual class as the six things that ARE scored. Its supporting values are
// unchanged.
function DepthAndRobustnessPanel({ diagnostic }) {
  const [isOpen, setIsOpen] = useState(false);
  const panelId = "financial-rip-depth-and-robustness-panel";
  const buttonId = "financial-rip-depth-and-robustness-control";

  return (
    <section
      data-depth-and-robustness
      data-depth-and-robustness-context-only="true"
      className="mt-3 min-w-0 border-t border-[var(--border-subtle)] pt-2.5"
    >
      <button
        type="button"
        id={buttonId}
        aria-expanded={isOpen}
        aria-controls={panelId}
        onClick={() => setIsOpen((previous) => !previous)}
        className="flex w-full min-w-0 items-baseline justify-between gap-3 rounded text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
      >
        <span className="min-w-0 text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
          Depth and robustness
        </span>
        <span className="flex-none text-[11px] font-medium text-[var(--text-secondary)]">
          {isOpen ? "Hide" : "Show"}
          <span aria-hidden="true" className="pl-1 text-[9px] leading-none">
            {isOpen ? "▲" : "▼"}
          </span>
        </span>
      </button>

      {/* Stated where a reader sees it before opening the panel, so nobody
          counts these values as a seventh scored component. */}
      <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
        Additional context — not part of the Financial RIP score.
      </p>

      {isOpen ? (
        <div id={panelId} role="region" aria-labelledby={buttonId} className="mt-2.5 min-w-0">
          {diagnostic.available ? (
            <>
              {diagnostic.concentrationLabel ? (
                <p className="text-sm font-semibold text-[var(--text-primary)]">
                  {diagnostic.concentrationLabel}
                </p>
              ) : null}
              <dl className="mt-2 grid gap-x-6 gap-y-1.5 desk:grid-cols-2">
                {diagnostic.rows.map((row) => (
                  <MetricRow key={row.key} label={row.label} value={row.value} />
                ))}
              </dl>
            </>
          ) : (
            <p className="text-xs text-[var(--text-secondary)]">
              {diagnostic.statusReason || "Not available for this set yet."}
            </p>
          )}
        </div>
      ) : null}
    </section>
  );
}

// `canonical` is the ALREADY-RESOLVED bundle from resolveCanonicalRipV7, owned
// by the set page and shared with the hero, the Overview summary and Collector
// Appeal. This component deliberately takes no raw sources: when it resolved
// its own `publicRipContractV7`/`overallRipV7`/`financialRipV3` props it could
// land on a different source than the hero did, which is the exact split this
// pass removes.
export default function FinancialRipV3Breakdown({ canonical, requestTimeout = false }) {
  const financialRip = useMemo(() => resolveCanonicalFinancialRip(canonical), [canonical]);
  const v3 = useMemo(
    () => selectFinancialRipV3Breakdown(financialRip, { requestTimeout }),
    [financialRip, requestTimeout]
  );
  const depth = useMemo(() => selectDepthAndRobustness(financialRip), [financialRip]);
  // Financial RIP's own accordion state. Collector Appeal calls the hook
  // separately, so expanding a factor there never collapses a component here.
  const disclosure = useRipDisclosureSection();

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
          {/* SIX SCANNABLE ROWS, not six open reports. Every supporting metric
              the backend publishes is still here, one disclosure away; none was
              dropped to make the default view shorter. */}
          <div data-financial-rip-rows className="mt-2 min-w-0">
            {v3.rows.map((row) => (
              <RipMetricDisclosureRow
                key={row.key}
                rowKey={row.key}
                dataAttribute="data-v3-component"
                title={row.title}
                value={row.scoreLabel}
                valueSuffix="/100"
                meta={formatComponentMeta(row)}
                interpretation={row.interpretation}
                metrics={row.metrics}
                isOpen={disclosure.openKeys.includes(row.key)}
                onToggle={disclosure.toggle}
              />
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
