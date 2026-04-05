/**
 * Component for displaying a collector's binder in a visually organized layout.
 * Shows binder "pages" with cards organized in rows.
 */
"use client";

import { useState } from "react";

export default function PublicBinderViewer({
  binderPages = [],
  emptyMessage = "No binder pages available.",
  isLoading = false,
}) {
  const [currentPage, setCurrentPage] = useState(0);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-32 animate-pulse rounded bg-[var(--surface-hover)]" />
        <div className="grid gap-2 sm:grid-cols-4 lg:grid-cols-6">
          {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map((i) => (
            <div
              key={i}
              className="aspect-[16/20] animate-pulse rounded border border-[var(--border-subtle)] bg-[var(--surface-hover)]"
            />
          ))}
        </div>
      </div>
    );
  }

  if (!binderPages || binderPages.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)] p-12 text-center">
        <p className="text-sm text-[var(--text-secondary)]">{emptyMessage}</p>
      </div>
    );
  }

  const page = binderPages[currentPage];

  return (
    <div className="space-y-6">
      {/* Page Navigation */}
      {binderPages.length > 1 && (
        <div className="flex items-center justify-between">
          <button
            onClick={() => setCurrentPage((p) => Math.max(0, p - 1))}
            disabled={currentPage === 0}
            className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-3 py-2 text-sm font-medium text-[var(--text-primary)] disabled:opacity-50 hover:enabled:bg-[var(--surface-hover)]"
          >
            ← Previous
          </button>

          <div className="text-sm text-[var(--text-secondary)]">
            Page <span className="font-semibold text-[var(--text-primary)]">{currentPage + 1}</span> of{" "}
            <span className="font-semibold text-[var(--text-primary)]">{binderPages.length}</span>
          </div>

          <button
            onClick={() => setCurrentPage((p) => Math.min(binderPages.length - 1, p + 1))}
            disabled={currentPage === binderPages.length - 1}
            className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-3 py-2 text-sm font-medium text-[var(--text-primary)] disabled:opacity-50 hover:enabled:bg-[var(--surface-hover)]"
          >
            Next →
          </button>
        </div>
      )}

      {/* Binder Page */}
      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-4 sm:p-6">
        <div className="mb-4">
          <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
            {page.section || "Binder Section"}
          </p>
          <h3 className="mt-1 text-lg font-semibold text-[var(--text-primary)]">{page.title || `Page ${currentPage + 1}`}</h3>
        </div>

        {/* Card Grid - 6 cards per row, 2 rows per page (12 slots) */}
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-6">
          {page.slots && page.slots.map((slot, idx) => (
            <div
              key={idx}
              className="aspect-[2.5/3.5] overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-hover)]"
            >
              {slot ? (
                <>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={slot.imageUrl || ""}
                    alt={slot.name}
                    className="h-full w-full object-cover"
                  />
                  {slot.isFoil && (
                    <div className="absolute right-1 top-1 rounded bg-amber-500 px-1 text-[8px] font-bold text-white">
                      FOIL
                    </div>
                  )}
                </>
              ) : (
                <div className="flex h-full items-center justify-center text-[10px] text-[var(--text-secondary)]">
                  Empty
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Page Info */}
        {page.cardCount !== undefined && (
          <div className="mt-4 text-xs text-[var(--text-secondary)]">
            {page.cardCount} card{page.cardCount !== 1 ? "s" : ""} on this page
          </div>
        )}
      </div>

      {/* Quick Stats */}
      {binderPages.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-3">
          <StatPill
            label="Total Pages"
            value={binderPages.length}
          />
          <StatPill
            label="Total Cards"
            value={binderPages.reduce((sum, p) => sum + (p.cardCount || 0), 0)}
          />
          <StatPill
            label="Binder Value"
            value={binderPages[0]?.binderValue || "Calculating..."}
          />
        </div>
      )}
    </div>
  );
}

function StatPill({ label, value }) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-3 text-center">
      <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{label}</p>
      <p className="mt-1 text-lg font-semibold text-[var(--text-primary)]">{value}</p>
    </div>
  );
}
