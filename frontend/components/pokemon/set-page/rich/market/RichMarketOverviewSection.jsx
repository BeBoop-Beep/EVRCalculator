"use client";

import { useId, useMemo, useState } from "react";
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip as RechartsTooltip, XAxis, YAxis } from "recharts";
import ChartEdgeDateTick from "@/components/explore/ChartEdgeDateTick";
import ChartFrame from "@/components/explore/ChartFrame";
import MarketTrendTooltipCard from "@/components/explore/MarketTrendTooltipCard";
import MarketWindowSelector from "@/components/explore/MarketWindowSelector";
import InfoPopover from "@/components/ui/InfoPopover";
import MarketValueChange from "@/components/ui/MarketValueChange";
import { ChaseConcentrationSignal, MarketBreadthSignal, useSetMarketSignalAccess } from "@/components/pokemon/set-page/Market/SetMarketSignals";
import usePokemonSetMarketSignals from "@/hooks/pokemon/usePokemonSetMarketSignals";
import usePointerMode, { POINTER_MODE_COARSE } from "@/hooks/usePointerMode";
import { MINIMAL_Y_AXIS_PROPS, buildEdgeDateTicks, getMinimalPlotMargin } from "@/components/explore/minimalChartAxis.mjs";
import { NEGATIVE_VALUE_COLOR, POSITIVE_VALUE_COLOR } from "@/lib/explore/interpretationTone";
import { formatHistoryDate, getHistoryDateKey } from "@/components/explore/historyDateFormatting.mjs";
import { getDeltaWindowLabel } from "@/lib/explore/marketDeltaWindows.mjs";
import {
  MARKET_SEGMENT_LABELS,
  SEGMENT_UNAVAILABLE_TEXT,
  buildMarketSegmentRows,
  buildSupportingDetails,
  resolveActiveSegmentKey,
  selectChaseConcentration,
  selectPreparedMarketBreadth,
  selectPreparedSegmentTrend,
  unavailableSegmentTrend,
} from "@/components/pokemon/set-page/Market/setMarketOverviewModel.mjs";

const currencyFormatter = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const toNumber = (value) => { if (value === null || value === undefined || value === "") return null; const parsed = Number(value); return Number.isFinite(parsed) ? parsed : null; };
const getPriceDeltaPercent = (currentValue, previousValue) => { const current = toNumber(currentValue); const previous = toNumber(previousValue); return current === null || previous === null || previous === 0 ? null : ((current - previous) / previous) * 100; };
const getPriceDeltaAmount = (currentValue, previousValue) => { const current = toNumber(currentValue); const previous = toNumber(previousValue); return current === null || previous === null ? null : current - previous; };
const formatShortDate = (value) => value ? (formatHistoryDate(value, { month: "short", day: "numeric" }) || String(value).slice(0, 10)) : null;
const formatLongDate = (value) => value ? (formatHistoryDate(value, { year: "numeric", month: "short", day: "numeric" }) || String(value)) : "Date unavailable";

function formatAxisCurrency(value) {
  const parsed = toNumber(value);
  if (parsed === null) return "N/A";
  const abs = Math.abs(parsed);
  if (abs >= 1000000) return `$${(parsed / 1000000).toFixed(1)}M`;
  if (abs >= 1000) return `$${(parsed / 1000).toFixed(abs >= 10000 ? 0 : 1)}K`;
  return formatCurrency(parsed);
}

function buildCurrencyTicks(points) {
  const values = points.map((point) => toNumber(point?.setValue ?? point?.value)).filter((value) => value !== null);
  if (values.length === 0) {
    return [];
  }

  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const rawRange = maxValue - minValue;
  const padding = rawRange > 0 ? rawRange * 0.16 : Math.max(Math.abs(maxValue) * 0.08, 1);
  const lower = Math.max(0, minValue - padding);
  const upper = maxValue + padding;
  const range = upper - lower || Math.max(upper, 1);
  const stepBase = Math.pow(10, Math.floor(Math.log10(range / 3 || 1)));
  const roughStep = range / 3;
  const stepMultiplier = roughStep / stepBase <= 2 ? 2 : roughStep / stepBase <= 5 ? 5 : 10;
  const step = stepBase * stepMultiplier;
  const start = Math.floor(lower / step) * step;
  const end = Math.ceil(upper / step) * step;
  const ticks = [];

  for (let value = start; value <= end + step * 0.5; value += step) {
    const rounded = Number(value.toFixed(2));
    if (rounded >= 0 && !ticks.includes(rounded)) {
      ticks.push(rounded);
    }
  }

  if (ticks.length >= 2) {
    return ticks;
  }

  return [Math.max(0, minValue - padding), maxValue + padding].filter(
    (value, index, list) => list.findIndex((candidate) => Math.abs(candidate - value) < 0.01) === index
  );
}

