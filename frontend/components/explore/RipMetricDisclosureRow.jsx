"use client";

// ONE compact disclosure row, shared by Financial RIP's six components and
// Collector Appeal's three factors.
//
// WHY THIS EXISTS
// ---------------
// Both surfaces previously rendered every metric as a full report card with all
// of its supporting numbers permanently open: six of them under Financial RIP
// and three under Collector Appeal, each a bordered glass tile carrying a title,
// a score, a rank line, an explanation and a `<dl>` of four to six rows. The
// default view was therefore nine expanded reports, which is a document to read
// rather than a set of scores to scan. The supporting numbers are not removed —
// every one of them is still reachable — they are simply behind a disclosure, so
// the default state answers "how does this set score" and the expanded state
// answers "why".
//
// DELIBERATELY NARROW SCOPE
// -------------------------
// This is a RIP metric row, not a site-wide generic disclosure component. It
// knows about scores, tiers, ranks and cohorts because those are what its two
// callers show. The existing architecture has no general accordion primitive to
// extend, and inventing one to serve two callers would be speculative.
//
// INTERACTION, BY WIDTH
// ---------------------
// The MARKUP AND CONTROLS ARE IDENTICAL at every width — same button, same
// aria-expanded/aria-controls wiring, same panel. Only the open-set policy
// differs, and it is owned by `useRipDisclosureSection` rather than by the row:
//
//   mobile (< 1200px)  one row open at a time WITHIN A SECTION. Opening a row
//                      closes the previously open row, so a phone never has to
//                      scroll past four expanded panels to reach the fifth.
//   desktop (>= 1200px) any number of rows open at once. There is room to
//                      compare two components side by side, and forcing the
//                      mobile accordion there would take that away.
//
// Each section calls the hook separately, so Financial RIP and Collector Appeal
// hold INDEPENDENT accordion state: expanding a Collector Appeal factor never
// collapses a Financial RIP component.
//
// THIS MODULE HAS NO VIEWPORT DEPENDENCY. The row renders exactly what it is
// told and never asks how wide the window is; `useRipDisclosureSection` owns
// the media query and `ripDisclosurePolicy` owns the open-set decision. That
// separation is what lets the row be rendered and asserted on directly, instead
// of being checked by reading its source.

import React, { useId } from "react";

// THE QUIET RAIL.
//
// Deliberately NOT the summary treatment. The three Insights Summary cards own
// the elevated, glowing rail; these nine rows get a low-contrast fill with no
// bloom, no end dot and no shadow, so a breakdown reads as supporting evidence
// rather than as nine competing headlines. Only the accent hue changes between
// the two sections — blue/cyan for Financial RIP, purple/magenta for Collector
// Appeal — and both are drawn at the same restraint.
const RAIL_ACCENTS = {
  financial: "56,189,248",
  collector: "192,132,252",
};

/**
 * A rail is drawn ONLY from a real, finite value the row is already showing.
 * There is no fabricated history, no sparkline and no placeholder fill: an
 * unavailable metric renders the empty track, which reads as "no value" rather
 * than as zero. Zero itself IS a real value on a cohort-relative scale, so a
 * 0/100 metric remains available even though its fill has zero width.
 */
function MetricRail({ percent, accentFamily }) {
  const accent = RAIL_ACCENTS[accentFamily] || RAIL_ACCENTS.financial;
  const parsed = Number(percent);
  const width = Number.isFinite(parsed) ? Math.max(0, Math.min(100, parsed)) : null;
  const hasValue = width !== null;

  return (
    <div
      data-rip-metric-rail
      data-rail-emphasis="quiet"
      data-rail-available={hasValue ? "true" : "false"}
      className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-[rgba(255,255,255,0.05)]"
    >
      {hasValue ? (
        <div
          className="h-full rounded-full"
          style={{
            width: `${width}%`,
            background: `linear-gradient(90deg, rgba(${accent},0.26) 0%, rgba(${accent},0.5) 100%)`,
          }}
        />
      ) : null}
    </div>
  );
}

/**
 * The supporting-metric list. Rendered only when the row is expanded, so the
 * default view carries no hidden-but-present measurement noise.
 */
