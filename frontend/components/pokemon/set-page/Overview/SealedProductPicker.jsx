"use client";

// React is imported explicitly (not just its hooks) because these components
// are compiled with the classic JSX runtime under the node test runner.
import React, { useCallback, useEffect, useId, useRef, useState } from "react";

import { compactSealedProductLabel } from "./sealedMarketTrendSelector.mjs";

// Sealed product picker.
//
// This replaces a native <select>. The trigger could be styled to match the
// rest of the dropdown system, but the OPENED panel could not: the option list
// is drawn by the operating system, so it stayed a white/gray platform menu
// with platform selection highlighting, and no amount of CSS on the <select>
// changes that. A custom listbox is the only way the opened state can match.
//
// The interaction model is deliberately copied from the set picker in
// RipStatisticsPageClient: real DOM focus moves between the option buttons
// (roving focus, not aria-activedescendant), Escape hands focus back to the
// control that opened the menu, and dismissal listens on mousedown/touchstart
// so a tap that lands outside closes before any click resolves.
//
// The picker owns open/active state only. Data loading, ordering and chart
// rendering stay in SealedMarketTrendCard — `products` arrives already sorted
// price-descending and is rendered in the order given.

const priceFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function formatPrice(value) {
  const price = Number(value);
  return Number.isFinite(price) && price > 0 ? priceFormatter.format(price) : "—";
}

// The same chevron the set picker draws, so the two controls read as one system.
function Chevron({ open }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 20 20"
      className={`h-4 w-4 flex-none text-[var(--text-secondary)] transition-transform ${open ? "rotate-180" : ""}`}
      fill="currentColor"
    >
      <path d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.12l3.71-3.89a.75.75 0 1 1 1.08 1.04l-4.25 4.45a.75.75 0 0 1-1.08 0L5.21 8.27a.75.75 0 0 1 .02-1.06Z" />
    </svg>
  );
}

export default function SealedProductPicker({ products = [], value, onChange, onOpenChange = null }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const triggerRef = useRef(null);
  const listboxRef = useRef(null);
  // Which option to land focus on once the menu paints: the current product by
  // default, or the first/last when opened with an arrow key.
  const pendingFocusRef = useRef("selected");
  const listboxId = `sealed-product-listbox-${useId().replace(/:/g, "")}`;

  const options = Array.isArray(products) ? products.filter(Boolean) : [];
  const selected = options.find((item) => String(item.sealedProductId) === String(value)) || null;
  const selectedIndex = selected ? options.indexOf(selected) : -1;

  // An empty product list has nothing to show, so the menu never opens — the
  // trigger is disabled in that case and an empty panel would just be a stray
  // frosted rectangle over the chart.
  const canOpen = options.length > 0;
  const setOpenState = useCallback((next) => {
    const resolved = next && canOpen;
    setOpen(resolved);
    onOpenChange?.(resolved);
  }, [onOpenChange, canOpen]);

  const closeAndRestoreFocus = useCallback(() => {
    setOpenState(false);
    triggerRef.current?.focus?.();
  }, [setOpenState]);

  // Dismissal. Pointer-down rather than click so a tap outside cannot be
  // swallowed by the option that is about to unmount underneath it.
  useEffect(() => {
    if (!open || typeof document === "undefined") return undefined;

    const handleOutside = (event) => {
      if (!rootRef.current?.contains(event.target)) {
        setOpenState(false);
      }
    };
    const handleEscape = (event) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        closeAndRestoreFocus();
      }
    };

    document.addEventListener("mousedown", handleOutside);
    document.addEventListener("touchstart", handleOutside, { passive: true });
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handleOutside);
      document.removeEventListener("touchstart", handleOutside);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [open, closeAndRestoreFocus, setOpenState]);

  // Move real focus into the list on open, matching the set picker.
  useEffect(() => {
    if (!open) return;
    const rows = Array.from(listboxRef.current?.querySelectorAll('[role="option"]') || []);
    if (rows.length === 0) return;
    const target =
      pendingFocusRef.current === "last"
        ? rows.length - 1
        : pendingFocusRef.current === "first"
          ? 0
          : Math.max(selectedIndex, 0);
    rows[target]?.focus?.();
    pendingFocusRef.current = "selected";
  }, [open, selectedIndex]);

  const handleTriggerKeyDown = (event) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    pendingFocusRef.current = open ? "selected" : event.key === "ArrowUp" ? "last" : "first";
    if (!open) setOpenState(true);
  };

  // Identical roving-focus arithmetic to the set picker's handler.
  const handleListKeyDown = (event) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    const rows = Array.from(event.currentTarget.querySelectorAll('[role="option"]:not(:disabled)'));
    if (rows.length === 0) return;
    event.preventDefault();
    const currentIndex = rows.indexOf(document.activeElement);
    const nextIndex =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? rows.length - 1
          : event.key === "ArrowDown"
            ? (currentIndex + 1 + rows.length) % rows.length
            : (currentIndex - 1 + rows.length) % rows.length;
    rows[nextIndex]?.focus();
  };

  const handleSelect = (item) => {
    onChange?.(String(item.sealedProductId));
    closeAndRestoreFocus();
  };

  const triggerLabel = selected ? compactSealedProductLabel(selected) : "Select a product";

  return (
    <div ref={rootRef} data-sealed-product-picker className="relative mt-3 min-w-0">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpenState(!open)}
        onKeyDown={handleTriggerKeyDown}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listboxId}
        aria-label={selected ? `Sealed product: ${selected.name}` : "Select a sealed product"}
        title={selected?.name || undefined}
        disabled={options.length === 0}
        className="set-dropdown-glass-trigger flex h-10 w-full min-w-0 items-center justify-between gap-2 rounded-lg pl-2 pr-3 text-xs text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-70"
      >
        <span className="min-w-0 flex-1 truncate text-left">{triggerLabel}</span>
        <Chevron open={open} />
      </button>

      {open ? (
        <div
          ref={listboxRef}
          id={listboxId}
          role="listbox"
          aria-label="Sealed products"
          onKeyDown={handleListKeyDown}
          className="index-scrollbar set-dropdown-glass absolute left-0 top-[calc(100%+0.5rem)] z-50 max-h-[min(50vh,14rem)] w-full overflow-y-auto rounded-xl p-1.5"
        >
          {options.map((item) => {
            const isSelected = String(item.sealedProductId) === String(value);
            const label = compactSealedProductLabel(item);
            const price = formatPrice(item.currentPrice);
            return (
              <button
                key={item.sealedProductId}
                type="button"
                role="option"
                aria-selected={isSelected}
                // The concise label is what shows; the full scraped name is
                // what assistive technology and the tooltip get.
                aria-label={`${label}, ${item.name}, ${price}${isSelected ? ", current selection" : ""}`}
                title={item.name}
                onClick={() => handleSelect(item)}
                className={`set-dropdown-option flex min-h-11 w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-xs leading-5 transition-colors ${
                  isSelected ? "text-[var(--text-primary)]" : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                }`}
              >
                <span className="min-w-0 flex-1 truncate">{label}</span>
                <span className={`shrink-0 tabular-nums ${isSelected ? "font-medium text-[var(--accent)]" : ""}`}>{price}</span>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