function SetValueTooltip({ active, payload }) {
  const row = active && payload?.[0]?.payload;
  if (!row) {
    return null;
  }
  return (
    <MarketTrendTooltipCard
      date={row.date}
      value={row.setValue}
      deltaAmount={row.deltaFromPrevious}
      deltaPercent={row.deltaPercentFromPrevious}
      isCarriedForward={row.isCarriedForward}
      sourceDate={row.sourceDate}
    />
  );
}

export function SetValueLineChart({ points, trendDirection = "neutral", scopeLabel = "Set" }) {
  const isCoarsePointer = usePointerMode() === POINTER_MODE_COARSE;
  // No width branch left to make: the axis treatment is now identical at every
  // size, so this chart no longer reads the desktop composition at all. Pointer
  // mode still decides tap-vs-hover, which is a capability, not a width.
  const chartId = useId().replace(/:/g, "");
  let previousValuedPoint = null;
  const numericPoints = (Array.isArray(points) ? points : [])
    .map((point, index) => {
      const setValue = toNumber(point?.setValue ?? point?.value);
      const explicitDeltaAmount = toNumber(point?.deltaFromPrevious);
      const explicitDeltaPercent = toNumber(point?.deltaPercentFromPrevious);
      const fallbackDeltaAmount =
        setValue !== null && previousValuedPoint ? getPriceDeltaAmount(setValue, previousValuedPoint.setValue) : null;
      const fallbackDeltaPercent =
        setValue !== null && previousValuedPoint ? getPriceDeltaPercent(setValue, previousValuedPoint.setValue) : null;
      const nextPoint = {
        ...point,
        date: getHistoryDateKey(point?.date),
        setValue,
        index,
        deltaFromPrevious: explicitDeltaAmount ?? fallbackDeltaAmount,
        deltaPercentFromPrevious: explicitDeltaPercent ?? fallbackDeltaPercent,
      };

      if (setValue !== null) {
        previousValuedPoint = nextPoint;
      }

      return nextPoint;
    })
    .filter((point) => point.date);
  const valuedPoints = numericPoints.filter((point) => toNumber(point?.setValue) !== null);

  if (valuedPoints.length < 2) {
    return (
      <p className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)]/42 px-4 py-3 text-sm text-[var(--text-secondary)]">
        Not enough set value history yet. The trend chart appears after a few days of market observations.
      </p>
    );
  }

  const values = valuedPoints.map((point) => point.setValue);
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const range = maxValue - minValue || Math.max(maxValue, 1) * 0.08 || 1;
  const yAxisTicks = buildCurrencyTicks(valuedPoints);
  const yMin = Math.max(0, Math.min(...yAxisTicks, minValue - range * 0.14));
  const yMax = Math.max(...yAxisTicks, maxValue + range * 0.14);
  // One date system at every width: the first and last date of the visible
  // series, printed on the axis directly under the line they describe. The
  // every-day / preserveStartEnd desktop tick set and the external bookend-date
  // row it used to pair with are both gone — see minimalChartAxis.mjs.
  const edgeDateTicks = buildEdgeDateTicks(numericPoints, "date");
  const trendColor =
    trendDirection === "negative"
      ? NEGATIVE_VALUE_COLOR
      : trendDirection === "positive"
      ? POSITIVE_VALUE_COLOR
      : "rgba(148,163,184,0.9)";
  const fillGradientId = `set-value-fill-${chartId}`;
  const glowFilterId = `set-value-glow-${chartId}`;

  return (
    <div className="min-h-[clamp(220px,31dvh,280px)] w-full desk:min-h-[21rem]">
      <ChartFrame className="h-[clamp(220px,31dvh,280px)] w-full desk:h-[21rem]">
        <ResponsiveContainer width="100%" height="100%">
          {/* Shared insets: with the y-axis reserving no width at any size, a
              zero left margin would put the first data point exactly on x=0,
              where the SVG clips half its stroke and all of its 7px glow. */}
          {/* The completed mobile values become the shared ones, so the phone
              and tablet plot is byte-identical to before and desktop simply
              adopts it (it had top 12 / bottom 8 to sit under its old axis). */}
          <ComposedChart data={numericPoints} margin={getMinimalPlotMargin({ top: 6, bottom: 2 })}>
            <defs>
              <linearGradient id={fillGradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={trendColor} stopOpacity="0.13" />
                <stop offset="68%" stopColor={trendColor} stopOpacity="0.035" />
                <stop offset="100%" stopColor={trendColor} stopOpacity="0" />
              </linearGradient>
              <filter id={glowFilterId} x="-12%" y="-18%" width="124%" height="136%">
                <feGaussianBlur stdDeviation="1.8" />
              </filter>
            </defs>
            <Area
              type="linear"
              dataKey="setValue"
              baseValue={yMin}
              fill={`url(#${fillGradientId})`}
              stroke="none"
              dot={false}
              activeDot={false}
              legendType="none"
              tooltipType="none"
              isAnimationActive={false}
            />
            <CartesianGrid stroke="var(--border-subtle)" strokeOpacity={0.28} strokeDasharray="2 8" vertical={false} />
            {/* The two edge dates are the only dates, at every width, and they
                are anchored inward so the SVG cannot clip them. */}
            <XAxis
              dataKey="date"
              ticks={edgeDateTicks}
              tickLine={false}
              axisLine={false}
              tick={<ChartEdgeDateTick ticks={edgeDateTicks} formatter={(value) => formatShortDate(value) || ""} />}
              tickFormatter={(value) => formatShortDate(value) || ""}
              minTickGap={0}
              interval={0}
            />
            {/* Scale unchanged — the domain is still computed from the data and
                still drives the gridlines. Only the printed labels and the
                58px gutter they reserved are gone, so the series uses the full
                card width. Exact values stay available by hover and tap/scrub. */}
            <YAxis
              {...MINIMAL_Y_AXIS_PROPS}
              domain={[yMin, yMax]}
              tickCount={4}
              tickFormatter={formatAxisCurrency}
            />
            {/* Touch gets an explicit tap trigger: it persists after the finger
                lifts, and it binds click rather than touchmove, so scrolling
                past the chart can never select a random point. Mouse and
                trackpad keep hover at every width. */}
            <RechartsTooltip
              trigger={isCoarsePointer ? "click" : "hover"}
              content={<SetValueTooltip />}
              cursor={{ stroke: "rgba(255,255,255,0.16)", strokeWidth: 1 }}
            />
            <Line
              type="linear"
              dataKey="setValue"
              stroke={trendColor}
              strokeWidth={7}
              strokeOpacity={0.16}
              filter={`url(#${glowFilterId})`}
              dot={false}
              activeDot={false}
              legendType="none"
              tooltipType="none"
              isAnimationActive={false}
            />
            <Line
              type="linear"
              dataKey="setValue"
              name={`${scopeLabel} Set Value`}
              stroke={trendColor}
              strokeWidth={2.5}
              dot={{ r: 2.5, fill: trendColor, strokeWidth: 0 }}
              activeDot={{ r: 4.5, stroke: "var(--surface-page)", strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </ChartFrame>
    </div>
  );
}

function formatSegmentMoney(value, { compact = false } = {}) {
  const parsed = toNumber(value);
  if (parsed === null) return null;
  const dropCents = compact && Math.abs(parsed) >= 1000;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: dropCents ? 0 : 2,
    maximumFractionDigits: dropCents ? 0 : 2,
  }).format(parsed);
}