function SupportingMetrics({ metrics }) {
  return (
    <dl className="space-y-1.5 border-t border-[var(--border-subtle)] pt-2.5">
      {metrics.map((metric) => (
        <div key={metric.label} className="flex min-w-0 items-baseline justify-between gap-3">
          <dt className="min-w-0 text-xs text-[var(--text-secondary)]">{metric.label}</dt>
          {/* `tabular-nums` so a column of dollar values does not jitter
              between sets. A missing value arrives from the selector already
              rendered as an em dash and is printed as such — never as 0. */}
          <dd className="flex-none text-xs font-semibold tabular-nums text-[var(--text-primary)]">
            {metric.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * One metric row.
 *
 * Default (collapsed) content, in reading order:
 *   title · value · tier and rank where the backend supplies them ·
 *   one short explanation · the disclosure control when there is more to show.
 *
 * A row with NO supporting metrics renders no control at all rather than an
 * inert one that opens an empty panel — Roster Desirability is exactly that
 * case.
 *
 * `meta` is pre-formatted by the caller from backend fields. Nothing here
 * computes, rounds or normalises a score, a rank or a denominator.
 */
export default function RipMetricDisclosureRow({
  rowKey,
  title,
  value,
  valueSuffix = null,
  meta = null,
  interpretation = null,
  // Rendered ALWAYS, collapsed or not. Reserved for statements that change how
  // the visible number must be read — Collector Appeal's "a desirable outcome
  // can still be worth less than the pack price" is the only current use.
  disclaimer = null,
  metrics = [],
  // The quiet rail. `railPercent` is a 0-100 reading of the value already
  // rendered above it, supplied by the caller from backend numbers only; null
  // (or a non-finite value) draws the empty track. `accentFamily` selects the
  // section hue and nothing else — it never changes the rail's emphasis.
  railPercent = null,
  accentFamily = null,
  statusNote = null,
  isOpen = false,
  onToggle,
  // Distinguishes the two sections' rows in the DOM for tests and for styling
  // hooks, without either section needing its own copy of this component.
  dataAttribute = null,
}) {
  // Stable across renders, and unique per mounted row, so aria-controls points
  // at exactly one panel even when both sections render a row with the same key.
  const generatedId = useId();
  const panelId = `${generatedId}-panel`;
  const buttonId = `${generatedId}-control`;

  const hasMetrics = Array.isArray(metrics) && metrics.length > 0;
  const attributes = dataAttribute ? { [dataAttribute]: rowKey } : {};

  return (
    <div
      {...attributes}
      data-rip-metric-row={rowKey}
      /* Below 1200px the row stays a divider-separated stack: a phone reads a
         list, not a wall of boxes. At 1200px+ it becomes a compact card so the
         two sections can lay their rows out on a grid without the dividers
         running into each other between columns. Nothing about the markup, the
         controls or the disclosure wiring changes with width. */
      className="min-w-0 rounded-xl border border-[rgba(255,255,255,0.09)] bg-[linear-gradient(145deg,rgba(255,255,255,0.045),rgba(255,255,255,0.012))] p-3.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.04),0_8px_24px_rgba(0,0,0,0.08)] transition-colors hover:border-[rgba(255,255,255,0.15)]"
    >
      <div className="flex min-w-0 items-baseline justify-between gap-3">
        <h4 className="min-w-0 text-sm font-semibold text-[var(--text-primary)]">{title}</h4>
        <p className="flex-none text-base font-semibold leading-none tabular-nums text-[var(--text-primary)]">
          {value}
          {valueSuffix ? (
            <span className="pl-0.5 text-[10px] font-medium text-[var(--text-secondary)]">{valueSuffix}</span>
          ) : null}
        </p>
      </div>

      {railPercent !== null && railPercent !== undefined ? (
        <MetricRail percent={railPercent} accentFamily={accentFamily} />
      ) : null}

      {meta ? <p className="mt-1 text-[11px] font-medium text-[var(--text-secondary)]">{meta}</p> : null}

      {interpretation ? (
        <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">{interpretation}</p>
      ) : null}

      {disclaimer ? (
        <p
          data-desirable-outcome-disclaimer
          className="mt-1.5 text-[11px] italic leading-relaxed text-[var(--text-secondary)]"
        >
          {disclaimer}
        </p>
      ) : null}

      {hasMetrics ? (
        <>
          {/* A plain <button>. It is never nested inside a link or another
              button: the row is a sibling of the section's navigation, not a
              child of it, so activating the disclosure cannot also navigate. */}
          <button
            type="button"
            id={buttonId}
            aria-expanded={isOpen}
            aria-controls={panelId}
            onClick={() => onToggle?.(rowKey)}
            className="mt-1.5 inline-flex items-center gap-1 rounded text-[11px] font-medium text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
          >
            {isOpen ? "Hide details" : "Details"}
            <svg aria-hidden="true" viewBox="0 0 12 12" className={`h-3 w-3 transition-transform ${isOpen ? "rotate-180" : ""}`}><path d="m2.5 4.25 3.5 3.5 3.5-3.5" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </button>

          {/* Unmounted rather than hidden when collapsed, so a screen reader
              and a keyboard tab order both see exactly what is on screen. */}
          {isOpen ? (
            <div id={panelId} role="region" aria-labelledby={buttonId} className="mt-2.5 min-w-0">
              <SupportingMetrics metrics={metrics} />
              {statusNote ? (
                <p className="mt-2 text-[11px] text-[var(--text-secondary)]">{statusNote}</p>
              ) : null}
            </div>
          ) : null}
        </>
      ) : statusNote ? (
        <p className="mt-1.5 text-[11px] text-[var(--text-secondary)]">{statusNote}</p>
      ) : null}
    </div>
  );
}
