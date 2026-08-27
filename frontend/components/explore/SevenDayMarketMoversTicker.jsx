"use client";
import MarketValueChange from "@/components/ui/MarketValueChange";
import MoversTickerViewport from "./MoversTickerViewport";
import { selectMoversTickerItems } from "./moversTickerSelector.mjs";
import { buildPokemonCardDetailHref } from "@/lib/pokemon/pokemonCardDetailClient";
import { CARD_THUMBNAIL_WIDTH, optimizedImageUrl } from "@/lib/images/remoteImageDelivery.mjs";

const identity = (card) => [card?.canonicalCardId || card?.cardId || card?.id, card?.cardVariantId || "", card?.conditionId || ""].join(":");
const hrefFor = (card) => buildPokemonCardDetailHref(card);

function Item({ card, movement, href, hidden, crossSet, thumbnailSize }) {
  const image = optimizedImageUrl(card?.imageSmallUrl || card?.imageLargeUrl || card?.imageUrl, CARD_THUMBNAIL_WIDTH);
  const name = card?.name || "Unknown card";
  const price = Number(card?.marketPrice ?? card?.currentPrice);
  const thumbnailSizeClass = thumbnailSize === "medium"
    ? "h-12 w-[2.1rem] max-desk:h-11 max-desk:w-[1.925rem]"
    : "h-10 w-7";
  return <a href={href} tabIndex={hidden ? -1 : undefined} title={`${name} — view market movers`}
    className="flex min-w-0 flex-none items-center gap-2 rounded-lg px-2 py-1 hover:bg-[var(--surface-hover)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]">
    <span className={`flex ${thumbnailSizeClass} flex-none items-center justify-center overflow-hidden rounded border border-[rgba(255,255,255,0.08)]`}>
      {image ? <img src={image} alt="" className="h-full w-full object-contain" loading="lazy" decoding="async" /> : <span className="text-[8px]">{name.slice(0, 2)}</span>}
    </span>
    <span className="min-w-0 max-w-[11rem]">
      <span className="block truncate text-xs font-semibold text-[var(--text-primary)]">{name}</span>
      {crossSet ? <span className="block truncate text-[10px] text-[var(--text-secondary)]">{card?.setName || "Unknown set"}</span> : null}
      <MarketValueChange value={Number.isFinite(price) ? price : null} changeAmount={movement?.amount}
        changePercent={movement?.percent} windowLabel="7D" showWindowLabel={false} variant="ticker"
        accessibleLabel={`${name} market price`} />
    </span>
  </a>;
}

export default function SevenDayMarketMoversTicker({ entry, maxItems = 10, scope = "set", thumbnailSize = "small", status = "success", error, viewAllHref = "#", onRetry }) {
  const items = selectMoversTickerItems(entry, { maxItems });
  const crossSet = scope === "explore";
  const containerHeightClass = crossSet ? "h-20" : "h-14";
  const renderSequence = (hidden, ref) => <div ref={ref} aria-hidden={hidden ? "true" : undefined}
    className={`flex items-center gap-1 pr-1 ${hidden ? "index-ticker-duplicate" : ""}`.trim()}>
    {items.map(({ card, movement }) => <Item key={`${hidden ? "dup:" : ""}${identity(card)}`} card={card} movement={movement}
      href={hrefFor(card)} hidden={hidden} crossSet={crossSet} thumbnailSize={thumbnailSize} />)}
  </div>;
  const fallback = status === "loading" ? <div className="h-6 w-full max-w-[28rem] animate-pulse rounded-md bg-[rgba(148,163,184,0.10)]" /> :
    status === "error" ? <span className="truncate text-xs text-red-300">{error || "Market movers are unavailable."}{onRetry ? <button onClick={onRetry}> Retry</button> : null}</span> :
    <p className="truncate text-xs text-[var(--text-secondary)]">No reliable 7D movers yet.</p>;
  return <div className={`set-glass-surface flex ${containerHeightClass} min-w-0 items-center gap-2 rounded-xl border border-[var(--border-subtle)] py-1 pl-3 pr-2 max-desk:rounded-none max-desk:border-0 max-desk:px-0`}>
    <span className="flex-none px-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">7D Movers</span>
    <MoversTickerViewport hasItems={items.length > 0} items={items} renderSequence={renderSequence} fallback={fallback} />
    {!crossSet && viewAllHref ? <a href={viewAllHref} aria-label="View all 7-day movers"
      className="flex h-10 w-10 flex-none items-center justify-center rounded-md text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] desk:h-auto desk:w-auto desk:px-2.5 desk:py-1.5">
      <span className="desk:hidden" aria-hidden="true">
        <svg viewBox="0 0 20 20" fill="none" className="h-4 w-4">
          <path d="m7.5 4.5 5 5-5 5" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
      <span className="hidden text-xs font-semibold desk:inline">View all movers →</span>
    </a> : null}
  </div>;
}