function formatSignedMoney(value) {
  const parsed = toNumber(value);
  if (parsed === null) return null;
  return `${parsed >= 0 ? "+" : "−"}${formatSegmentMoney(Math.abs(parsed))}`;
}

function formatSignedPercentValue(value) {
  const parsed = toNumber(value);
  if (parsed === null) return null;
  return `${parsed >= 0 ? "+" : "−"}${Math.abs(parsed).toFixed(1)}%`;
}

export function deltaToneClassName(value) {
  const parsed = toNumber(value);
  if (parsed === null || parsed === 0) return "text-[var(--text-secondary)]";
  return parsed > 0 ? "text-[var(--positive)]" : "text-[var(--negative)]";
}

/**
 * The set's sealed market, read once for the whole Market tab.
 *
 * The page already fetches Cards history and the movers windows; sealed is the
 * one lens whose payload nothing else on this tab has loaded. It reads the same
 * prepared snapshot endpoint the Sealed card used, so no new contract and no
 * client-side aggregation: `setMarket` is the canonical set-level series the
 * snapshot service publishes.
 */
/** One Market Segments row on the right rail. */
function MarketSegmentRow({ row, active, onSelect }) {
  const valueText = row.available ? formatSegmentMoney(row.currentValue, { compact: true }) : null;
  const amountText = row.available ? formatSignedMoney(row.deltaAmount) : null;
  const percentText = row.available ? formatSignedPercentValue(row.deltaPercent) : null;
  const className = `w-full min-w-0 rounded-xl border px-3 py-2.5 text-left transition-colors ${
    // CANONICAL MARKET GREEN, not the site's yellow --accent. This is the
    // same rgb(45,212,191) family Market Explorer's "Open Market Explorer"
    // CTA and the approved TimeRangeSelector already use for selection —
    // reused here rather than invented, so Set Market has one interaction
    // color instead of a second one.
    active ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,0.10)]" : "border-[var(--border-subtle)] bg-[var(--surface-page)]/55"
  } ${row.selectable ? "hover:border-[rgba(45,212,191,0.6)]" : "cursor-default opacity-70"}`;

  const body = (
    <>
      <div className="flex min-w-0 items-baseline justify-between gap-2">
        <span className="truncate text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
          {row.label}
        </span>
        {row.available ? (
          <span className={`flex-none text-[11px] font-semibold ${deltaToneClassName(row.deltaAmount)}`}>
            {percentText || "—"}
          </span>
        ) : null}
      </div>
      <div className="mt-1 flex min-w-0 items-baseline gap-2">
        <span className="truncate text-base font-semibold text-[var(--text-primary)]">
          {/* An unavailable lens prints an em dash. Never $0 — zero is a real
              price, and claiming it here would be a false reading. */}
          {valueText || "—"}
        </span>
        {row.available && amountText ? (
          <span className={`flex-none text-[11px] ${deltaToneClassName(row.deltaAmount)}`}>{amountText}</span>
        ) : null}
      </div>
      {row.available && row.marketIndexValue !== null && row.marketIndexValue !== undefined ? (
        <p className="mt-0.5 text-[11px] tabular-nums text-[var(--text-secondary)]">Index {Number(row.marketIndexValue).toFixed(2)}</p>
      ) : null}
      {!row.available ? (
        <p data-segment-unavailable className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
          {row.unavailableReason}
        </p>
      ) : null}
    </>
  );

  if (!row.selectable) {
    return (
      <div data-market-segment-row={row.key} data-segment-available="false" aria-disabled="true" className={className}>
        {body}
      </div>
    );
  }

  return (
    <button
      type="button"
      data-market-segment-row={row.key}
      data-segment-available="true"
      aria-pressed={active}
      onClick={() => onSelect?.(row.key)}
      className={className}
    >
      {body}
    </button>
  );
}

