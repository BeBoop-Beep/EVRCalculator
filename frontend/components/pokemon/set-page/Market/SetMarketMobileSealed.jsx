"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";

import MarketMobileSection from "./MarketMobileSection.jsx";
import MarketMobileChart from "./MarketMobileChart.jsx";
import MarketWindowSelector from "@/components/explore/MarketWindowSelector";
import MarketValueChange from "@/components/ui/MarketValueChange";
import InfoPopover from "@/components/ui/InfoPopover";
import { getPokemonSetSealedMarket } from "@/lib/pokemon/pokemonSetMarketClient";
import { resolvePokemonBoosterPackAsset } from "@/lib/pokemon/pokemonBoosterPackAssets.mjs";
import {
  SEALED_MARKET_WINDOWS,
  compactSealedProductLabel,
  getDisplayedTrendDirection,
  selectSealedProduct,
  selectSealedWindow,
  sortSealedProductsByCurrentPrice,
} from "../Overview/sealedMarketTrendSelector.mjs";
import { buildSealedMetrics, buildSealedProductChips } from "./setMarketMobileModel.mjs";

// ---------------------------------------------------------------------------
// Sealed Market — a product detail view, not a footnote.
//
// The desktop card hides product switching behind a dropdown because it shares
// a narrow third of a row with two other modules. On a phone the section owns
// the full width, so the products become what they actually are: a small set of
// peers you flick between. Chips make the count visible at a glance ("this set
// has four tracked products"), which a closed dropdown cannot.
//
// DATA. Identical to the desktop card: the same slim /market/sealed request,
// the same `selectSealedProduct` / `selectSealedWindow` selectors, the same
// fallback-window semantics. Product ordering is price-descending, so the chip
// row leads with the showcased product.
//
// METRICS. The published sealed contract carries price history, a current
// price, an as-of date and per-window movements — and nothing else. The metrics
// strip therefore reports the window's low and high, the number of observed
// days behind it, and how many sealed products this set tracks. There is no
// population, print run or market-cap figure in this contract, so no cell
// claims one. `buildSealedMetrics` drops any reading that resolves to null, and
// the strip is extensible: richer sealed metrics become extra entries there
// without touching this layout.
// ---------------------------------------------------------------------------

const INFO =
  "Tracks market-price history for unopened sealed products associated with this set. This first version does not include promo-card value, pack contents, or opening expected value.";

const WINDOW_NAMES = { "1D": "1 day", "7D": "7 days", "30D": "30 days", "3M": "3 months", "6M": "6 months", "1Y": "1 year", lifetime: "lifetime" };
const PACK_FAMILIES = new Set(["loose_booster_pack", "sleeved_booster_pack"]);

