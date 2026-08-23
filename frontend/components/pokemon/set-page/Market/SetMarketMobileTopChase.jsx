"use client";

import React, { useEffect, useMemo, useState } from "react";

import MarketMobileSection, { MarketMobileSectionLink } from "./MarketMobileSection.jsx";
import MarketWindowSelector from "../../../explore/MarketWindowSelector";
import { getStandardDeltaWindowDefinitions } from "../../../../lib/explore/marketDeltaWindows.mjs";
import { NEGATIVE_VALUE_COLOR, POSITIVE_VALUE_COLOR } from "../../../../lib/explore/interpretationTone";
import { CARD_ART_WIDTH, CARD_THUMBNAIL_WIDTH, optimizedImageUrl } from "../../../../lib/images/remoteImageDelivery.mjs";
import { MOBILE_TOP_CHASE_PREVIEW_LIMIT, buildTopChaseModel } from "./setMarketMobileModel.mjs";

// ---------------------------------------------------------------------------
// Top Chase Cards — featured card plus a ranked list.
//
// Desktop draws ten identical table rows, each with its own sparkline. Ported
// literally that becomes ten near-identical phone rows carrying ten ~120px
// charts, and the #1 chase card — the single most interesting object on the
// section — is indistinguishable from the #9. So the mobile structure states
// the hierarchy the data already has: one large featured card for #1, then a
// compact ranked list for the rest.
//
// NO MICROCHARTS. Every row here reports price and movement as text. A 120px
// sparkline on a phone row is decorative at best and misleading at worst, and
// dropping them is what lets the remaining rows stay tall enough to tap.
//
// The window selector governs which published delta the rows report; it fetches
// nothing, exactly as on desktop.
// ---------------------------------------------------------------------------

const TONE = {
  positive: POSITIVE_VALUE_COLOR,
  negative: NEGATIVE_VALUE_COLOR,
  neutral: "var(--text-secondary)",
};

const WINDOWS = getStandardDeltaWindowDefinitions();

function ChangeText({ row, className = "" }) {
  const parts = [row.amountText, row.percentText].filter(Boolean);
  if (parts.length === 0) {
    return <span className={`${className} text-[var(--text-secondary)]`}>No comparable window</span>;
  }
  return (
    <span className={`${className} tabular-nums`} style={{ color: TONE[row.direction] }}>
      {parts.join(" · ")}
    </span>
  );
}

function FeaturedChaseCard({ row, href }) {
  const image = optimizedImageUrl(row.imageUrl, CARD_ART_WIDTH);
  const Wrapper = href ? "a" : "div";
  return (
    <Wrapper
      {...(href ? { href, "aria-label": `${row.name} — open in Cards` } : {})}
      data-market-mobile-chase-featured
      className="relative flex min-w-0 items-center gap-3.5 overflow-hidden rounded-xl border border-[rgba(45,212,191,0.16)] bg-[rgba(8,17,31,0.42)] p-3 transition-colors hover:bg-[var(--surface-hover)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)]"
    >
      <span className="relative flex h-[7.5rem] w-[5.35rem] flex-none items-center justify-center overflow-hidden rounded-lg border border-[rgba(255,255,255,0.08)] bg-[rgba(2,6,23,0.5)] shadow-[0_10px_26px_rgba(2,6,23,0.45)]">
        {image ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={image} alt="" className="h-full w-full object-cover" loading="lazy" decoding="async" />
        ) : (
          <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
            {row.initials}
          </span>
        )}
        <span className="absolute left-1 top-1 inline-flex items-center rounded-md border border-[rgba(45,212,191,0.4)] bg-[rgba(2,6,23,0.78)] px-1.5 py-0.5 text-[10px] font-bold leading-none tabular-nums text-[rgb(45,212,191)]">
          {`#${row.rank}`}
        </span>
      </span>
      <span className="min-w-0 flex-1">
        <span className="line-clamp-2 text-[14px] font-semibold leading-tight text-[var(--text-primary)]">{row.name}</span>
        {row.rarity ? (
          <span className="mt-1 block truncate text-[11px] text-[var(--text-secondary)]">{row.rarity}</span>
        ) : null}
        {row.priceText ? (
          <span className="mt-2.5 block text-[21px] font-semibold leading-none tabular-nums text-[var(--text-primary)]">
            {row.priceText}
          </span>
        ) : null}
        <ChangeText row={row} className="mt-1.5 block text-[12px] font-semibold" />
      </span>
    </Wrapper>
  );
}