/** SECTION 2B — the right-hand signal rail. */
function SetSignalsRail({ segmentRows, activeSegmentKey, onSegmentChange, breadth, breadthStatus, concentration, windowLabel, sealedError, onSealedRetry, onSignalsRetry }) {
  return (
    <SectionCard title="Set Signals" className="h-full" bodySpacingClassName="mt-2">
      <div className="space-y-4">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
            Market Segments
          </p>
          <div className="mt-2 space-y-2">
            {segmentRows.map((row) => (
              <MarketSegmentRow key={row.key} row={row} active={row.key === activeSegmentKey} onSelect={onSegmentChange} />
            ))}
          </div>
        </div>

        {activeSegmentKey === "cards" || activeSegmentKey === "sealed" ? (
          <div>
            <MarketBreadthSignal
              breadth={breadthStatus ? { available: false, reason: breadthStatus } : breadth}
              windowLabel={windowLabel}
              itemNoun={activeSegmentKey === "sealed" ? "products" : "cards"}
              title={activeSegmentKey === "sealed" ? "Sealed Market Breadth" : "Card Market Breadth"}
              onRetry={activeSegmentKey === "cards" && onSignalsRetry ? onSignalsRetry : null}
              className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 px-3 py-3"
            />
            {activeSegmentKey === "sealed" && sealedError ? (
              <div className="mt-2 flex items-center justify-between gap-2 text-xs text-red-300">
                <span>{sealedError}</span>
                <button type="button" onClick={onSealedRetry} className="min-h-9 rounded-lg border border-[var(--border-subtle)] px-3 font-semibold text-[var(--text-primary)]">Retry</button>
              </div>
            ) : null}
          </div>
        ) : null}
        {activeSegmentKey === "cards" ? (
          <ChaseConcentrationSignal concentration={concentration} formatMoney={(value) => formatSegmentMoney(value, { compact: true })} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 px-3 py-3" />
        ) : null}
      </div>
    </SectionCard>
  );
}

