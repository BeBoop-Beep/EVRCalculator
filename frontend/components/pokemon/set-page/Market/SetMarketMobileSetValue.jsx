"use client";

import React, { useEffect, useMemo, useState } from "react";

import MarketMobileSection from "./MarketMobileSection.jsx";
import MarketMobileChart from "./MarketMobileChart.jsx";
import MarketWindowSelector from "@/components/explore/MarketWindowSelector";
import MarketValueChange from "@/components/ui/MarketValueChange";
import SegmentedControl from "@/components/ui/SegmentedControl";
import { getDeltaWindowLabel } from "@/lib/explore/marketDeltaWindows.mjs";
import { selectSetValueTrendFromContract } from "@/components/explore/setValueContract.mjs";
import {
  CANONICAL_SET_VALUE_SCOPE_KEY,
  SET_VALUE_TREND_VISIBLE_SCOPE_OPTIONS,
  selectOverviewSetValueTrendByScope,
} from "@/components/explore/setValueTrendSelector.mjs";

// ---------------------------------------------------------------------------
// Set Value — the anchor of the mobile Market tab.
//
// SAME DATA, SAME SELECTORS. This reads `selectSetValueTrendFromContract` when
// the page has a published Set Value contract and
// `selectOverviewSetValueTrendByScope` otherwise — byte for byte the branch the
// desktop card takes. No value, delta, window or scope is computed here; this
// module chooses layout only.
//
// TIMEFRAME OWNERSHIP. The window selector belongs to this section, not to the
// tab. A single master toggle at the top of the page would have to govern three
// modules whose supported windows differ (Set Value publishes whatever its
// history covers; sealed products publish their own), so it would spend most of
// its life showing options that two of the three sections silently ignore.
// Per-section control is the honest model on a phone, and it is the model the
// desktop composition already uses below 1200px.
// ---------------------------------------------------------------------------

export default function SetMarketMobileSetValue({
  id,
  setId,
  setValueContract,
  history,
  historiesByScope,
  availableScopes,
  status = "success",
  error = null,
  selectedScope = CANONICAL_SET_VALUE_SCOPE_KEY,
  onSelectedScopeChange,
  marketAsOfDate = null,
}) {
  const [selectedWindowKey, setSelectedWindowKey] = useState(null);

  const scopeOptions = useMemo(() => {
    const published = new Set(
      (Array.isArray(availableScopes) ? availableScopes : []).map((entry) => entry?.key).filter(Boolean)
    );
    // Only scopes this set actually publishes are offered; the canonical scope
    // is always offered because it is what every other surface reports.
    return SET_VALUE_TREND_VISIBLE_SCOPE_OPTIONS.filter(
      (entry) => entry.key === CANONICAL_SET_VALUE_SCOPE_KEY || published.has(entry.key)
    );
  }, [availableScopes]);

  const resolvedScope = scopeOptions.some((entry) => entry.key === selectedScope)
    ? selectedScope
    : CANONICAL_SET_VALUE_SCOPE_KEY;

  const trend = useMemo(
    () =>
      setValueContract
        ? selectSetValueTrendFromContract({
            contract: setValueContract,
            selectedScope: resolvedScope,
            selectedWindowKey,
          })
        : selectOverviewSetValueTrendByScope({
            history,
            historiesByScope,
            selectedScope: resolvedScope,
            allowedScopes: scopeOptions.map((entry) => entry.key),
            selectedWindowKey,
            preferredWindowKey: "30D",
            marketAsOfDate,
          }),
    [history, historiesByScope, marketAsOfDate, resolvedScope, scopeOptions, selectedWindowKey, setValueContract]
  );

  const effectiveWindowKey = trend.effectiveWindowKey;
  const windowLabel = effectiveWindowKey ? getDeltaWindowLabel(effectiveWindowKey) : "Trend";
  const direction =
    trend.deltaAmount === null ? "neutral" : trend.deltaAmount < 0 ? "negative" : trend.deltaAmount > 0 ? "positive" : "neutral";

  // A new set, or a new scope, drops back to the selector's own preferred
  // window rather than carrying a window the new series may not cover.
  useEffect(() => {
    setSelectedWindowKey(null);
  }, [setId, resolvedScope]);

  useEffect(() => {
    if (!effectiveWindowKey || selectedWindowKey === effectiveWindowKey) return;
    setSelectedWindowKey(effectiveWindowKey);
  }, [effectiveWindowKey, selectedWindowKey]);

  const isLoading = (status === "loading" || status === "idle") && trend.points.length === 0 && trend.currentValue === null;
  const isError = status === "error" && trend.currentValue === null;

  return (
    <MarketMobileSection id={id} eyebrow="Market" title="Set Value">
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
          {/* The reading leads: value, then movement, then the window that
              movement was measured over. MarketValueChange is the same
              component desktop uses, so the tone, the glyph and the accessible
              sentence are identical across compositions. */}
          <div data-market-mobile-set-value-summary className="min-w-0">
            <MarketValueChange
              value={trend.currentValue}
              changeAmount={trend.deltaAmount}
              changePercent={trend.deltaPercent}
              unavailable={!trend.hasTrend && trend.deltaAmount === null}
              windowLabel={windowLabel}
              variant="chart-summary"
              accessibleLabel={`Current ${trend.metricLabel}`}
            />
            {trend.shareOfStandardPercent !== null ? (
              <p className="mt-1.5 text-[11px] text-[var(--text-secondary)]">
                {`Share of Set Value: ${trend.shareOfStandardPercent.toFixed(1)}%`}
              </p>
            ) : null}
          </div>

          {scopeOptions.length > 1 ? (
            <SegmentedControl
              options={scopeOptions.map((entry) => ({ value: entry.key, label: entry.label }))}
              value={trend.scope}
              onChange={onSelectedScopeChange}
              ariaLabel="Set value scope"
              equalWidth
              mobileFullWidth
            />
          ) : null}

          <MarketWindowSelector
            windows={trend.availableDeltaWindows}
            value={effectiveWindowKey}
            onChange={setSelectedWindowKey}
            fullWidth
            ariaDescription="Clips the Set Value chart and its change reading to this timeframe. No data is fetched."
          />

          <MarketMobileChart
            key={`${setId || "set"}:${trend.scope}:${effectiveWindowKey || "window"}:${trend.series.length}`}
            points={trend.series}
            valueKey="setValue"
            trendDirection={direction}
            seriesLabel={`${trend.label} Set Value`}
            heightClassName="h-[clamp(210px,29dvh,268px)]"
            emptyMessage="Not enough set value history yet. The trend chart appears after a few days of market observations."
          />
        </div>
      )}
    </MarketMobileSection>
  );
}
