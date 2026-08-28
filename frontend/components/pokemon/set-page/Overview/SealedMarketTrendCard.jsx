"use client";

import { useCallback, useEffect, useId, useMemo, useState } from "react";
import { Area, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import ChartEdgeDateTick from "@/components/explore/ChartEdgeDateTick";
import ChartFrame from "@/components/explore/ChartFrame";
import MarketWindowSelector from "@/components/explore/MarketWindowSelector";
import MarketTrendTooltipCard from "@/components/explore/MarketTrendTooltipCard";
import { MINIMAL_Y_AXIS_PROPS, buildEdgeDateTicks, getMinimalPlotMargin } from "@/components/explore/minimalChartAxis.mjs";
import InfoPopover from "@/components/ui/InfoPopover";
import MarketValueChange from "@/components/ui/MarketValueChange";
import usePointerMode, { POINTER_MODE_COARSE } from "@/hooks/usePointerMode";
import { NEGATIVE_VALUE_COLOR, POSITIVE_VALUE_COLOR } from "@/lib/explore/interpretationTone";
import { getPokemonSetSealedMarket } from "@/lib/pokemon/pokemonSetMarketClient";
import Link from "next/link";
import { buildSealedProductHref } from "@/lib/pokemon/sealedProductRoutes";
import SealedProductPicker from "./SealedProductPicker";
import { SEALED_MARKET_WINDOWS, getDisplayedTrendDirection, selectSealedProduct, selectSealedWindow, sortSealedProductsByCurrentPrice } from "./sealedMarketTrendSelector.mjs";

const INFO = "Tracks market-price history for unopened sealed products associated with this set. This first version does not include promo-card value, pack contents, or opening expected value.";
const shortDate = (value) => value ? new Date(`${value}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "";
const WINDOW_NAMES = { "1D": "1 day", "7D": "7 days", "30D": "30 days", "3M": "3 months", "6M": "6 months", "1Y": "1 year", lifetime: "lifetime" };
const NEUTRAL_MARKET_COLOR = "rgba(148,163,184,0.9)";

function SealedMarketTooltip({ active, payload }) {
  const row = active && payload?.[0]?.payload;
  if (!row) return null;
  return (
    <MarketTrendTooltipCard
      date={row.date}
      value={row.marketPrice}
      deltaAmount={row.deltaFromWindowStart}
      deltaPercent={row.deltaPercentFromWindowStart}
      accessibleLabel="Market price at selected date"
    />
  );
}

export default function SealedMarketTrendCard({ setId }) {
  const [state, setState] = useState({ status: "idle", payload: null, error: null });
  const [selectedId, setSelectedId] = useState(null);
  const [windowKey, setWindowKey] = useState("30D");
  const [retryKey, setRetryKey] = useState(0);
  // Only used to lift the card while its menu is open — see the section below.
  const [pickerOpen, setPickerOpen] = useState(false);
  const pointerMode = usePointerMode();
  const chartId = useId().replace(/:/g, "");
  const gradientId = `sealed-market-fill-${chartId}`;
  const glowId = `sealed-market-glow-${chartId}`;
  const retry = useCallback(() => setRetryKey((value) => value + 1), []);

  useEffect(() => {
    let active = true;
    setState({ status: "loading", payload: null, error: null });
    setSelectedId(null);
    setWindowKey("30D");
    getPokemonSetSealedMarket(setId).then(
      (payload) => active && setState({ status: payload?.products?.length ? "success" : "empty", payload, error: null }),
      (error) => active && setState({ status: error?.status === 404 ? "empty" : "error", payload: null, error })
    );
    return () => { active = false; };
  }, [setId, retryKey]);

  // One price-descending array drives both the option order and the default
  // selection, so the showcased product is always the first option listed.
  const orderedProducts = useMemo(
    () => sortSealedProductsByCurrentPrice(state.payload?.products),
    [state.payload],
  );
  const product = useMemo(() => selectSealedProduct(state.payload, selectedId), [state.payload, selectedId]);
  const selected = useMemo(() => selectSealedWindow(product, windowKey), [product, windowKey]);
  const chartHistory = useMemo(() => {
    const firstPrice = Number(selected.history?.[0]?.marketPrice);
    return (selected.history || []).map((point) => {
      const value = Number(point.marketPrice);
      const amount = Number.isFinite(value) && Number.isFinite(firstPrice) ? value - firstPrice : null;
      return {
        ...point,
        deltaFromWindowStart: amount,
        deltaPercentFromWindowStart: amount !== null && firstPrice !== 0 ? amount / firstPrice * 100 : null,
      };
    });
  }, [selected.history]);
  const ticks = buildEdgeDateTicks(chartHistory, "date");
  const fallbackDescription = selected.isFallback
    ? `${WINDOW_NAMES[selected.requestedWindowKey]} view selected; showing ${WINDOW_NAMES[selected.effectiveWindowKey]} because ${WINDOW_NAMES[selected.requestedWindowKey]} of history are not available yet.`
    : undefined;
  const trendDirection = getDisplayedTrendDirection(selected.movement);
  const trendColor = trendDirection === "positive"
    ? POSITIVE_VALUE_COLOR
    : trendDirection === "negative"
      ? NEGATIVE_VALUE_COLOR
      : NEUTRAL_MARKET_COLOR;

  return (
    /* The card clipped its own dropdown. `overflow-hidden` existed to keep the
       chart inside the rounded corners, but it also cropped the product menu at
       the card edge, so the clip moves onto the ChartFrame (which is what
       actually needs it) and the card goes overflow-visible.
       `.set-glass-surface` carries a backdrop-filter on desktop, which creates a
       stacking context the menu's z-50 cannot escape — so while the menu is
       open the whole card is raised above its later siblings (Decision Signals
       follows it in DOM order and would otherwise paint over the menu). */
    <section
      data-sealed-market-card
      data-picker-open={pickerOpen ? "true" : "false"}
      className={`set-glass-surface relative min-w-0 overflow-visible rounded-2xl border border-[var(--border-subtle)] p-4 ${pickerOpen ? "z-50" : ""}`}
    >
      <div className="flex items-center gap-2">
        <h2 className="text-lg font-semibold leading-normal text-[var(--text-primary)]">Sealed Market</h2>
        <InfoPopover text={INFO} />
      </div>
      {state.status === "loading" ? (
        <div className="mt-4 h-[11rem] animate-pulse rounded-xl bg-[rgba(148,163,184,0.08)]" aria-label="Loading sealed market history" />
      ) : state.status === "error" ? (
        <div className="flex min-h-[11rem] flex-col items-center justify-center gap-3 text-center text-sm text-[var(--text-secondary)]">
          <p>Unable to load sealed market history.</p>
          <button type="button" onClick={retry} className="rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-[var(--text-primary)]">Retry</button>
        </div>
      ) : !product ? (
        <p className="flex min-h-[11rem] items-center justify-center text-center text-sm text-[var(--text-secondary)]">Sealed market history is not available for this set yet.</p>
      ) : (
        <>
          {/* Order is deliberate: the market value is the insight, so it leads.
              The product is the analytical subject and the window is a filter
              applied to it, so the stack reads value → product → time → chart.
              One DOM order for every breakpoint — no CSS `order` utilities and
              no second composition. 12px between each layer. */}
          <div data-sealed-market-summary className="mt-3">
            <MarketValueChange
              value={product.currentPrice}
              changeAmount={selected.movement.amount}
              changePercent={selected.movement.percent}
              unavailable={selected.movement.status !== "available"}
              windowLabel={selected.effectiveWindowKey}
              variant="chart-summary"
              accessibleLabel={`${product.name} market price`}
            />
            {fallbackDescription ? <span className="sr-only">{fallbackDescription}</span> : null}
          </div>
          <SealedProductPicker
            products={orderedProducts}
            value={product.sealedProductId}
            onChange={setSelectedId}
            onOpenChange={setPickerOpen}
          />
          <Link href={buildSealedProductHref(product)} className="mt-2 inline-flex text-xs font-semibold text-[var(--accent)] hover:underline">
            View Product <span aria-hidden="true" className="ml-1">→</span>
          </Link>
          <MarketWindowSelector
            windows={SEALED_MARKET_WINDOWS}
            value={windowKey}
            onChange={setWindowKey}
            fullWidth
            className="mt-3"
            ariaDescription={fallbackDescription}
          />
          <ChartFrame className="mt-3 h-32 overflow-hidden rounded-xl md:h-36 lg:h-32">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartHistory} margin={getMinimalPlotMargin({ top: 6, bottom: 2 })}>
                <defs>
                  <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={trendColor} stopOpacity="0.13" />
                    <stop offset="68%" stopColor={trendColor} stopOpacity="0.035" />
                    <stop offset="100%" stopColor={trendColor} stopOpacity="0" />
                  </linearGradient>
                  <filter id={glowId} x="-12%" y="-18%" width="124%" height="136%">
                    <feGaussianBlur stdDeviation="1.8" />
                  </filter>
                </defs>
                <Area type="linear" dataKey="marketPrice" baseValue="dataMin" fill={`url(#${gradientId})`} stroke="none" dot={false} activeDot={false} legendType="none" tooltipType="none" isAnimationActive={false} />
                <XAxis dataKey="date" ticks={ticks} tick={<ChartEdgeDateTick ticks={ticks} formatter={shortDate} />} tickLine={false} axisLine={false} interval={0} />
                <YAxis {...MINIMAL_Y_AXIS_PROPS} domain={["dataMin", "dataMax"]} />
                <Tooltip
                  trigger={pointerMode === POINTER_MODE_COARSE ? "click" : "hover"}
                  content={<SealedMarketTooltip />}
                  cursor={{ stroke: "rgba(255,255,255,0.16)", strokeWidth: 1 }}
                />
                <Line type="linear" dataKey="marketPrice" stroke={trendColor} strokeWidth={7} strokeOpacity={0.16} filter={`url(#${glowId})`} dot={false} activeDot={false} legendType="none" tooltipType="none" isAnimationActive={false} />
                <Line type="linear" dataKey="marketPrice" stroke={trendColor} strokeWidth={2.5} dot={{ r: 2.5, fill: trendColor, strokeWidth: 0 }} activeDot={{ r: 4.5, fill: trendColor, stroke: "var(--surface-page)", strokeWidth: 2 }} isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </ChartFrame>
          <p className="mt-1 text-[10px] text-[var(--text-secondary)]">As of {shortDate(product.priceAsOf)} · Unopened market price only</p>
        </>
      )}
    </section>
  );
}