/** SECTION 2A — the dominant Market Value Trend panel. */
function MarketValueTrendPanel({
  setId,
  segmentRows,
  activeSegmentKey,
  onSegmentChange,
  trend,
  onWindowChange,
  windowLabel,
  statusMessage = null,
}) {
  const chartKey = `${setId || "set"}-${activeSegmentKey}-${trend.effectiveWindowKey || "window"}-${trend.series.length}`;
  const details = useMemo(() => buildSupportingDetails(trend), [trend]);
  const trendDirection =
    trend.deltaAmount === null ? "neutral" : trend.deltaAmount < 0 ? "negative" : trend.deltaAmount > 0 ? "positive" : "neutral";

  return (
    <SectionCard
      title="Market Value Trend"
      titleInfoText="Three separate lenses on this set's market. Cards, Sealed and Graded are charted independently and are never summed into one set total."
      className="h-full"
      bodySpacingClassName="mt-2"
    >
      <div className="flex min-h-0 flex-col space-y-4">
        {/* Segment lenses. The active one carries the teal treatment. */}
        <div data-market-segment-tabs role="tablist" aria-label="Market segment" className="flex min-w-0 flex-wrap gap-1.5">
          {segmentRows.map((row) => (
            <button
              key={row.key}
              type="button"
              role="tab"
              data-market-segment-tab={row.key}
              aria-selected={row.key === activeSegmentKey}
              disabled={!row.selectable}
              onClick={() => onSegmentChange?.(row.key)}
              className={`min-h-9 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors ${
                row.key === activeSegmentKey
                  ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,0.12)] text-[rgb(45,212,191)]"
                  : "border-[var(--border-subtle)] bg-[var(--surface-page)]/55 text-[var(--text-secondary)]"
              } ${row.selectable ? "hover:border-[rgba(45,212,191,0.6)]" : "cursor-not-allowed opacity-50"}`}
            >
              {row.label}
            </button>
          ))}
        </div>

        {statusMessage ? (
          <div data-market-sealed-request-state className="rounded-xl border border-dashed border-[var(--border-subtle)] px-4 py-8 text-center text-sm text-[var(--text-secondary)]">
            {statusMessage}
          </div>
        ) : trend.available ? (
          <>
            <div data-market-trend-summary className="min-w-0">
              <MarketValueChange
                value={trend.currentValue}
                changeAmount={trend.deltaAmount}
                changePercent={trend.deltaPercent}
                windowLabel={windowLabel}
                variant="chart-summary"
                accessibleLabel={`Current ${MARKET_SEGMENT_LABELS[activeSegmentKey]} market value`}
              />
              <p data-market-trend-index className="text-[11px] font-medium leading-tight text-[var(--text-secondary)]">
                Market Index <span className="tabular-nums text-[var(--text-primary)]">{trend.marketIndexValue == null ? "—" : Number(trend.marketIndexValue).toFixed(2)}</span>
              </p>
            </div>

            <div className="flex min-w-0 items-center gap-2">
              <MarketWindowSelector
                windows={trend.availableDeltaWindows}
                value={trend.effectiveWindowKey}
                onChange={onWindowChange}
              />
            </div>

            {/* The graph dominates the panel; it is a chart, not a sparkline. */}
            <div data-market-trend-chart className="min-h-[20rem]">
              <SetValueLineChart
                key={chartKey}
                points={trend.series}
                trendDirection={trendDirection}
                scopeLabel={MARKET_SEGMENT_LABELS[activeSegmentKey]}
              />
            </div>
          </>
        ) : (
          <div
            data-market-trend-unavailable
            className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)]/42 px-4 py-8 text-center"
          >
            <p className="text-2xl font-semibold text-[var(--text-primary)]">—</p>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">{trend.unavailableReason || SEGMENT_UNAVAILABLE_TEXT}</p>
          </div>
        )}

        <div data-supporting-details>
          <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
            Supporting Details
          </p>
          <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
            {details.map((detail) => {
              let value = "—";
              let toneClassName = "text-[var(--text-primary)]";
              if ((detail.key === "periodHigh" || detail.key === "periodLow") && detail.value !== null) {
                value = formatSegmentMoney(detail.value, { compact: true });
              } else if (detail.key === "trackingSince" && detail.date) {
                value = formatLongDate(detail.date);
              } else if (detail.key === "trackedItems" && detail.count !== null) {
                value = `${detail.count.toLocaleString("en-US")} ${detail.noun}`;
              }
              return (
                <div key={detail.key} className="min-w-0" data-supporting-detail={detail.key}>
                  <dt className="truncate text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
                    {detail.label}
                  </dt>
                  <dd className={`mt-1 truncate text-sm font-semibold ${toneClassName}`}>{value}</dd>
                </div>
              );
            })}
          </dl>
        </div>
      </div>
    </SectionCard>
  );
}

