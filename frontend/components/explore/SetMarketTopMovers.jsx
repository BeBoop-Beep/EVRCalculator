"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import MarketValueChange from "@/components/ui/MarketValueChange";
import { selectMoversTickerItems } from "./moversTickerSelector.mjs";
import { getPokemonSetMarketMovers } from "@/lib/pokemon/pokemonSetMarketClient";
import { CARD_THUMBNAIL_WIDTH, optimizedImageUrl } from "@/lib/images/remoteImageDelivery.mjs";
import styles from "./explore.module.css";

// Top Movers for the SELECTED set — a fixed-height horizontal carousel at the
// foot of the Set Market analysis pane.
//
// SOURCING — nothing here is new market machinery:
//   * the data is the existing per-set /market/movers module, the same slim
//     endpoint the set detail page's Market Movers reads. It is the canonical
//     Cards dataset filtered to section=market-movers and sorted by largest
//     dollar move, so the carousel's order IS the published mover ranking.
//     Nothing is ranked, derived or fabricated here.
//   * `selectMoversTickerItems` is the same shared selector the page-level 7D
//     ticker uses to turn that payload into displayable items, so an item that
//     is not a reliable mover there is not one here either.
//   * `getPokemonSetMarketMovers` de-duplicates concurrent identical requests
//     (joinSlimModuleRequest), so re-selecting a set does not fan out.
//
// One request per selected set, cached for the life of the page, and none at
// all until a set is selected — browsing 167 sets prefetches nothing.
//
// WHY NOT THE SHARED TICKER COMPONENT: SevenDayMarketMoversTicker is a
// marquee. It auto-scrolls, it has no paging controls, and it is the approved
// page-level 7D Movers module that must not be modified. This is a paged,
// stationary carousel — a different interaction, so it gets its own small
// component rather than a mode flag on that one.
const WINDOW = "7D";
const LIMIT = 10;

const cache = new Map();
const CACHE_MAX_ENTRIES = 48;

function cacheResult(setId, value) {
  cache.delete(setId);
  cache.set(setId, value);
  while (cache.size > CACHE_MAX_ENTRIES) cache.delete(cache.keys().next().value);
}

function preloadedState(setId, initialPayload) {
  if (!setId || initialPayload?.setId !== setId || initialPayload?.window !== WINDOW || !Array.isArray(initialPayload?.items)) {
    return null;
  }
  const next = {
    status: "success",
    entry: { ...initialPayload, all: initialPayload.items, heatingUp: [], coolingOff: [] },
  };
  cacheResult(setId, next);
  return next;
}

const identity = (card) => [card?.canonicalCardId || card?.cardId || card?.id, card?.cardVariantId || "", card?.conditionId || ""].join(":");

function MoverCard({ card, movement, href }) {
  const image = optimizedImageUrl(card?.imageSmallUrl || card?.imageLargeUrl || card?.imageUrl, CARD_THUMBNAIL_WIDTH);
  const name = card?.name || "Unknown card";
  const price = Number(card?.marketPrice ?? card?.currentPrice);
  return (
    <a href={href} className={styles.moverCard} title={`${name} — view market movers`}>
      <span className="flex h-[3.25rem] w-[2.3rem] flex-none items-center justify-center overflow-hidden rounded border border-[rgba(255,255,255,0.08)]">
        {image
          ? <img src={image} alt="" className="h-full w-full object-contain" loading="lazy" decoding="async" />
          : <span className="text-[8px]">{name.slice(0, 2)}</span>}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-xs font-semibold text-[var(--text-primary)]">{name}</span>
        <MarketValueChange
          value={Number.isFinite(price) ? price : null}
          changeAmount={movement?.amount}
          changePercent={movement?.percent}
          windowLabel={WINDOW}
          showWindowLabel={false}
          variant="ticker"
          accessibleLabel={`${name} market price`}
        />
      </span>
    </a>
  );
}

function StepButton({ direction, disabled, onClick, setName }) {
  const back = direction === "back";
  return (
    <button
      type="button"
      data-mover-carousel-step={direction}
      disabled={disabled}
      onClick={onClick}
      aria-label={`${back ? "Previous" : "Next"} movers in ${setName || "this set"}`}
      className={styles.moverStep}
    >
      <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" className="h-3.5 w-3.5">
        <path d={back ? "m12 4.5-5 5 5 5" : "m8 4.5 5 5-5 5"} stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  );
}