function RankedChaseRow({ row, href }) {
  const image = optimizedImageUrl(row.imageUrl, CARD_THUMBNAIL_WIDTH);
  const Wrapper = href ? "a" : "div";
  return (
    <Wrapper
      {...(href ? { href, "aria-label": `${row.name} — open in Cards` } : {})}
      data-market-mobile-chase-row
      className="flex min-h-[3.25rem] min-w-0 items-center gap-2.5 rounded-lg px-1 py-2 transition-colors hover:bg-[var(--surface-hover)]/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)]"
    >
      <span className="w-5 flex-none text-right text-[11px] font-semibold tabular-nums text-[var(--text-secondary)]">
        {row.rank}
      </span>
      <span className="flex h-10 w-[1.85rem] flex-none items-center justify-center overflow-hidden rounded border border-[rgba(255,255,255,0.07)] bg-[rgba(2,6,23,0.5)]">
        {image ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={image} alt="" className="h-full w-full object-cover" loading="lazy" decoding="async" />
        ) : (
          <span className="text-[8px] font-semibold text-[var(--text-secondary)]">{row.initials}</span>
        )}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[12.5px] font-medium leading-tight text-[var(--text-primary)]">{row.name}</span>
        {row.rarity ? (
          <span className="mt-0.5 block truncate text-[10px] leading-tight text-[var(--text-secondary)]">{row.rarity}</span>
        ) : null}
      </span>
      <span className="min-w-0 flex-none text-right">
        {row.priceText ? (
          <span className="block text-[12.5px] font-semibold leading-tight tabular-nums text-[var(--text-primary)]">
            {row.priceText}
          </span>
        ) : null}
        <ChangeText row={row} className="mt-0.5 block text-[10.5px] font-semibold leading-tight" />
      </span>
    </Wrapper>
  );
}

export default function SetMarketMobileTopChase({
  id,
  cards,
  status = "success",
  error = null,
  selectedWindowKey = null,
  onWindowChange = null,
  marketAsOfDate = null,
  rowHref = null,
  viewAllHref = null,
  onRetry = null,
}) {
  const [expanded, setExpanded] = useState(false);
  const hasCards = Array.isArray(cards) && cards.length > 0;
  const availableWindows = hasCards ? WINDOWS : [];
  const effectiveWindowKey =
    selectedWindowKey && availableWindows.some((entry) => entry.key === selectedWindowKey) ? selectedWindowKey : "7D";

  const model = useMemo(
    () => buildTopChaseModel(cards, { selectedWindowKey: effectiveWindowKey, marketAsOfDate }),
    [cards, effectiveWindowKey, marketAsOfDate]
  );

  const resetKey = model.rows.map((row) => row.key).join("|");
  useEffect(() => {
    setExpanded(false);
  }, [resetKey]);

  // The list below the featured card previews four rows (#2-#5) and expands in
  // place to whatever the fetch actually returned. There is no dedicated chase
  // destination to link out to, so nothing is discarded — the extra ranks are
  // one tap away rather than absent.
  const visibleRanked = expanded ? model.ranked : model.ranked.slice(0, MOBILE_TOP_CHASE_PREVIEW_LIMIT - 1);
  const hiddenCount = model.ranked.length - visibleRanked.length;

  return (
    <MarketMobileSection
      id={id}
      eyebrow="Chase Pool"
      title="Top Chase Cards"
      action={<MarketMobileSectionLink href={hasCards ? viewAllHref : null} label="All cards" />}
    >
      {(status === "loading" || status === "idle") && !hasCards ? (
        <div className="space-y-2" aria-hidden="true">
          <div className="h-[8.5rem] w-full animate-pulse rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/50" />
          {Array.from({ length: 4 }).map((_, index) => (
            <div
              key={`chase-skeleton:${index}`}
              className="h-[3.25rem] w-full animate-pulse rounded-lg bg-[var(--surface-page)]/40"
            />
          ))}
        </div>
      ) : status === "error" && !hasCards ? (
        <div className="flex flex-col items-start gap-2">
          <p className="text-[13px] text-red-300">{error || "Unable to load market cards for this set."}</p>
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
      ) : !model.featured ? (
        <p className="text-[13px] text-[var(--text-secondary)]">No priced chase cards are available yet for this set.</p>
      ) : (
        <div className="space-y-3">
          <MarketWindowSelector
            windows={availableWindows}
            value={effectiveWindowKey}
            onChange={onWindowChange}
            fullWidth
            ariaDescription="Chooses which published change window these chase cards report. No data is fetched."
          />

          <FeaturedChaseCard row={model.featured} href={rowHref} />

          {visibleRanked.length > 0 ? (
            <div className="divide-y divide-[var(--border-subtle)]">
              {visibleRanked.map((row) => (
                <RankedChaseRow key={row.key} row={row} href={rowHref} />
              ))}
            </div>
          ) : null}

          {hiddenCount > 0 || expanded ? (
            <div className="flex justify-center">
              <button
                type="button"
                onClick={() => setExpanded((value) => !value)}
                aria-expanded={expanded}
                aria-label={expanded ? "Show fewer chase cards" : "View Top 10 chase cards"}
                className="inline-flex min-h-11 items-center gap-1.5 rounded-lg px-3 text-[11px] font-semibold text-[rgb(45,212,191)] transition-colors hover:bg-[var(--surface-hover)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)]"
              >
                <span aria-hidden="true">{expanded ? "Show less" : "View Top 10"}</span>
                <svg
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  aria-hidden="true"
                  className={`h-4 w-4 flex-none transition-transform ${expanded ? "rotate-180" : ""}`}
                >
                  <path d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.12l3.71-3.89a.75.75 0 1 1 1.08 1.04l-4.25 4.45a.75.75 0 0 1-1.08 0L5.21 8.27a.75.75 0 0 1 .02-1.06Z" />
                </svg>
              </button>
            </div>
          ) : null}
        </div>
      )}
    </MarketMobileSection>
  );
}