/**
 * SECTION 2 — Main Market Overview.
 *
 * The chart takes roughly two thirds and the signal rail one third, which is
 * what makes this read as "one dominant chart with supporting signals" rather
 * than as two equal cards competing for the eye.
 */
export default function RichMarketOverviewSection({ setId, cardsHistory, cardsMarket, cardsTrackedCount, top10Value, standardValue, sealedSummaryState }) {
  const { canViewSetMarketSignals } = useSetMarketSignalAccess();
  const seededSignals = useMemo(() => cardsMarket?.marketBreadth ? {
    set: { id: setId }, marketBreadth: cardsMarket.marketBreadth,
  } : null, [cardsMarket?.marketBreadth, setId]);
  const signalsState = usePokemonSetMarketSignals(setId, {
    enabled: canViewSetMarketSignals,
    initialPayload: seededSignals,
  });
  const [activeSegmentKey, setActiveSegmentKey] = useState("cards");
  // Site convention: every market timeframe control opens on 7D. The reader
  // can still switch away; nothing here re-forces 7D after that.
  const [selectedWindowKey, setSelectedWindowKey] = useState("7D");

  const cardsTrend = useMemo(
    () => {
      if (cardsMarket?.available === false) {
        return unavailableSegmentTrend({
          reason: cardsMarket.reason || cardsMarket.status || SEGMENT_UNAVAILABLE_TEXT,
          trackedItemNoun: "Cards",
        });
      }
      return selectPreparedSegmentTrend({
        valueHistory: cardsHistory,
        marketIndex: cardsMarket?.marketIndex || cardsMarket?.market_index,
        selectedWindowKey,
        trackedItemCount: cardsTrackedCount,
        trackedItemNoun: "Cards",
      });
    },
    [cardsHistory, cardsMarket, cardsTrackedCount, selectedWindowKey]
  );

  const sealedTrend = useMemo(() => {
    const setMarket = sealedSummaryState.payload?.setPageConsumerMarket || null;
    if (!setMarket?.history?.length) {
      return unavailableSegmentTrend({ trackedItemNoun: "Sealed Products" });
    }
    return selectPreparedSegmentTrend({
      valueHistory: setMarket.history,
      marketIndex: setMarket.marketIndex || setMarket.market_index,
      selectedWindowKey,
      trackedItemCount: setMarket.productCount,
      trackedItemNoun: "Sealed Products",
    });
  }, [sealedSummaryState.payload, selectedWindowKey]);

  // GRADED. The product publishes no graded market series for a set — the only
  // graded prices that exist anywhere are per-user collection valuations, which
  // are not a set-level market. The lens is therefore rendered as genuinely
  // unavailable rather than fabricated from unrelated data or shown as $0.
  const gradedTrend = useMemo(() => unavailableSegmentTrend({ trackedItemNoun: "Graded Cards" }), []);

  const trendsByKey = useMemo(
    () => ({ cards: cardsTrend, sealed: sealedTrend, graded: gradedTrend }),
    [cardsTrend, gradedTrend, sealedTrend]
  );
  const resolvedSegmentKey = activeSegmentKey === "sealed" && ["idle", "loading", "error"].includes(sealedSummaryState.status)
    ? "sealed"
    : resolveActiveSegmentKey(activeSegmentKey, trendsByKey);
  const activeTrend = trendsByKey[resolvedSegmentKey] || cardsTrend;
  const segmentRows = useMemo(
    () => buildMarketSegmentRows(trendsByKey).map((row) => row.key === "sealed" && ["idle", "loading", "error"].includes(sealedSummaryState.status) ? { ...row, selectable: true, unavailableReason: sealedSummaryState.status === "error" ? sealedSummaryState.error : "Loading Sealed marketâ€¦" } : row),
    [sealedSummaryState.status, trendsByKey]
  );
  const effectiveWindowKey = activeTrend.effectiveWindowKey || selectedWindowKey;
  const windowLabel = getDeltaWindowLabel(effectiveWindowKey) || "Trend";

  const breadthSource = resolvedSegmentKey === "sealed"
    ? sealedSummaryState.payload?.setPageConsumerMarket?.marketBreadth || sealedSummaryState.payload?.setPageConsumerMarket?.market_breadth
    : resolvedSegmentKey === "cards"
    ? signalsState.payload?.marketBreadth
    : resolvedSegmentKey === "cards" && signalsState.status === "loading" ? "Loading Market Breadthâ€¦"
    : resolvedSegmentKey === "cards" && ["error", "forbidden"].includes(signalsState.status) ? signalsState.error
    : null;
  const breadth = useMemo(
    () => selectPreparedMarketBreadth({
      marketBreadth: breadthSource,
      windowKey: effectiveWindowKey,
      totalTrackedCount: activeTrend.trackedItemCount,
    }),
    [activeTrend.trackedItemCount, breadthSource, effectiveWindowKey]
  );
  const breadthStatus = resolvedSegmentKey === "sealed" && sealedSummaryState.status === "loading" && !sealedSummaryState.payload
    ? "Loading Sealed market…"
    : resolvedSegmentKey === "sealed" && sealedSummaryState.status === "error" && !sealedSummaryState.payload
    ? sealedSummaryState.error || "Unable to load sealed market breadth"
    : null;
  // INDEPENDENT of cardsTrend: Chase Concentration only needs the current
  // Standard and Top 10 set-value scopes, not a full Cards Market Index
  // history — see the prop's own comment at the call site.
  const concentration = useMemo(
    () => selectChaseConcentration({ top10Value, cardsValue: standardValue }),
    [standardValue, top10Value]
  );

  return (
    <div className="grid min-w-0 grid-cols-1 gap-5 desk:grid-cols-[minmax(0,67fr)_minmax(0,33fr)]">
      <div className="min-w-0">
        <MarketValueTrendPanel
          setId={setId}
          segmentRows={segmentRows}
          activeSegmentKey={resolvedSegmentKey}
          onSegmentChange={(key) => { if (key === "sealed") sealedSummaryState.load?.(); setActiveSegmentKey(key); }}
          trend={activeTrend}
          onWindowChange={setSelectedWindowKey}
          windowLabel={windowLabel}
          statusMessage={resolvedSegmentKey === "sealed" && ["idle", "loading"].includes(sealedSummaryState.status)
            ? "Loading Sealed marketâ€¦"
            : resolvedSegmentKey === "sealed" && sealedSummaryState.status === "error"
            ? sealedSummaryState.error || "Unable to load Sealed market summary"
            : null}
        />
      </div>
      <div className="min-w-0">
        <SetSignalsRail
          segmentRows={segmentRows}
          activeSegmentKey={resolvedSegmentKey}
          onSegmentChange={(key) => { if (key === "sealed") sealedSummaryState.load?.(); setActiveSegmentKey(key); }}
          breadth={breadth}
          breadthStatus={breadthStatus}
          concentration={concentration}
          windowLabel={windowLabel}
          sealedError={resolvedSegmentKey === "sealed" && sealedSummaryState.status === "error" ? sealedSummaryState.error : null}
          onSealedRetry={sealedSummaryState.retry}
          onSignalsRetry={["error", "forbidden"].includes(signalsState.status) ? signalsState.retry : null}
        />
      </div>
    </div>
  );
}

