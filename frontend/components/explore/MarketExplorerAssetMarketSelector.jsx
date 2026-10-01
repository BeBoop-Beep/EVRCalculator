"use client";

import React, { useEffect, useId, useRef } from "react";

export const ASSET_MARKET_OPTION_CLASS =
  "flex w-full items-center justify-between gap-3 rounded-md border-l-2 px-2 py-2 text-left text-xs transition-colors hover:bg-white/[.035] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,.65)]";
export const ASSET_MARKET_ACTIVE_CLASS =
  "border-[rgb(45,212,191)] bg-[rgba(45,212,191,.12)] font-bold text-[rgb(45,212,191)]";

export default function MarketExplorerAssetMarketSelector({
  disclosureId,
  heading,
  summary,
  open,
  onOpenChange,
  search,
  onSearchChange,
  searchPlaceholder,
  options = [],
  emptyCopy,
  actionLabel = "View",
  onOptionAction,
  message = "",
  statusContent = null,
}) {
  const rootRef = useRef(null);
  const triggerRef = useRef(null);
  const searchRef = useRef(null);
  const generatedId = useId();
  const panelId = `${disclosureId}-${generatedId.replace(/:/g, "")}`;

  useEffect(() => {
    if (!open) return undefined;
    if (typeof document === "undefined") return undefined;
    requestAnimationFrame(() => searchRef.current?.focus());
    const onPointerDown = (event) => {
      const path = typeof event.composedPath === "function" ? event.composedPath() : [];
      if (path.includes(rootRef.current) || rootRef.current?.contains(event.target)) return;
      onOpenChange(false);
    };
    const onKeyDown = (event) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      onOpenChange(false);
      requestAnimationFrame(() => triggerRef.current?.focus());
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onOpenChange]);

  return (
    <section ref={rootRef} data-market-explorer-asset-selector={disclosureId} data-market-explorer-rarity-markets={disclosureId === "rarities" ? true : undefined} data-market-explorer-sealed-types={disclosureId === "sealed-types" ? true : undefined} className={`relative py-2 ${open ? "z-[80]" : "z-0"}`}>
      <button
        ref={triggerRef}
        type="button"
        data-market-asset-selector-trigger={disclosureId}
        data-rarity-market-trigger={disclosureId === "rarities" ? true : undefined}
        data-sealed-types-trigger={disclosureId === "sealed-types" ? true : undefined}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => onOpenChange(!open)}
        className="flex min-h-10 w-full items-center justify-between rounded-md border border-[var(--border-subtle)] bg-white/[.03] px-3 text-left text-xs font-semibold text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgb(45,212,191)]"
      >
        <span><span className="block">{heading}</span><span className="block text-[10px] font-normal text-[var(--text-secondary)]">{summary}</span></span>
        <span aria-hidden="true">{open ? "−" : "+"}</span>
      </button>
      <div
        id={panelId}
        hidden={!open}
        data-market-asset-selector-popover={disclosureId}
        data-market-directory-interaction-boundary
        onPointerDownCapture={(event) => event.stopPropagation()}
        onWheelCapture={(event) => event.stopPropagation()}
        className="absolute left-0 right-0 z-[81] mt-1 overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-slate-950 shadow-2xl"
      >
        <label htmlFor={`${panelId}-search`} className="sr-only">{searchPlaceholder}</label>
        <input ref={searchRef} id={`${panelId}-search`} data-rarity-market-search={disclosureId === "rarities" ? true : undefined} data-sealed-type-search={disclosureId === "sealed-types" ? true : undefined} type="search" value={search} onChange={(event) => onSearchChange(event.target.value)} placeholder={searchPlaceholder} className="min-h-10 w-full border-b border-[var(--border-subtle)] bg-transparent px-3 text-xs text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[rgb(45,212,191)]" />
        <div role="listbox" aria-label={`${heading} options`} data-market-asset-selector-scroll-region className="max-h-[min(25rem,55vh)] space-y-1 overflow-y-auto overscroll-contain p-2">
          {statusContent}
          {options.map((option) => (
            <button
              key={option.id}
              type="button"
              role="option"
              aria-selected={option.active}
              aria-disabled={option.unavailable || option.pending}
              disabled={option.unavailable || option.pending}
              data-market-asset-option={option.id}
              data-rarity-market={disclosureId === "rarities" ? option.id : undefined}
              data-rarity-market-action={disclosureId === "rarities" ? option.action : undefined}
              data-sealed-type-action-button={disclosureId === "sealed-types" && !option.unavailable ? option.id : undefined}
              data-sealed-type-unavailable={disclosureId === "sealed-types" && option.unavailable ? true : undefined}
              data-sealed-type={disclosureId === "sealed-types" ? option.id : undefined}
              data-sealed-type-action={disclosureId === "sealed-types" ? option.action : undefined}
              data-market-asset-option-state={option.state}
              onClick={() => onOptionAction(option)}
              className={`${ASSET_MARKET_OPTION_CLASS} ${option.active ? ASSET_MARKET_ACTIVE_CLASS : "border-transparent text-[var(--text-primary)]"}`}
            >
              <span className="min-w-0"><span className="block truncate">{option.label}</span>{option.reason ? <span data-rarity-market-reason={disclosureId === "rarities" ? true : undefined} data-sealed-type-reason={disclosureId === "sealed-types" ? true : undefined} className="block text-[9px] font-normal text-[var(--text-secondary)]">{option.reason}</span> : null}{option.note ? <span data-sealed-type-note={disclosureId === "sealed-types" ? true : undefined} className="block text-[9px] font-normal text-[var(--text-secondary)]">{option.note}</span> : null}</span>
              <span className="flex-none text-[10px] font-semibold">{option.pending ? "Adding…" : option.unavailable ? "Unavailable" : option.active ? "Remove" : actionLabel}</span>
            </button>
          ))}
          {!options.length && !statusContent ? <p className="px-2 py-3 text-xs text-[var(--text-secondary)]">{emptyCopy}</p> : null}
        </div>
        {message ? <p role="alert" className="border-t border-[var(--border-subtle)] px-3 py-2 text-[10px] text-[var(--text-secondary)]">{message}</p> : null}
      </div>
    </section>
  );
}
