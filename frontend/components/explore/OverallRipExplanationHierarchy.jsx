"use client";

// Overall RIP explanation hierarchy — ONE shared, version-aware component.
//
// Renders the view model produced by `overallRipExplanationHierarchySelector.mjs`.
// V10 data renders "90% Financial RIP V4 + 10% Collector Appeal V5" with no
// Accessibility claim. V12/publicRipContractV11 data renders
// "86% Financial RIP V4 + 4% Chase Accessibility Score + 10% Collector Appeal
// V5", with an OPTIONAL Market-Based Opening Quality explanatory grouping.
//
// This is the ONLY Overall RIP explanation implementation in the frontend.
// PokemonSetAnalysisClient.jsx (Set Analysis) and any future Product RIP V12
// surface must import and reuse THIS component rather than building a second,
// parallel explanation.
//
// No arithmetic happens in this file. Every number and every headline sentence
// is read from the selector's view model, which itself only ever reads
// backend-supplied weights.

import { selectOverallRipExplanationHierarchy } from "./overallRipExplanationHierarchySelector.mjs";

export default function OverallRipExplanationHierarchy({ sources = [] }) {
  const explanation = selectOverallRipExplanationHierarchy(...sources);

  return (
    <div className="overall-rip-explanation-hierarchy" data-overall-rip-version={explanation.version}>
      <p className="text-sm font-semibold text-[var(--text-primary)]">Overall RIP</p>
      <p className="mt-1 text-xs text-[var(--text-secondary)]">{explanation.publicQuestion}</p>

      {explanation.available ? (
        <p className="mt-2 text-sm text-[var(--text-primary)]">{explanation.headline}</p>
      ) : (
        <p className="mt-2 text-sm text-[var(--text-secondary)]">
          {explanation.statusReason || "Overall RIP is not currently available for this target."}
        </p>
      )}

      {!explanation.canonical ? (
        <p className="mt-1 text-[10px] uppercase tracking-wide text-amber-400">
          Shadow / not canonical — Overall RIP V10 remains the published score.
        </p>
      ) : null}

      {explanation.marketBased ? (
        <div className="mt-3 rounded-lg border border-[var(--border-subtle)] p-3">
          <p className="text-xs font-semibold text-[var(--text-primary)]">{explanation.marketBased.label}</p>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">{explanation.marketBased.publicQuestion}</p>
          <p className="mt-2 text-xs text-[var(--text-primary)]">{explanation.marketBased.headline}</p>
          <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
            {explanation.marketBased.internalHeadline}
          </p>
          <p className="mt-2 text-[10px] italic text-[var(--text-secondary)]">{explanation.marketBased.note}</p>
        </div>
      ) : null}
    </div>
  );
}
