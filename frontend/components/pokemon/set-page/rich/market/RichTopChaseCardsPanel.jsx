"use client";

import { useCallback, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import DeltaTrendIcon from "@/components/ui/DeltaTrendIcon";
import MarketValueChange from "@/components/ui/MarketValueChange";
import MarketWindowSelector from "@/components/explore/MarketWindowSelector";
import { buildPokemonCardHref } from "@/lib/pokemon/pokemonCardDetailClient";
import { buildSealedProductHref } from "@/components/explore/setProductComparison.mjs";
import { getDeltaWindowLabel } from "@/lib/explore/marketDeltaWindows.mjs";
import { selectSegmentTrend, unavailableSegmentTrend, SEGMENT_UNAVAILABLE_TEXT } from "@/components/pokemon/set-page/Market/setMarketOverviewModel.mjs";
import { buildTopChaseHistory, buildTopChaseModel, buildTopSealedModel, readCardHeroImageUrl } from "@/components/pokemon/set-page/Market/setMarketMobileModel.mjs";
import { SectionCard, SetValueLineChart, deltaToneClassName } from "./RichMarketOverviewSection";

const CHASE_ARTWORK_RATIO = "63 / 88";

function InlinePanelSkeleton({ rows = 3, className = "" }) {
  return (
    <div className={`animate-pulse space-y-3 ${className}`.trim()} aria-hidden="true">
      {Array.from({ length: rows }).map((_, index) => (
        <div
          key={`inline-skeleton:${index}`}
          className="h-12 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/50"
        />
      ))}
    </div>
  );
}

function CardArtworkFrame({ imageUrl, alt, initials, className = "" }) {
  return (
    <div
      data-chase-artwork-frame
      className={`flex min-h-0 items-center justify-center overflow-hidden ${className}`}
      style={{ aspectRatio: CHASE_ARTWORK_RATIO }}
    >
      {imageUrl ? (
        <img
          src={imageUrl}
          alt={alt}
          loading="lazy"
          decoding="async"
          data-chase-artwork-image
          // h-full + w-auto + object-contain is the whole contract: height
          // drives, width follows the intrinsic ratio, nothing is cropped.
          className="h-full w-auto max-h-full max-w-full object-contain"
          style={{ aspectRatio: CHASE_ARTWORK_RATIO }}
        />
      ) : (
        <div
          className="flex h-full w-full items-center justify-center rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 text-sm font-semibold text-[var(--text-secondary)]"
          aria-hidden="true"
        >
          {initials || "?"}
        </div>
      )}
    </div>
  );
}

export default function RichTopChaseCardsPanel({ setId, setSlug, cards, status, error, selectedWindowKey, onWindowChange, marketAsOfDate, onRetry, sealedState }) {
  const router = useRouter();
  const [lens, setLens] = useState("cards");
  const sealedProducts = useMemo(
    () => (Array.isArray(sealedState.payload?.setPageConsumerTopProducts) ? sealedState.payload.setPageConsumerTopProducts : []),
    [sealedState.payload]
  );
  const model = useMemo(
    () => lens === "cards"
      ? buildTopChaseModel(cards, { selectedWindowKey, marketAsOfDate, maxRows: 10 })
      : buildTopSealedModel(sealedProducts, { selectedWindowKey, maxRows: 10 }),
    [cards, lens, marketAsOfDate, sealedProducts, selectedWindowKey]
  );
  const [selectedKey, setSelectedKey] = useState(null);
  // Desktop shows the full authoritative Top 10 in the left list at all
  // times — no collapsed/expanded state here. (Progressive disclosure to a
  // Top 3 default is a MOBILE-only pattern; see SetMarketMobileTopChase.)
  const rows = model.rows;
  const resolvedKey = rows.some((row) => row.key === selectedKey) ? selectedKey : rows[0]?.key || null;
  const selectedRow = rows.find((row) => row.key === resolvedKey) || null;
  const selectedCard = useMemo(() => {
    const source = lens === "cards" ? cards : sealedProducts;
    if (!Array.isArray(source)) return null;
    return (
      source.find(
        (card, index) => String(card?.sealedProductId || card?.id || card?.cardId || card?.cardNumber || card?.name || index) === resolvedKey
      ) || null
    );
  }, [cards, lens, resolvedKey, sealedProducts]);

  // The selected card's own series, read through the SAME window machinery the
  // Market Value Trend uses, so a 30D move means the same thing in both places.
  const cardTrend = useMemo(() => {
    if (!selectedCard) return unavailableSegmentTrend({ trackedItemNoun: "Cards" });
    const history = lens === "cards"
      ? buildTopChaseHistory(selectedCard, selectedWindowKey, marketAsOfDate)
      : (selectedCard.history || []).map((point) => ({ ...point, setValue: point.marketPrice }));
    return selectSegmentTrend({ history, selectedWindowKey, trackedItemNoun: "Cards" });
  }, [lens, marketAsOfDate, selectedCard, selectedWindowKey]);

  // NONE until setSlug and a resolvable card identity both exist — never a
  // href="#" and never a guessed id. See buildPokemonCardHref for the
  // identity fallback order (canonicalCardId, then id).
  const cardDetailHref = lens === "cards" && setSlug && selectedCard
    ? buildPokemonCardHref(setSlug, selectedCard)
    : null;
  // Same one-authority rule as the card lens: a product whose canonical id
  // does not resolve gets a null href, and image/name/View Product/second-click
  // navigation all degrade to non-interactive together.
  const productDetailHref = lens === "sealed" && selectedCard
    ? buildSealedProductHref(selectedCard.sealedProductId)
    : null;
  const detailHref = lens === "cards" ? cardDetailHref : productDetailHref;
  // First activation of an unselected row only selects it -- switching the
  // detail pane. A second activation of the row ALREADY selected navigates,
  // because at that point the reader has already seen the detail pane and is
  // asking for the full page. This is two ordinary activations, not a
  // dblclick: a fast double click still lands as two onClick calls.
  const activateTopTenRow = useCallback(
    (row) => {
      if (row.key !== resolvedKey) {
        setSelectedKey(row.key);
        return;
      }
      if (detailHref) router.push(detailHref);
    },
    [resolvedKey, detailHref, router]
  );
  const heroImageUrl = selectedCard ? readCardHeroImageUrl(selectedCard) : null;
  const windowLabel = getDeltaWindowLabel(cardTrend.effectiveWindowKey || selectedWindowKey) || "Trend";
  const trendDirection =
    cardTrend.deltaAmount === null
      ? "neutral"
      : cardTrend.deltaAmount < 0
      ? "negative"
      : cardTrend.deltaAmount > 0
      ? "positive"
      : "neutral";
  const effectiveStatus = lens === "cards" ? status : sealedState.status;
  const effectiveError = lens === "cards" ? error : sealedState.error;

  if ((effectiveStatus === "loading" || effectiveStatus === "idle") && rows.length === 0) {
    return (
      <SectionCard title="Top 10">
        <InlinePanelSkeleton rows={5} />
      </SectionCard>
    );
  }

  if (effectiveStatus === "error" && rows.length === 0) {
    return (
      <SectionCard title="Top 10">
        <p className="text-sm text-red-300">{effectiveError || "Unable to load this ranking for this set."}</p>
        {(lens === "cards" ? onRetry : sealedState.retry) ? (
          <button type="button" onClick={lens === "cards" ? onRetry : sealedState.retry} className="mt-2 text-xs font-semibold text-[var(--accent)]">
            Try again
          </button>
        ) : null}
      </SectionCard>
    );
  }

  return (
    <SectionCard
      title="Top 10"
      titleInfoText="The ten highest-value tracked cards or sealed products in this set."
    >
      <div className="mb-4 flex gap-1.5" role="tablist" aria-label="Top 10 market lens">
        {["cards", "sealed"].map((key) => (
          <button key={key} type="button" role="tab" aria-selected={lens === key} onClick={() => { if (key === "sealed") sealedState.load?.(); setLens(key); }} className={`min-h-9 rounded-lg border px-3 text-xs font-semibold ${lens === key ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,0.12)] text-[rgb(45,212,191)]" : "border-[var(--border-subtle)] text-[var(--text-secondary)]"}`}>
            {key === "cards" ? "Cards" : "Sealed"}
          </button>
        ))}
      </div>
      <div className="grid min-w-0 grid-cols-1 gap-5 desk:grid-cols-[minmax(0,37fr)_minmax(0,63fr)]">
        {/* LEFT — the ranked list. */}
        <ol id="top-chase-list" data-top-chase-list className="min-w-0 space-y-1.5">
          {rows.map((row) => {
            const active = row.key === resolvedKey;
            return (
              <li key={row.key} className="min-w-0">
                <button
                  type="button"
                  data-top-chase-row={row.rank}
                  aria-pressed={active}
                  onClick={() => activateTopTenRow(row)}
                  className={`flex w-full min-w-0 items-center gap-3 rounded-xl border px-3 py-2 text-left transition-colors ${
                    active
                      ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,0.10)]"
                      : "border-[var(--border-subtle)] bg-[var(--surface-page)]/55 hover:border-[rgba(45,212,191,0.5)]"
                  }`}
                >
                  <span className="w-6 flex-none text-xs font-semibold tabular-nums text-[var(--text-secondary)]">
                    #{row.rank}
                  </span>
                  <CardArtworkFrame imageUrl={row.imageUrl} alt="" initials={row.initials} className="h-12 flex-none" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold text-[var(--text-primary)]">{row.name}</span>
                    {row.rarity ? (
                      <span className="block truncate text-[11px] text-[var(--text-secondary)]">{row.rarity}</span>
                    ) : null}
                  </span>
                  <span className="flex-none text-right">
                    <span className="block text-sm font-semibold text-[var(--text-primary)]">{row.priceText || "—"}</span>
                    {row.hasMovement ? (
                      <span className={`flex items-center justify-end gap-1 text-[11px] ${deltaToneClassName(row.amount ?? row.percent)}`}>
                        <DeltaTrendIcon value={row.amount ?? row.percent} />
                        {[row.amountText, row.percentText].filter(Boolean).join(" ")}
                      </span>
                    ) : (
                      // No comparable window for this card — an explicit dash,
                      // never a fabricated 0.0% and never a false arrow.
                      <span className="block text-[11px] text-[var(--text-secondary)]">—</span>
                    )}
                  </span>
                </button>
              </li>
            );
          })}
        </ol>

        {/* RIGHT — selected card detail. Two stacked zones. */}
        <div data-top-chase-detail className="flex min-w-0 flex-col gap-4">
          {/* ZONE A — detail. Artwork left, metadata right. The artwork is
              height-constrained here and appears nowhere else in this column. */}
          <div data-chase-detail-zone className="flex min-w-0 items-start gap-4">
            {/* IMAGE, NAME and the VIEW CTA all point at the ONE routing
                authority for the active lens — buildPokemonCardHref for Cards
                (the same helper the checklist grid uses to reach
                /TCGs/Pokemon/Sets/[setSlug]/Cards/[cardId]), buildSealedProductHref
                for Sealed (the same resolver the RIP page's product comparison
                already uses to reach /sealed-products/[productId]). A row whose
                identity does not resolve gets a null href from that helper, and
                every one of the three entry points degrades to non-interactive
                together rather than three independently-guessed hrefs. */}
            {detailHref ? (
              <a
                href={detailHref}
                aria-label={`View ${selectedRow?.name || (lens === "cards" ? "card" : "product")} details`}
                className="flex-none rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)]"
              >
                <CardArtworkFrame
                  imageUrl={heroImageUrl}
                  alt=""
                  initials={selectedRow?.initials}
                  className="h-40 flex-none desk:h-48"
                />
              </a>
            ) : (
              <CardArtworkFrame
                imageUrl={heroImageUrl}
                alt={selectedRow ? `${selectedRow.name} artwork` : ""}
                initials={selectedRow?.initials}
                className="h-40 flex-none desk:h-48"
              />
            )}
            <div className="min-w-0 flex-1">
              {detailHref ? (
                <a
                  href={detailHref}
                  className="block truncate text-lg font-semibold text-[var(--text-primary)] hover:text-[rgb(45,212,191)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)]"
                >
                  {selectedRow?.name || "—"}
                </a>
              ) : (
                <p className="truncate text-lg font-semibold text-[var(--text-primary)]">{selectedRow?.name || "—"}</p>
              )}
              <p className="mt-0.5 truncate text-xs text-[var(--text-secondary)]">
                {[selectedRow?.rarity, selectedRow?.cardNumber].filter(Boolean).join(" · ") || "—"}
              </p>
              {(() => {
                const viewLabel = lens === "cards" ? "View Card" : "View Product";
                const unavailableTitle =
                  lens === "cards"
                    ? "Card details are unavailable for this listing."
                    : "Product details are unavailable for this listing.";
                return (
                <div className="mt-2">
                  {detailHref ? (
                    <a
                      href={detailHref}
                      data-top-chase-view-card
                      className="inline-flex min-h-8 items-center rounded-md border border-[rgb(45,212,191)] bg-[rgba(45,212,191,0.16)] px-2.5 text-[11px] font-semibold text-[rgb(45,212,191)] transition-colors hover:bg-[rgba(45,212,191,0.26)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)]"
                    >
                      {viewLabel}
                    </a>
                  ) : (
                    <button
                      type="button"
                      data-top-chase-view-card
                      aria-disabled="true"
                      disabled
                      title={unavailableTitle}
                      className="inline-flex min-h-8 cursor-not-allowed items-center rounded-md border border-[var(--border-subtle)] bg-transparent px-2.5 text-[11px] font-semibold text-[var(--text-secondary)] opacity-60"
                    >
                      {viewLabel}
                    </button>
                  )}
                </div>
                );
              })()}
              <div className="mt-3">
                <MarketValueChange
                  value={cardTrend.currentValue ?? selectedRow?.price ?? null}
                  changeAmount={cardTrend.deltaAmount}
                  changePercent={cardTrend.deltaPercent}
                  windowLabel={windowLabel}
                  variant="chart-summary"
                  unavailable={cardTrend.currentValue === null && (selectedRow?.price ?? null) === null}
                  accessibleLabel={`Current price for ${selectedRow?.name || "selected card"}`}
                />
              </div>
              <div className="mt-3 flex min-w-0 items-center gap-2">
                <MarketWindowSelector
                  windows={cardTrend.availableDeltaWindows}
                  value={cardTrend.effectiveWindowKey}
                  onChange={onWindowChange}
                />
              </div>
            </div>
          </div>

          {/* ZONE B — the graph. Full width of this column, and it takes the
              larger share of the height so it reads as substantial. */}
          <div data-chase-graph-zone className="min-w-0 flex-1">
            {cardTrend.series.length ? (
              <SetValueLineChart
                key={`${resolvedKey}-${cardTrend.effectiveWindowKey}-${cardTrend.series.length}`}
                points={cardTrend.series}
                trendDirection={trendDirection}
                scopeLabel={selectedRow?.name || "Card"}
              />
            ) : (
              <p className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)]/42 px-4 py-8 text-center text-sm text-[var(--text-secondary)]">
                {SEGMENT_UNAVAILABLE_TEXT}
              </p>
            )}
          </div>
        </div>
      </div>
    </SectionCard>
  );
}
