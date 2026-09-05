"use client";

// Market-Based Opening Quality — ONE shared PRESENTATION container (Phase 5 of
// the Overall RIP V12 UI standardization pass).
//
// THIS IS NOT A NEW SCORE.
// -------------------------
// "Market-Based Opening Quality" is the locked EXPLANATORY grouping over
// Financial RIP + Chase Accessibility (see
// `overallRipExplanationHierarchySelector.mjs`'s `marketBased` object, which
// this component renders the header/note from). It is never persisted, never
// independently scored, and this component performs no arithmetic of its own
// — every number it shows is read from the Financial RIP V3 breakdown
// selector or the Chase Accessibility presentation selector, both of which
// already read backend-only values.
//
// TWO DEPTH MODES
// -----------------
// COMPACT: a one-line Financial RIP summary + a one-line Chase Accessibility
// summary — for a hero/summary context that just needs "what are the two
// ingredients and roughly how do they read".
// FULL: Financial RIP's existing six-dimension breakdown (reused verbatim via
// `FinancialRipV3Breakdown`, no restyle) sitting alongside a Chase
// Accessibility panel showing its primary metric, then (behind the same
// disclosure visual language as Financial's Depth-and-Robustness panel) its
// diagnostics: Chase Depth and Mapped HC Mass coverage. Rank/tier is NOT
// rendered as a real value (see the Phase 8 note below) — if a caller wants
// this to ever show a cohort rank, that requires a canonical backend Chase
// Accessibility ranking contract that does not exist yet.
//
// SIX CHASE FACTORS ARE NOT FABRICATED.
// ---------------------------------------
// Chase Accessibility currently has exactly ONE scored metric (the raw
// accessibility value) plus two real diagnostics (Chase Depth, Mapped HC
// Mass coverage). This component does not invent additional "Chase factor"
// cards to visually mirror Financial RIP's six; it mirrors the visual
// LANGUAGE (glass surface, disclosure rows, MetricRow dt/dd pattern) while
// staying truthful about what is actually scored vs. diagnostic.
//
// NO WEIGHT DISCLOSURE.
// ------------------------
// Nothing in this component renders a scoring-weight percentage. The
// Market-Based header/note text is read verbatim from
// `overallRipExplanationHierarchySelector.mjs`'s already-fixed,
// presentation-safe copy.

import React, { useMemo, useState } from "react";

import FinancialRipV3Breakdown from "./FinancialRipV3Breakdown.jsx";
import { resolveCanonicalFinancialRip, selectFinancialRipV3Breakdown } from "./financialRipV3Selector.mjs";
import { selectChaseAccessibilityPresentation } from "./chaseAccessibilityPresentationSelector.mjs";
import { MARKET_BASED_LABEL, MARKET_BASED_PUBLIC_QUESTION } from "./overallRipExplanationHierarchySelector.mjs";

function MetricRow({ label, value }) {
  return (
    <div className="flex min-w-0 items-baseline justify-between gap-3">
      <dt className="min-w-0 text-xs text-[var(--text-secondary)]">{label}</dt>
      <dd className="flex-none text-xs font-semibold tabular-nums text-[var(--text-primary)]">{value}</dd>
    </div>
  );
}

function formatPercent(value, digits = 2) {
  return value === null || value === undefined ? "—" : `${value.toFixed(digits)}%`;
}

/** Chase Accessibility — COMPACT: one summary line, no diagnostics panel. */
function ChaseAccessibilitySummary({ chase }) {
  return (
    <div data-chase-accessibility-summary className="min-w-0">
      <p className="text-xs font-semibold text-[var(--text-primary)]">{chase.label}</p>
      <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">{chase.publicQuestion}</p>
      {chase.available ? (
        <p className="mt-1.5 text-sm font-semibold tabular-nums text-[var(--text-primary)]">
          {formatPercent(chase.displayAccessibility)}
        </p>
      ) : (
        <p className="mt-1.5 text-xs text-[var(--text-secondary)]">
          {chase.statusReason || "Chase Accessibility is not currently available for this set."}
        </p>
      )}
    </div>
  );
}

/**
 * Chase Accessibility — FULL: primary metric plus a disclosure panel for
 * Chase Depth / Mapped HC Mass, mirroring the visual language of Financial
 * RIP's "Depth and robustness" panel WITHOUT claiming these are scored
 * components. Rank/tier fields are read from the selector but are always
 * null today (Phase 8) — rendered only as "not yet available", never
 * fabricated.
 */
