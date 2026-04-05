"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import CollectionItemCard from "@/components/Profile/CollectionItemCard";
import { getGridClasses, getBinderPageSize } from "@/config/collectionViewSystem";

/**
 * Unified collection grid component used by both My Collection and Public Collection
 * Supports continuous scroll and binder view modes with shared grid rhythm
 *
 * @param {array} items - Array of collection items
 * @param {string} viewMode - "continuous" or "binder"
 * @param {string} variant - "compact" or "detailed" for card rendering
 * @param {string} emptyMessage - Message when no items
 * @param {bool} isLoading - Loading state
 * @param {string} className - Additional CSS classes
 */
export default function SharedCollectionGrid({
  items = [],
  viewMode = "continuous",
  variant = "detailed",
  emptyMessage = "No items to display.",
  isLoading = false,
  className = "",
  getItemHref = null,
  onSetAssetSpotlight = null,
}) {
  const [currentPage, setCurrentPage] = useState(0);
  const router = useRouter();

  useEffect(() => {
    setCurrentPage(0);
  }, [viewMode, items.length]);

  // For binder mode: paginate items
  const { displayItems, totalPages } = useMemo(() => {
    if (viewMode === "binder") {
      const perPage = getBinderPageSize("binder");
      const pages = Math.ceil(items.length / perPage);
      const start = currentPage * perPage;
      const display = items.slice(start, start + perPage);
      return {
        displayItems: display,
        totalPages: pages,
      };
    }
    return {
      displayItems: items,
      totalPages: 1,
    };
  }, [items, viewMode, currentPage]);

  // Loading state
  if (isLoading) {
    return (
      <div className={`${getGridClasses(viewMode)} ${className}`}>
        {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
          <div
            key={i}
            className="aspect-[3/4] animate-pulse rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-hover)]"
          />
        ))}
      </div>
    );
  }

  // Empty state
  if (!displayItems || displayItems.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)] p-12 text-center">
        <p className="text-sm text-[var(--text-secondary)]">{emptyMessage}</p>
      </div>
    );
  }

  const resolveItemHref = (item) => {
    if (typeof getItemHref !== "function") return null;
    return getItemHref(item) || null;
  };

  const renderCard = (item) => {
    const href = resolveItemHref(item);
    return (
      <CollectionItemCard
        key={item.id}
        item={item}
        variant={variant}
        onClick={href ? () => router.push(href) : null}
        onSetAsSpotlight={onSetAssetSpotlight ? () => onSetAssetSpotlight(item) : null}
      />
    );
  };

  // Continuous scroll view: simple grid
  if (viewMode === "continuous") {
    return (
      <div className={`space-y-6 ${className}`}>
        <div className={getGridClasses("continuous")}>
          {displayItems.map((item) => renderCard(item))}
        </div>
      </div>
    );
  }

  // Binder mode: grid with page navigation
  if (viewMode === "binder") {
    const pageSlots = getBinderPageSize("binder");
    const emptySlots = Math.max(0, pageSlots - displayItems.length);

    return (
      <div className={`space-y-6 ${className}`}>
        <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.4)] sm:p-4">
          <div className={getGridClasses("binder")}>
            {displayItems.map((item) => renderCard(item))}
            {Array.from({ length: emptySlots }).map((_, index) => (
              <div
                key={`empty-slot-${index}`}
                className="hidden rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)]/60 lg:block"
              />
            ))}
          </div>
        </div>

        {totalPages > 1 && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-2 sm:px-4">
            <button
              onClick={() => setCurrentPage((p) => Math.max(0, p - 1))}
              disabled={currentPage === 0}
              className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-4 py-2 text-sm font-medium text-[var(--text-primary)] transition-colors hover:enabled:bg-[var(--surface-hover)] disabled:opacity-50"
              aria-label="Previous page"
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
              Previous Page
            </button>

            <div className="flex items-center gap-2">
              <div className="text-sm text-[var(--text-secondary)]">
                Page {currentPage + 1} of {totalPages}
              </div>
              <div className="flex items-center gap-1" aria-hidden="true">
                {Array.from({ length: totalPages }).map((_, pageIndex) => (
                  <span
                    key={`page-dot-${pageIndex}`}
                    className={`h-1.5 w-1.5 rounded-full ${
                      pageIndex === currentPage ? "bg-[var(--accent)]" : "bg-[var(--border-subtle)]"
                    }`}
                  />
                ))}
              </div>
            </div>

            <button
              onClick={() => setCurrentPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={currentPage === totalPages - 1}
              className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-4 py-2 text-sm font-medium text-[var(--text-primary)] transition-colors hover:enabled:bg-[var(--surface-hover)] disabled:opacity-50"
              aria-label="Next page"
            >
              Next Page
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </button>
          </div>
        )}
      </div>
    );
  }

  return null;
}