/**
 * SECTION 3 — Top 10 Chase Cards.
 *
 * Left: the ranked list. Right: the selected card, in TWO stacked zones —
 * Zone A is the detail (artwork plus metadata, side by side), Zone B is the
 * price graph spanning the full width beneath it.
 *
 * The artwork lives in Zone A only. It deliberately does NOT run down the side
 * of the graph: an image column beside a chart forces the chart into a narrow
 * strip and forces the card to stretch to fill a tall thin box. Stacking gives
 * the chart its full width and lets the card keep its real proportions.
 *
 * There is NO movers strip in here. 7D movers is Section 1's job, and repeating
 * it would make the reader check two places for one answer.
 */
function SectionEyebrow({ children }) {
  if (!children) return null;
  return <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">{children}</p>;
}

const SECTION_CARD_MOBILE_FLUSH_CLASS =
  "max-desk:rounded-none max-desk:border-0 max-desk:bg-transparent max-desk:p-0 max-desk:shadow-none max-desk:[backdrop-filter:none]";

export function SectionCard({
  title,
  subtitle,
  titleInfoText,
  eyebrow = null,
  tone = "default",
  children,
  className = "",
  bodyClassName = "",
  bodySpacingClassName = "mt-4",
  mobileFlush = false,
}) {
  // A flush card states its 1200px+ inset with `desk:p-5`, not `sm:p-5`.
  // `max-desk:` utilities are emitted BEFORE `sm:` in the stylesheet and both
  // are !important, so an sm-scoped inset wins back 640-1199px and the card
  // would still look inset on a tablet — the only band where the reset appears
  // to do nothing. The two produce the identical p-5 at 1200px+; they differ
  // only in the band that is supposed to be flush. Callers that keep their card
  // are untouched.
  const insetClass = mobileFlush ? "p-4 desk:p-5" : "p-4 sm:p-5";
  const toneClass =
    tone === "plain"
      ? `rounded-2xl border border-[var(--border-subtle)] ${insetClass}`
      : `rounded-2xl border border-[var(--border-subtle)] ${insetClass}`;
  return (
    <article
      className={["set-glass-surface w-full max-w-full min-w-0", toneClass, mobileFlush ? SECTION_CARD_MOBILE_FLUSH_CLASS : "", className]
        .filter(Boolean)
        .join(" ")}
    >
      <div>
        <SectionEyebrow>{eyebrow}</SectionEyebrow>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <h2 className="min-w-0 max-w-full text-lg font-semibold text-[var(--text-primary)]">{title}</h2>
          {titleInfoText ? <InfoPopover text={titleInfoText} /> : null}
        </div>
        {subtitle ? <p className="mt-1 min-w-0 max-w-full text-sm text-[var(--text-secondary)]">{subtitle}</p> : null}
      </div>
      <div className={[bodySpacingClassName, "min-w-0 max-w-full", bodyClassName].filter(Boolean).join(" ")}>{children}</div>
    </article>
  );
}