function ChaseAccessibilityFullPanel({ chase }) {
  const [isOpen, setIsOpen] = useState(false);
  const panelId = "chase-accessibility-diagnostics-panel";
  const buttonId = "chase-accessibility-diagnostics-control";

  return (
    <div data-chase-accessibility-full className="min-w-0">
      <p className="text-sm font-semibold text-[var(--text-primary)]">{chase.label}</p>
      <p className="mt-1 text-xs text-[var(--text-secondary)]">{chase.publicQuestion}</p>

      {chase.available ? (
        <p className="mt-2 text-lg font-semibold tabular-nums text-[var(--text-primary)]">
          {formatPercent(chase.displayAccessibility)}
        </p>
      ) : (
        <p className="mt-2 text-xs text-[var(--text-secondary)]">
          {chase.statusReason || "Chase Accessibility is not currently available for this set."}
        </p>
      )}

      {/* Rank line — NEVER a fabricated cohort rank (Phase 8). Rendered only
          when the backend eventually supplies one. */}
      {chase.rank !== null ? (
        <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
          {`Rank #${chase.rank}${chase.cohortSize ? ` of ${chase.cohortSize}` : ""}`}
        </p>
      ) : (
        <p className="mt-1 text-[11px] italic text-[var(--text-secondary)]">
          Cohort rank not yet available for Chase Accessibility.
        </p>
      )}

      <section
        data-chase-accessibility-diagnostics
        data-chase-accessibility-diagnostics-context-only="true"
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
            Chase depth &amp; concentration
          </span>
          <span className="inline-flex flex-none items-center gap-1 text-[11px] font-medium text-[var(--text-secondary)]">
            {isOpen ? "Hide context" : "View context"}
            <svg aria-hidden="true" viewBox="0 0 12 12" className={`h-3 w-3 transition-transform ${isOpen ? "rotate-180" : ""}`}><path d="m2.5 4.25 3.5 3.5 3.5-3.5" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </span>
        </button>

        {/* Stated before the panel opens so nobody mistakes these for
            additional scored Overall RIP inputs. */}
        <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
          Diagnostics — not part of the Chase Accessibility score.
        </p>

        {isOpen ? (
          <div id={panelId} role="region" aria-labelledby={buttonId} className="mt-2.5 min-w-0">
            <dl className="grid gap-x-6 gap-y-1.5 desk:grid-cols-2">
              <MetricRow
                label="Chase Depth"
                value={chase.chaseDepthAvailable ? chase.chaseDepth.toFixed(2) : "Not available"}
              />
              <MetricRow
                label="Value Concentration"
                value={chase.valueConcentration === null ? "Not yet published" : chase.valueConcentration}
              />
              <MetricRow
                label="Top-card Concentration"
                value={chase.topCardConcentration === null ? "Not yet published" : chase.topCardConcentration}
              />
              <MetricRow
                label="Mapped HC Mass Coverage"
                value={chase.mappedHcMassAvailable ? formatPercent(chase.mappedHcMass, 1) : "Not available"}
              />
            </dl>
          </div>
        ) : null}
      </section>
    </div>
  );
}

/**
 * `canonical` — the ALREADY-RESOLVED bundle shared with the Set RIP hero
 * (same rule `FinancialRipV3Breakdown` follows: no independent re-resolution
 * that could disagree with the hero). `sources` — the raw source objects the
 * Overall RIP explanation hierarchy selector needs to resolve the
 * `marketBased` grouping and (for FULL mode) the Chase Accessibility
 * presentation; typically the same `rawSources` array already passed to
 * `OverallRipExplanationHierarchy`.
 */
export default function MarketBasedOpeningQualityBreakdown({
  canonical,
  sources = [],
  depth = "compact",
  requestTimeout = false,
}) {
  const financialRip = useMemo(() => resolveCanonicalFinancialRip(canonical), [canonical]);
  const financialSummary = useMemo(
    () => selectFinancialRipV3Breakdown(financialRip, { requestTimeout }),
    [financialRip, requestTimeout]
  );
  const chase = useMemo(() => selectChaseAccessibilityPresentation(...sources), [sources]);

  const isFull = depth === "full";

  return (
    <section data-market-based-opening-quality={depth} className="min-w-0">
      <p className="text-xs font-semibold text-[var(--text-primary)]">{MARKET_BASED_LABEL}</p>
      <p className="mt-1 text-[11px] text-[var(--text-secondary)]">{MARKET_BASED_PUBLIC_QUESTION}</p>
      <p className="mt-1 text-[10px] italic text-[var(--text-secondary)]">
        Explanatory grouping only — not an independent third pillar and never persisted as its own score.
      </p>

      {isFull ? (
        <div className="mt-3 grid min-w-0 grid-cols-1 items-start gap-4 desk:grid-cols-2">
          <div data-market-based-financial-child className="min-w-0">
            {financialSummary.diagnostics.status === "ready" ? (
              <FinancialRipV3Breakdown canonical={canonical} requestTimeout={requestTimeout} />
            ) : (
              <p className="text-xs text-[var(--text-secondary)]">
                {financialSummary.diagnostics.statusReason || "Financial RIP is not currently available."}
              </p>
            )}
          </div>
          <div data-market-based-chase-child className="min-w-0">
            <ChaseAccessibilityFullPanel chase={chase} />
          </div>
        </div>
      ) : (
        <div className="mt-3 grid min-w-0 grid-cols-1 items-start gap-3 desk:grid-cols-2">
          <div data-market-based-financial-child className="min-w-0">
            <p className="text-xs font-semibold text-[var(--text-primary)]">Financial RIP</p>
            <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
              How favorable are the modeled financial outcomes of opening this?
            </p>
            {financialSummary.diagnostics.status === "ready" ? (
              <p className="mt-1.5 text-sm font-semibold text-[var(--text-primary)]">
                {financialSummary.rows.length} scored dimensions
              </p>
            ) : (
              <p className="mt-1.5 text-xs text-[var(--text-secondary)]">
                {financialSummary.diagnostics.statusReason || "Not currently available."}
              </p>
            )}
          </div>
          <div data-market-based-chase-child className="min-w-0">
            <ChaseAccessibilitySummary chase={chase} />
          </div>
        </div>
      )}
    </section>
  );
}