export default function SetMarketTopMovers({ setId, setName, viewAllHref, initialPayload = null }) {
  const [state, setState] = useState(() => preloadedState(setId, initialPayload) || (setId && cache.has(setId) ? cache.get(setId) : { status: "idle", entry: null }));
  const trackRef = useRef(null);
  const [edges, setEdges] = useState({ atStart: true, atEnd: true });
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    if (!setId) {
      setState({ status: "idle", entry: null });
      return undefined;
    }
    if (cache.has(setId) && retryToken === 0) {
      setState(cache.get(setId));
      return undefined;
    }
    let cancelled = false;
    setState({ status: "loading", entry: null });
    getPokemonSetMarketMovers(setId, { window: WINDOW, limit: LIMIT })
      .then((payload) => {
        const next = { status: "success", entry: payload };
        cacheResult(setId, next);
        if (!cancelled) setState(next);
      })
      .catch(() => {
        // Deliberately NOT cached: a transport failure must stay retryable on
        // the next selection rather than becoming this set's permanent answer.
        if (!cancelled) setState({ status: "error", entry: null });
      });
    return () => {
      cancelled = true;
    };
  }, [setId, retryToken]);

  const items = selectMoversTickerItems(state.entry, { maxItems: LIMIT });

  // Which arrows are live is read from the track's own scroll position, so it
  // stays correct whether the user paged, swiped or resized the window.
  const measure = useCallback(() => {
    const track = trackRef.current;
    if (!track) return;
    const max = track.scrollWidth - track.clientWidth;
    setEdges({ atStart: track.scrollLeft <= 1, atEnd: track.scrollLeft >= max - 1 });
  }, []);

  useEffect(() => {
    const track = trackRef.current;
    if (!track) return undefined;
    measure();
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(track);
    return () => observer.disconnect();
  }, [measure, items.length, setId]);

  // scrollBy on the TRACK only. Nothing above it moves, the panel does not
  // resize and the page never scrolls — the carousel viewport is stationary
  // and only its contents translate.
  const page = (sign) => {
    const track = trackRef.current;
    if (!track) return;
    track.scrollBy({ left: sign * Math.max(track.clientWidth - 48, 160), behavior: "smooth" });
  };

  if (!setId) return null;

  const headingId = "set-market-top-movers-heading";
  return (
    <section data-set-market-top-movers aria-labelledby={headingId} className="mt-4 border-t border-[var(--border-subtle)] pt-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        {/* The window is named in the heading ON PURPOSE. This rail is the
            canonical 7D mover dataset and does NOT follow the Set Market
            timeframe — no 30D/3M/1Y mover data exists to follow it with. An
            unlabelled heading beside a 30D set chart would imply 30D movers. */}
        <h4 id={headingId} className="min-w-0 truncate text-[11px] font-semibold uppercase tracking-[0.09em] text-[var(--text-secondary)]">
          Top {WINDOW} Movers in {setName || "this set"}
        </h4>
        {/* A real destination: the selected set's Cards tab, opened on its
            Market Movers section at the same 7D window. Never a dead control. */}
        {viewAllHref ? (
          <a
            href={viewAllHref}
            className="flex-none rounded text-[11px] font-semibold text-[var(--text-secondary)] hover:text-[rgb(45,212,191)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
          >
            View all <span aria-hidden="true">→</span>
            <span className="sr-only"> movers in {setName || "this set"}</span>
          </a>
        ) : null}
      </div>

      {state.status === "error" ? (
        <div role="status" className="flex items-center justify-between gap-3 py-3 text-xs text-[var(--text-secondary)]">
          <span>{`7-day movers for ${setName || "this set"} are currently unavailable.`}</span>
          <button type="button" onClick={() => { cache.delete(setId); setRetryToken((token) => token + 1); }} className="rounded-md border border-[rgba(45,212,191,0.40)] px-3 py-1.5 font-semibold text-[rgb(45,212,191)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)]">Retry movers</button>
        </div>
      ) : state.status !== "success" ? (
        <div aria-hidden="true" className="h-[4.5rem] animate-pulse rounded-[10px] bg-[rgba(148,163,184,0.08)] max-desk:h-[4.75rem]" />
      ) : items.length === 0 ? (
        <p role="status" className="py-3 text-xs text-[var(--text-secondary)]">No reliable 7D movers in this set yet.</p>
      ) : (
        <div className={styles.moverCarousel}>
          <StepButton direction="back" disabled={edges.atStart} onClick={() => page(-1)} setName={setName} />
          <div
            ref={trackRef}
            onScroll={measure}
            data-mover-carousel-track
            role="group"
            aria-label={`Top ${items.length} 7-day movers in ${setName || "this set"}`}
            className={styles.moverTrack}
          >
            {items.map(({ card, movement }) => (
              <MoverCard key={identity(card)} card={card} movement={movement} href={viewAllHref || "#"} />
            ))}
          </div>
          <StepButton direction="forward" disabled={edges.atEnd} onClick={() => page(1)} setName={setName} />
        </div>
      )}
    </section>
  );
}