const shortDate = (value) =>
  value ? new Date(`${String(value).slice(0, 10)}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : null;

/**
 * The product's own art, or an honest stand-in. Real booster-pack photography
 * exists in the local registry and IS the product for the pack families, so it
 * is used for them. No other sealed family has published artwork in this
 * contract, and dressing an ETB in a pack photo would be a lie — those render a
 * neutral family monogram instead.
 */
function SealedProductArt({ product, packAsset }) {
  const usePackArt = packAsset && PACK_FAMILIES.has(String(product?.productFamily || ""));
  return (
    <span className="flex h-[5.25rem] w-[4rem] flex-none items-center justify-center overflow-hidden rounded-lg border border-[rgba(255,255,255,0.08)] bg-[rgba(2,6,23,0.5)] shadow-[0_10px_24px_rgba(2,6,23,0.4)]">
      {usePackArt ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={packAsset.src} alt="" className="h-full w-full object-cover" loading="lazy" decoding="async" />
      ) : (
        <span className="px-1 text-center text-[9px] font-bold uppercase leading-tight tracking-[0.06em] text-[var(--text-secondary)]">
          {compactSealedProductLabel(product)}
        </span>
      )}
    </span>
  );
}

export default function SetMarketMobileSealed({ id, setId, canonicalSetKey = null }) {
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
    return () => {
      active = false;
    };
  }, [setId, retryKey]);

  const orderedProducts = useMemo(() => sortSealedProductsByCurrentPrice(state.payload?.products), [state.payload]);
  const chips = useMemo(() => buildSealedProductChips(orderedProducts), [orderedProducts]);
  const product = useMemo(() => selectSealedProduct(state.payload, selectedId), [state.payload, selectedId]);
  const selected = useMemo(() => selectSealedWindow(product, windowKey), [product, windowKey]);
  const packAsset = useMemo(() => resolvePokemonBoosterPackAsset(canonicalSetKey), [canonicalSetKey]);
  const metrics = useMemo(
    () =>
      buildSealedMetrics({
        history: selected.history,
        windowLabel: selected.effectiveWindowKey,
        productCount: orderedProducts.length,
      }),
    [orderedProducts.length, selected.effectiveWindowKey, selected.history]
  );

  const fallbackDescription = selected.isFallback
    ? `${WINDOW_NAMES[selected.requestedWindowKey]} view selected; showing ${WINDOW_NAMES[selected.effectiveWindowKey]} because ${WINDOW_NAMES[selected.requestedWindowKey]} of history are not available yet.`
    : undefined;
  const asOfText = shortDate(product?.priceAsOf);

  return (
    <MarketMobileSection
      id={id}
      eyebrow="Unopened Product"
      title="Sealed Market"
      headerAside={<InfoPopover text={INFO} />}
    >
      {state.status === "loading" ? (
        <div className="space-y-3" aria-hidden="true">
          <div className="h-11 w-full animate-pulse rounded-lg bg-[rgba(148,163,184,0.08)]" />
          <div className="h-[5.75rem] w-full animate-pulse rounded-xl bg-[rgba(148,163,184,0.08)]" />
          <div className="h-[10rem] w-full animate-pulse rounded-xl bg-[rgba(148,163,184,0.08)]" />
        </div>
      ) : state.status === "error" ? (
        <div className="flex flex-col items-start gap-2">
          <p className="text-[13px] text-red-300">Unable to load sealed market history.</p>
          <button
            type="button"
            onClick={retry}
            className="inline-flex min-h-11 items-center rounded-lg border border-[var(--border-subtle)] bg-[rgba(255,255,255,0.04)] px-3 text-xs font-semibold text-[var(--text-primary)]"
          >
            Retry
          </button>
        </div>
      ) : !product ? (
        <p className="text-[13px] text-[var(--text-secondary)]">Sealed market history is not available for this set yet.</p>
      ) : (
        <div className="space-y-3">
          {/* Product switching. One product means no choice to offer, so the
              chip row is omitted entirely rather than rendering a single
              permanently-selected pill that looks like a broken control. */}
          {chips.length > 1 ? (
            <div
              role="radiogroup"
              aria-label="Sealed product"
              data-market-mobile-sealed-products
              className="-mx-3.5 flex gap-2 overflow-x-auto px-3.5 pb-0.5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
            >
              {chips.map((chip) => {
                const isActive = String(product.sealedProductId) === chip.id;
                return (
                  <button
                    key={chip.id}
                    type="button"
                    role="radio"
                    aria-checked={isActive}
                    onClick={() => setSelectedId(chip.id)}
                    className={[
                      "inline-flex min-h-11 flex-none items-center gap-1.5 whitespace-nowrap rounded-full border px-3 text-[11.5px] font-semibold transition-colors",
                      "focus:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)]",
                      isActive
                        ? "border-[rgba(45,212,191,0.34)] bg-[rgba(45,212,191,0.10)] text-[rgb(45,212,191)]"
                        : "border-[var(--border-subtle)] bg-[var(--surface-page)]/42 text-[var(--text-secondary)]",
                    ].join(" ")}
                  >
                    {chip.label}
                  </button>
                );
              })}
            </div>
          ) : null}

          <div className="flex min-w-0 items-center gap-3">
            <SealedProductArt product={product} packAsset={packAsset} />
            <div className="min-w-0 flex-1">
              <p className="line-clamp-2 text-[12.5px] font-semibold leading-tight text-[var(--text-primary)]">
                {compactSealedProductLabel(product)}
              </p>
              <div className="mt-1.5">
                <MarketValueChange
                  value={product.currentPrice}
                  changeAmount={selected.movement.amount}
                  changePercent={selected.movement.percent}
                  unavailable={selected.movement.status !== "available"}
                  windowLabel={selected.effectiveWindowKey === "lifetime" ? "LT" : selected.effectiveWindowKey}
                  variant="chart-summary"
                  accessibleLabel={`${product.name} market price`}
                />
              </div>
              {fallbackDescription ? <span className="sr-only">{fallbackDescription}</span> : null}
            </div>
          </div>

          <MarketWindowSelector
            windows={SEALED_MARKET_WINDOWS}
            value={windowKey}
            onChange={setWindowKey}
            fullWidth
            ariaDescription={fallbackDescription}
          />

          <MarketMobileChart
            key={`${product.sealedProductId}:${selected.effectiveWindowKey}`}
            points={selected.history}
            valueKey="marketPrice"
            trendDirection={getDisplayedTrendDirection(selected.movement)}
            seriesLabel={`${compactSealedProductLabel(product)} market price`}
            heightClassName="h-[clamp(168px,22dvh,208px)]"
            emptyMessage="Not enough sealed price history in this window yet."
          />

          {metrics.length > 0 ? (
            <div
              data-market-mobile-sealed-metrics
              className="grid grid-cols-2 gap-2"
            >
              {metrics.map((metric) => (
                <div
                  key={metric.key}
                  className="min-w-0 rounded-lg border border-[var(--border-subtle)] bg-[rgba(8,17,31,0.34)] px-2.5 py-2"
                >
                  <p className="truncate text-[9.5px] font-bold uppercase leading-none tracking-[0.11em] text-[rgba(199,214,234,0.6)]">
                    {metric.label}
                  </p>
                  <p className="mt-1.5 truncate text-[13px] font-semibold leading-tight tabular-nums text-[var(--text-primary)]">
                    {metric.value}
                  </p>
                </div>
              ))}
            </div>
          ) : null}

          {asOfText ? (
            <p className="text-[10px] text-[var(--text-secondary)]">{`As of ${asOfText} · Unopened market price only`}</p>
          ) : null}
        </div>
      )}
    </MarketMobileSection>
  );
}
