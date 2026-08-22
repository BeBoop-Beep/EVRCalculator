"use client";

import React from "react";

import MarketMobileSection, { MarketMobileSectionLink } from "./MarketMobileSection.jsx";
import { NEGATIVE_VALUE_COLOR, POSITIVE_VALUE_COLOR } from "../../../../lib/explore/interpretationTone";
import { CARD_THUMBNAIL_WIDTH, optimizedImageUrl } from "../../../../lib/images/remoteImageDelivery.mjs";
import { buildMoverCards } from "./setMarketMobileModel.mjs";

// ---------------------------------------------------------------------------
// 7D Market Movers — the mobile headline module.
//
// Desktop shows this as an auto-scrolling one-line ticker. A ticker is the
// wrong instrument on a phone: it moves under the thumb, its chips are far
// below a comfortable touch target, and it can never be paused by a reader who
// is trying to look at the third item. The mobile reinterpretation is a
// scroll-snapped carousel of real cards — one card per snap point, large art,
// price and both movement readings — which a thumb drives directly.
//
// Fixed 7D, exactly like desktop: no selector, no other window. The section
// renders only the movers that qualified, so a set with three eligible cards
// shows three cards rather than three cards and five empty frames.
// ---------------------------------------------------------------------------

const TONE = {
  positive: POSITIVE_VALUE_COLOR,
  negative: NEGATIVE_VALUE_COLOR,
  neutral: "var(--text-secondary)",
};

function MoverCard({ mover, href }) {
  const image = optimizedImageUrl(mover.imageUrl, CARD_THUMBNAIL_WIDTH);
  const Wrapper = href ? "a" : "div";
  const changeParts = [mover.amountText, mover.percentText].filter(Boolean);

  return (
    <Wrapper
      {...(href ? { href, "aria-label": `${mover.name} — view 7 day movers` } : {})}
      data-market-mobile-mover
      className="flex w-[8.75rem] flex-none snap-start flex-col gap-2 rounded-xl border border-[var(--border-subtle)] bg-[rgba(8,17,31,0.34)] p-2 transition-colors hover:bg-[var(--surface-hover)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)]"
    >
      <span className="flex h-[6.5rem] w-full items-center justify-center overflow-hidden rounded-lg border border-[rgba(255,255,255,0.07)] bg-[rgba(2,6,23,0.5)]">
        {image ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={image} alt="" className="h-full w-auto object-contain" loading="lazy" decoding="async" />
        ) : (
          <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
            {mover.initials}
          </span>
        )}
      </span>
      <span className="min-w-0">
        <span className="line-clamp-2 min-h-[2.1rem] text-[11.5px] font-semibold leading-[1.08rem] text-[var(--text-primary)]">
          {mover.name}
        </span>
        {mover.priceText ? (
          <span className="mt-1 block truncate text-[13px] font-semibold leading-none tabular-nums text-[var(--text-primary)]">
            {mover.priceText}
          </span>
        ) : null}
        {changeParts.length > 0 ? (
          <span
            className="mt-1 block truncate text-[10.5px] font-semibold leading-none tabular-nums"
            style={{ color: TONE[mover.direction] }}
          >
            {changeParts.join(" · ")}
          </span>
        ) : null}
      </span>
    </Wrapper>
  );
}

export default function SetMarketMobileMovers({ id, entry, status = "success", error = null, viewAllHref = null, onRetry = null }) {
  const movers = buildMoverCards(entry);
  const isLoading = status === "loading" || status === "idle";

  return (
    <MarketMobileSection
      id={id}
      eyebrow="Set Pulse"
      title="7D Market Movers"
      action={<MarketMobileSectionLink href={movers.length > 0 ? viewAllHref : null} />}
    >
      {isLoading && movers.length === 0 ? (
        <div className="flex gap-2.5 overflow-hidden" aria-hidden="true">
          {Array.from({ length: 3 }).map((_, index) => (
            <div
              key={`mover-skeleton:${index}`}
              className="h-[11.5rem] w-[8.75rem] flex-none animate-pulse rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/50"
            />
          ))}
        </div>
      ) : status === "error" && movers.length === 0 ? (
        <div className="flex flex-col items-start gap-2">
          <p className="text-[13px] text-red-300">{error || "Market movers are unavailable."}</p>
          {onRetry ? (
            <button
              type="button"
              onClick={onRetry}
              className="inline-flex min-h-11 items-center rounded-lg border border-[var(--border-subtle)] bg-[rgba(255,255,255,0.04)] px-3 text-xs font-semibold text-[var(--text-primary)]"
            >
              Retry
            </button>
          ) : null}
        </div>
      ) : movers.length === 0 ? (
        <p className="text-[13px] text-[var(--text-secondary)]">No reliable 7-day movers for this set yet.</p>
      ) : (
        /* Snap scrolling, negative gutters and matching padding: the row bleeds
           to both card edges so the strip reads as a rail rather than as a
           boxed list, while each card still lands flush with the section's own
           inset when it snaps. */
        <div
          data-market-mobile-movers-rail
          className="-mx-3.5 flex snap-x snap-mandatory gap-2.5 overflow-x-auto px-3.5 pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        >
          {movers.map((mover) => (
            <MoverCard key={mover.key} mover={mover} href={viewAllHref} />
          ))}
        </div>
      )}
    </MarketMobileSection>
  );
}
