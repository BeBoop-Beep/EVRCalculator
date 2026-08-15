"use client";

// The canonical Collector Appeal V4 section: one score, two scored factors.
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

import React, { useMemo } from "react";

import RipMetricDisclosureRow from "./RipMetricDisclosureRow.jsx";
import useRipDisclosureSection from "./useRipDisclosureSection.js";
import {
  FINANCIAL_VS_COLLECTOR_NOTE,
  selectCollectorAppealBreakdown,
} from "./collectorAppealBreakdownSelector.mjs";

// `canonical` is the ALREADY-RESOLVED bundle from resolveCanonicalRipV7, owned
// by the set page and shared with the hero, the Overview summary and Financial
// RIP. This component deliberately takes no raw sources: when it resolved its
// own `publicRipContractV8`/`overallRipV8` props it could land on a different
// source than the hero did, which is the exact split this pass removes.
export default function CollectorAppealBreakdown({ canonical }) {
  const appeal = useMemo(() => selectCollectorAppealBreakdown(canonical), [canonical]);
  // Collector Appeal's own accordion state, independent of Financial RIP's.
  const disclosure = useRipDisclosureSection();

  return (
    <section data-collector-appeal-v3 className="min-w-0">
      {/* Heading only. The Collector Appeal score, tier, rank and cohort are
          stated ONCE, in the compact supporting line directly under the RIP
          Score headline above; repeating them here put the same four values on
          screen twice, a few centimetres apart, in two different treatments.
          The factors below are what this section adds. */}
      {appeal.available ? (
        // THREE PEERS. A flat stack of identical rows: no arrows, no numbered
        // stages, no ordering device that reads as one factor feeding the next.
        // Every row uses the SAME component as Financial RIP's six, so neither
        // section's factors look more or less structural than the other's.
        <div data-collector-appeal-rows className="mt-2 min-w-0">
          {/* Three PEERS on one row at 1200px+, a stack below it. A grid is a
              side-by-side arrangement, not a sequence: there are still no
              arrows, no numbering and no ordering device that reads as one
              factor feeding the next. `items-start` keeps an expanded factor
              from stretching the other two, and no cell has a fixed height. */}
          <div className="grid min-w-0 grid-cols-1 items-start gap-y-0 desk:grid-cols-2 desk:gap-3">
          {appeal.rows.map((row) => (
            <RipMetricDisclosureRow
              key={row.key}
              rowKey={row.key}
              dataAttribute="data-collector-appeal-factor"
              title={row.title}
              value={row.value}
              meta={row.rank === null ? null : `Rank #${Math.round(row.rank)}${row.cohortSize === null ? "" : ` of ${Math.round(row.cohortSize)}`}`}
              tier={row.tier}
              interpretation={row.interpretation}
              // The same quiet tier-colored rail as Financial RIP. Its width is
              // the backend's cohort-relative standing, never the raw value.
              railPercent={row.railPercent ?? null}
              // Visible WITHOUT expanding. This is the sentence that stops a
              // probability under an appeal heading from reading as a promise
              // about money, so it can never be behind a disclosure.
              disclaimer={row.disclaimer || null}
              metrics={row.metrics}
              statusNote={!row.available && row.statusReason ? row.statusReason : null}
              isOpen={disclosure.openKeys.includes(row.key)}
              onToggle={disclosure.toggle}
            />
          ))}
          </div>
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
