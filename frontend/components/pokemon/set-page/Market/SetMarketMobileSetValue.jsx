"use client";

import React, { useEffect, useMemo, useState } from "react";

import MarketMobileSection from "./MarketMobileSection.jsx";
import MarketMobileChart from "./MarketMobileChart.jsx";
import MarketWindowSelector from "@/components/explore/MarketWindowSelector";
import MarketValueChange from "@/components/ui/MarketValueChange";
import SegmentedControl from "@/components/ui/SegmentedControl";
import { getDeltaWindowLabel } from "@/lib/explore/marketDeltaWindows.mjs";
import { getPokemonSetSealedMarket } from "@/lib/pokemon/pokemonSetMarketClient";
import {
  MARKET_SEGMENT_LABELS,
  SEGMENT_UNAVAILABLE_TEXT,
  buildMarketSegmentRows,
  buildSupportingDetails,
  resolveActiveSegmentKey,
  selectChaseConcentration,
  selectMarketBreadth,
  selectSegmentTrend,
  unavailableSegmentTrend,
} from "./setMarketOverviewModel.mjs";
import { formatCompactMoney, formatCount, formatSignedCompactMoney, formatSignedPercent } from "./setMarketMobileModel.mjs";

const shortDate = (value) =>
  value ? new Date(`${String(value).slice(0, 10)}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : null;

// ---------------------------------------------------------------------------
// Market Snapshot — the anchor of the mobile Market tab.
//
// Renamed in substance, not just in label: this used to switch between Cards
// and Top 10 SCOPES of the same card-market series. It now switches between
// Cards, Sealed and Graded LENSES — the exact same three the desktop Market
// Value Trend offers — because "Top 10" is a ranking slice of Cards, not a
// distinct market to view. Top 10 chase pricing already has its own dedicated
// section below; this control is strictly Cards | Sealed | Graded.
//
// SAME MODEL AS DESKTOP. Every number here comes from
// `setMarketOverviewModel.mjs` — the identical selectors
// `SetMarketOverviewSection` uses. A 7D move means the same thing in both
// compositions, and an unavailable lens (Graded, always; Sealed, when a set
// has no sealed products) renders the same em dash / "Not enough market data"
// treatment desktop uses. Nothing is fabricated for a cell mobile didn't
// previously render.
//
// TIMEFRAME OWNERSHIP. Unchanged from before: the window selector belongs to
// this section, not to the tab.
// ---------------------------------------------------------------------------

/** Mirrors the desktop `useSealedSetMarket` hook. The standalone mobile Sealed
 * Market module that used to own this fetch was removed as redundant — this
 * section's Sealed lens is now the only mobile consumer of it. */
function useSealedSetMarket(setId) {
  const [state, setState] = useState({ status: "idle", payload: null, error: null });

  useEffect(() => {
    if (!setId) {
      setState({ status: "idle", payload: null, error: null });
      return undefined;
    }
    let cancelled = false;
    setState((current) => ({ ...current, status: "loading" }));
    getPokemonSetSealedMarket(setId).then(
      (payload) => {
        if (!cancelled) setState({ status: "success", payload, error: null });
      },
      (error) => {
        if (!cancelled) setState({ status: "error", payload: null, error: error?.message || "Unable to load sealed market" });
      }
    );
    return () => {
      cancelled = true;
    };
  }, [setId]);

  return state;
}

function MicroStat({ label, value }) {
  return (
    <div className="min-w-0">
      <p className="truncate text-[9.5px] font-bold uppercase leading-none tracking-[0.11em] text-[rgba(199,214,234,0.6)]">
        {label}
      </p>
      <p className="mt-1 truncate text-[13px] font-semibold leading-tight tabular-nums text-[var(--text-primary)]">
        {value ?? "—"}
      </p>
    </div>
  );
}

/**
 * The 2-column micro-stat readout. Six fields are the active lens's own
 * supporting details (shared with desktop via `buildSupportingDetails`); the
 * final two — Breadth and Concentration — are card-market-only metrics, so
 * they render only while Cards is the active segment. Showing a "Cards"
 * concentration figure under a Sealed or Graded heading would misrepresent
 * what is being measured, so those two rows are omitted rather than reused.
 */
function SupportingMicroStats({ trend, segmentKey, breadth, concentration }) {
  const details = useMemo(() => buildSupportingDetails(trend), [trend]);
  const cells = details.map((detail) => {
    if (detail.key === "periodChange") return { label: detail.label, value: formatSignedCompactMoney(detail.amount) };
    if (detail.key === "periodReturn") return { label: detail.label, value: formatSignedPercent(detail.percent) };
    if (detail.key === "periodHigh" || detail.key === "periodLow") {
      return { label: detail.label, value: formatCompactMoney(detail.value) };
    }
    if (detail.key === "trackingSince") return { label: detail.label, value: shortDate(detail.date) };
    if (detail.key === "trackedItems") {
      const count = formatCount(detail.count);
      return { label: detail.label, value: count ? `${count} ${detail.noun}` : null };
    }
    return { label: detail.label, value: null };
  });

  if (segmentKey === "cards") {
    cells.push({
      label: "Market Breadth",
      value: breadth.available ? `${breadth.advancingPercent}% Advancing` : SEGMENT_UNAVAILABLE_TEXT,
    });
    cells.push({
      label: "Chase Concentration",
      value: concentration.available ? `${concentration.sharePercent}%` : SEGMENT_UNAVAILABLE_TEXT,
    });
  }

  return (
    <div data-market-mobile-micro-stats className="grid grid-cols-2 gap-x-3 gap-y-2.5 border-t border-[var(--border-subtle)] pt-2.5">
      {cells.map((cell) => (
        <MicroStat key={cell.label} label={cell.label} value={cell.value} />
      ))}
    </div>
  );
}

export default function SetMarketMobileSetValue({
  id,
  setId,
  history,
  historiesByScope,
  status = "success",
  error = null,
  cardsTrackedCount = null,
  top10Value = null,
  moversByWindow = null,
}) {
  const [activeSegmentKey, setActiveSegmentKey] = useState("cards");
  const [selectedWindowKey, setSelectedWindowKey] = useState("7D");
  const sealedState = useSealedSetMarket(setId);

  const cardsHistory = Array.isArray(historiesByScope?.standard) ? historiesByScope.standard : history;
  const cardsTrend = useMemo(
    () =>
      selectSegmentTrend({
        history: cardsHistory,
        selectedWindowKey,
        trackedItemCount: cardsTrackedCount,
        trackedItemNoun: "Cards",
      }),
    [cardsHistory, cardsTrackedCount, selectedWindowKey]
  );

  const sealedTrend = useMemo(() => {
    const setMarket = sealedState.payload?.setMarket || null;
    if (!setMarket?.history?.length) return unavailableSegmentTrend({ trackedItemNoun: "Sealed Products" });
    return selectSegmentTrend({
      history: setMarket.history,
      selectedWindowKey,
      trackedItemCount: setMarket.productCount,
      trackedItemNoun: "Sealed Products",
    });
  }, [sealedState.payload, selectedWindowKey]);

  // GRADED. No set-level graded market series is published anywhere in the
  // product — the only graded prices in the system are per-user collection
  // valuations, not a set market. Genuinely unavailable, never fabricated.
  const gradedTrend = useMemo(() => unavailableSegmentTrend({ trackedItemNoun: "Graded Cards" }), []);

  const trendsByKey = useMemo(
    () => ({ cards: cardsTrend, sealed: sealedTrend, graded: gradedTrend }),
    [cardsTrend, gradedTrend, sealedTrend]
  );
  const resolvedSegmentKey = resolveActiveSegmentKey(activeSegmentKey, trendsByKey);
  const activeTrend = trendsByKey[resolvedSegmentKey] || cardsTrend;
  // An unavailable lens (Graded, always; Sealed, sometimes) is disabled rather
  // than clickable-then-snapping-back — the same treatment desktop's segment
  // tabs use, so a reader sees WHY the option didn't take instead of a control
  // that appears to ignore their tap.
  const segmentOptions = useMemo(
    () =>
      buildMarketSegmentRows(trendsByKey).map((row) => ({
        value: row.key,
        label: row.label,
        disabled: !row.selectable,
      })),
    [trendsByKey]
  );
  const effectiveWindowKey = activeTrend.effectiveWindowKey || selectedWindowKey;
  const windowLabel = effectiveWindowKey ? getDeltaWindowLabel(effectiveWindowKey) : "Trend";
  const direction =
    activeTrend.deltaAmount === null ? "neutral" : activeTrend.deltaAmount < 0 ? "negative" : activeTrend.deltaAmount > 0 ? "positive" : "neutral";

  const breadth = useMemo(
    () => selectMarketBreadth({ moversByWindow, windowKey: effectiveWindowKey }),
    [effectiveWindowKey, moversByWindow]
  );
  const concentration = useMemo(
    () => selectChaseConcentration({ top10Value, cardsValue: cardsTrend.currentValue }),
    [cardsTrend.currentValue, top10Value]
  );

  const isLoading = (status === "loading" || status === "idle") && activeTrend.points.length === 0 && activeTrend.currentValue === null;
  const isError = status === "error" && activeTrend.currentValue === null && resolvedSegmentKey === "cards";

  return (
    <MarketMobileSection id={id} eyebrow="Market" title="Market Snapshot">
      {isLoading ? (
        <div className="space-y-3" aria-hidden="true">
          <div className="h-9 w-40 animate-pulse rounded-lg bg-[rgba(148,163,184,0.10)]" />
          <div className="h-11 w-full animate-pulse rounded-lg bg-[rgba(148,163,184,0.08)]" />
          <div className="h-[13rem] w-full animate-pulse rounded-xl bg-[rgba(148,163,184,0.08)]" />
        </div>
      ) : isError ? (
        <p className="text-[13px] text-red-300">{error || "Unable to load set value history for this set."}</p>
      ) : (
        <div className="space-y-3">
          {/* Compact segmented lens switch — a small analytical toggle, not a
              content module. Cards is the default selection. */}
          <SegmentedControl
            options={segmentOptions}
            value={resolvedSegmentKey}
            onChange={setActiveSegmentKey}
            ariaLabel="Market segment"
            equalWidth
            mobileFullWidth
          />

          {activeTrend.available ? (
            <>
              <div data-market-mobile-set-value-summary className="min-w-0">
                <MarketValueChange
                  value={activeTrend.currentValue}
                  changeAmount={activeTrend.deltaAmount}
                  changePercent={activeTrend.deltaPercent}
                  windowLabel={windowLabel}
                  variant="chart-summary"
                  accessibleLabel={`Current ${MARKET_SEGMENT_LABELS[resolvedSegmentKey]} market value`}
                />
              </div>

              <MarketWindowSelector
                windows={activeTrend.availableDeltaWindows}
                value={effectiveWindowKey}
                onChange={setSelectedWindowKey}
                fullWidth
                ariaDescription="Clips the Market Snapshot chart and its change reading to this timeframe. No data is fetched."
              />

              <MarketMobileChart
                key={`${setId || "set"}:${resolvedSegmentKey}:${effectiveWindowKey || "window"}:${activeTrend.series.length}`}
                points={activeTrend.series}
                valueKey="setValue"
                trendDirection={direction}
                seriesLabel={`${MARKET_SEGMENT_LABELS[resolvedSegmentKey]} market value`}
                heightClassName="h-[clamp(210px,29dvh,268px)]"
                emptyMessage="Not enough market history yet. The trend chart appears after a few days of market observations."
              />
            </>
          ) : (
            <div data-market-mobile-segment-unavailable className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[rgba(8,17,31,0.34)] px-4 py-6 text-center">
              <p className="text-xl font-semibold text-[var(--text-primary)]">—</p>
              <p className="mt-1 text-[13px] text-[var(--text-secondary)]">{activeTrend.unavailableReason || SEGMENT_UNAVAILABLE_TEXT}</p>
            </div>
          )}

          <SupportingMicroStats trend={activeTrend} segmentKey={resolvedSegmentKey} breadth={breadth} concentration={concentration} />
        </div>
      )}
    </MarketMobileSection>
  );
}
