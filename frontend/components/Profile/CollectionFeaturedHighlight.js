"use client";

/**
 * Collection Showcase Display Component
 * Shows the 3-slot analytics showcase: Top Conviction Hold, Spotlight Asset, Biggest Gainer
 * Used by both public profile and My Collection dashboard
 */

import Link from "next/link";

import { SHOWCASE_SLOT_CONFIG } from "@/lib/profile/featuredItemsModel";
import { buildShowcaseAssetHref } from "@/lib/profile/collectionRoutes";

export default function CollectionFeaturedHighlight({
  showcase = {},
  mode = "public",
  username = "",
  title = "Asset Showcase",
  subtitle = null,
  emptyMessage = null,
  onSpotlightEdit = null,
  className = "",
}) {
  const isOwnerMode = mode === "owner";

  const slotItems = {
    topConviction: showcase?.topConviction || null,
    biggestGainer: showcase?.biggestGainer || null,
    spotlight: showcase?.spotlight || null,
  };

  const hasAtLeastOneItem = Object.values(slotItems).some(Boolean);

  const sectionSubtitle =
    subtitle
    || (isOwnerMode
      ? "Three aligned slots that shape your public portfolio story while keeping My Collection analytics-first."
      : "A read-only portfolio narrative across three slots: Top Conviction, Spotlight, and Biggest Gainer.");

  return (
    <section className={`dashboard-panel rounded-2xl border border-[var(--border-subtle)] p-4 sm:p-5 ${className}`}>
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">Showcase</p>
          <h2 className="mt-1 text-base font-semibold text-[var(--text-primary)]">{title}</h2>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">{sectionSubtitle}</p>
        </div>

        {isOwnerMode && typeof onSpotlightEdit === "function" ? (
          <button
            type="button"
            onClick={onSpotlightEdit}
            className="shrink-0 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:border-[var(--border-default)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-hover)]"
          >
            Change Spotlight
          </button>
        ) : null}
      </div>

      {!hasAtLeastOneItem ? (
        <div className="rounded-lg border border-dashed border-[var(--border-subtle)] bg-[var(--surface-hover)] p-10 text-center">
          <p className="text-sm text-[var(--text-secondary)]">
            {emptyMessage
              || (isOwnerMode
                ? "No showcase assets yet. Slots populate as soon as your collection has assets."
                : "This collector has not published showcase assets yet.")}
          </p>
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-3">
          {SHOWCASE_SLOT_CONFIG.map((slot) => (
            <ShowcaseAssetTile
              key={slot.key}
              slot={slot}
              item={slotItems[slot.key] || null}
              mode={mode}
              username={username}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function ShowcaseAssetTile({
  item,
  slot,
  mode,
  username,
}) {
  const href = buildShowcaseAssetHref({ asset: item, mode, username });

  const metricValue = item?.metricValueLabel || item?.valueLabel || "N/A";
  const metricLabel = item?.metricLabel || (slot.key === "spotlight" ? "Highlight" : "Metric");
  const contextualStat = item?.statLine || item?.context || item?.set || "Portfolio signal";
  const assetName = item?.name || "No eligible asset yet";
  const assetMeta = item?.set || item?.collectible_type?.replace("_", " ") || "Awaiting asset data";
  const statusPill = slot.mode === "computed" ? "Computed" : item?.isUserSelected ? "Manual" : "Fallback";
  const imageAlt = item?.name ? `${item.name} showcase asset` : `${slot.label} showcase slot`;

  return (
    <article className="group overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:scale-[1.03] hover:shadow-[0_12px_30px_rgba(15,23,42,0.12)]">
      <Link href={href} className="block p-4">
        <div className="flex items-center justify-between gap-3">
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">{slot.label}</p>
          <span className="rounded-full border border-[var(--border-subtle)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
            {statusPill}
          </span>
        </div>

        <div className="mt-3 overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-hover)]">
          <div className="relative aspect-[2/1] w-full">
            {item?.imageUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={item.imageUrl}
                alt={imageAlt}
                className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
              />
            ) : (
              <div className="flex h-full w-full items-center justify-center text-[11px] text-[var(--text-secondary)] opacity-70">
                Asset image unavailable
              </div>
            )}
          </div>
        </div>

        <div className="mt-3 space-y-1">
          <p className="line-clamp-2 min-h-[2.5rem] text-sm font-semibold leading-tight text-[var(--text-primary)]">{assetName}</p>
          <p className="truncate text-xs text-[var(--text-secondary)]">{assetMeta}</p>
        </div>

        <div className="mt-3 border-t border-[var(--border-subtle)] pt-3">
          <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--text-secondary)]">{metricLabel}</p>
          <p className="mt-1 font-mono text-lg font-semibold tracking-tight text-[var(--text-primary)]">{metricValue}</p>
          <p className="mt-1 line-clamp-2 text-xs text-[var(--text-secondary)]">{contextualStat}</p>
        </div>
      </Link>

      {!item && (
        <div className="border-t border-dashed border-[var(--border-subtle)] bg-[var(--surface-panel)] px-4 py-2 text-[11px] text-[var(--text-secondary)]">
          No eligible asset in this slot yet.
        </div>
      )}
    </article>
  );
}
