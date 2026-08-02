"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import ChartEdgeDateTick from "@/components/explore/ChartEdgeDateTick";
import ChartFrame from "@/components/explore/ChartFrame";
import MarketWindowSelector from "@/components/explore/MarketWindowSelector";
import { MINIMAL_Y_AXIS_PROPS, buildEdgeDateTicks, getMinimalPlotMargin } from "@/components/explore/minimalChartAxis.mjs";
import InfoPopover from "@/components/ui/InfoPopover";
import MarketValueChange from "@/components/ui/MarketValueChange";
import { POSITIVE_VALUE_COLOR } from "@/lib/explore/interpretationTone";
import { getPokemonSetSealedMarket } from "@/lib/pokemon/pokemonSetMarketClient";
import { SEALED_MARKET_WINDOWS, compactSealedProductLabel, selectSealedProduct, selectSealedWindow } from "./sealedMarketTrendSelector.mjs";

const INFO = "Tracks market-price history for unopened sealed products associated with this set. This first version does not include promo-card value, pack contents, or opening expected value.";
const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const shortDate = (value) => value ? new Date(`${value}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "";

export default function SealedMarketTrendCard({ setId }) {
  const [state, setState] = useState({ status: "idle", payload: null, error: null });
  const [selectedId, setSelectedId] = useState(null);
  const [windowKey, setWindowKey] = useState("30D");
  const [retryKey, setRetryKey] = useState(0);
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

  const product = useMemo(() => selectSealedProduct(state.payload, selectedId), [state.payload, selectedId]);
  const selected = useMemo(() => selectSealedWindow(product, windowKey), [product, windowKey]);
  const ticks = buildEdgeDateTicks(selected.history, "date");

  return (
    <section data-sealed-market-card className="set-glass-surface min-w-0 overflow-hidden rounded-2xl border border-[var(--border-subtle)] p-4">
      <div className="flex items-center gap-2">
        <h2 className="text-lg font-semibold leading-normal text-[var(--text-primary)] desk:text-sm">Sealed Market</h2>
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
          <label className="mt-3 block min-w-0">
            <span className="sr-only">Sealed product</span>
            <select
              value={product.sealedProductId}
              onChange={(event) => setSelectedId(event.target.value)}
              title={product.name}
              className="h-10 w-full min-w-0 truncate rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-2 text-xs text-[var(--text-primary)]"
            >
              {state.payload.products.map((item) => <option key={item.sealedProductId} value={item.sealedProductId} title={item.name}>{compactSealedProductLabel(item)} — {item.name}</option>)}
            </select>
          </label>
          <p className="mt-2 truncate text-xs text-[var(--text-secondary)]" title={product.name}>{product.name}</p>
          <div className="mt-2">
            <MarketValueChange
              value={product.currentPrice}
              changeAmount={selected.movement.amount}
              changePercent={selected.movement.percent}
              unavailable={selected.movement.status !== "available"}
              windowLabel={windowKey}
              variant="chart-summary"
              accessibleLabel={`${product.name} market price`}
            />
          </div>
          <MarketWindowSelector
            windows={SEALED_MARKET_WINDOWS}
            value={windowKey}
            onChange={setWindowKey}
            fullWidth
            className="mt-2"
          />
          <ChartFrame className="mt-2 h-32 md:h-36 lg:h-32">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={selected.history} margin={getMinimalPlotMargin({ top: 8, bottom: 16 })}>
                <XAxis dataKey="date" ticks={ticks} tick={<ChartEdgeDateTick ticks={ticks} formatter={shortDate} />} tickLine={false} axisLine={false} interval={0} />
                <YAxis {...MINIMAL_Y_AXIS_PROPS} domain={["dataMin", "dataMax"]} />
                <Tooltip formatter={(value) => [money.format(value), "Market price"]} labelFormatter={shortDate} />
                <Line type="monotone" dataKey="marketPrice" stroke={POSITIVE_VALUE_COLOR} strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </ChartFrame>
          <p className="mt-1 text-[10px] text-[var(--text-secondary)]">As of {shortDate(product.priceAsOf)} · Unopened market price only</p>
        </>
      )}
    </section>
  );
}