// ---------------------------------------------------------------------------
// THE PUBLIC COLLECTOR PROFILE WAS REMOVED HERE
//
// `CollectorProfileSection` and everything it exclusively owned - the Roster
// Appeal / Opening Paths view tabs, the desktop and mobile roster panels, the
// desktop and mobile opening-path panels, their loading/unavailable wrappers,
// the CollectorPanel/CollectorBand/CollectorMetric* primitives, the
// OpeningPathStepArrow and the path presentation helpers, and the whole
// COLLECTOR_PROFILE_* / SET_DESIRABILITY_* / ROSTER_QUALITY_* /
// DEMAND_DISTRIBUTION_* / OPENING_PATH_SUMMARY_* info-copy set - are gone.
// Every one of them had no consumer outside this block.
//
// WHY: the section presented the retired chain
//     Set Desirability -> Collector Appeal -> RIP Score Contribution
// as the current model. Collector Appeal V3 has THREE PARALLEL FACTORS, not a
// sequential pipeline with roster demand as its first stage, and the section's
// copy stated composition weights and contribution points that are internal to
// the model. Its info bullets also carried the "one of the two halves of RIP
// Score" claim, which the canonical 0.90/0.10 blend does not support.
//
// The canonical Collector Appeal presentation is CollectorAppealBreakdown,
// rendered exactly once inside the RIP Score section above. Every deep link
// this section used to own is relocated there as a compatibility anchor - see
// SET_DETAIL_SECTION_TARGETS and COLLECTOR_APPEAL_SECTION_ID.
//
// NO BACKEND DATA WAS REMOVED. `universalSetDesirability` and
// `openingExperience` are still published and still read elsewhere on the page;
// this block simply stopped rendering a superseded story about them.
// ---------------------------------------------------------------------------
