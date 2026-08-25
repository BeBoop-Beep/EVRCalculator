"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

// ---------------------------------------------------------------------------
// MultiSelectFilter — the one inDex multi-select control.
//
// WHY THIS EXISTS. `<select multiple>` is painted by the OS, not by us: on a
// dark research workspace it renders a bright box with washed-out option text
// and an inconsistent selected state. This is the shared replacement, so Era,
// Set and Card Segment are ONE control configured three ways rather than three
// bespoke widgets that drift apart.
//
// NOT COUPLED TO ANY AXIS. It knows about `options`, `selectedIds` and a
// summary noun. It knows nothing about eras, sets or rarities, and it holds no
// option authority of its own — the caller supplies the canonical list.
//
// EMPTY MEANS ALL. An empty selection is rendered as the caller's `allLabel`
// ("All Eras"), never as "none selected", because that is what the query spec
// means by an empty dimension.
//
// HYDRATION. The popover exists only while open, and open is always false on
// the first render, so nothing here can differ between the server-rendered
// markup and the first client render. Everything viewport-dependent (the
// mobile sheet, the popover anchor) is measured in an effect after mount, never
// during render.
// ---------------------------------------------------------------------------

const MOBILE_SHEET_BREAKPOINT_PX = 640;
const POPOVER_MIN_WIDTH_PX = 240;
const POPOVER_MAX_HEIGHT_PX = 320;
const VIEWPORT_GUTTER_PX = 12;
/** Search only earns its space once the list is too long to scan. */
export const SEARCH_THRESHOLD = 8;
/** Above this many selections chips stop helping and start crowding. */
export const CHIP_LIMIT = 6;

/** Closed-state summary. Never a comma-separated wall of names (section 5). */
export function summarizeSelection({ selectedIds = [], options = [], allLabel = "All", summaryNoun = "selected" }) {
  const ids = Array.isArray(selectedIds) ? selectedIds : [];
  if (ids.length === 0) return allLabel;
  if (ids.length === 1) {
    const match = options.find((option) => option.id === ids[0]);
    return match ? (match.shortLabel || match.label) : allLabel;
  }
  return `${ids.length} ${summaryNoun} selected`;
}

/** Case-insensitive substring match over the label the user can actually see. */
export function filterOptions(options, term) {
  const needle = String(term || "").trim().toLowerCase();
  if (!needle) return options;
  return options.filter((option) => `${option.label || ""} ${option.shortLabel || ""}`.toLowerCase().includes(needle));
}

function useIsMobileSheet(open) {
  const [isMobile, setIsMobile] = useState(false);
  useEffect(() => {
    if (!open || typeof window === "undefined") return undefined;
    const measure = () => setIsMobile(window.innerWidth < MOBILE_SHEET_BREAKPOINT_PX);
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [open]);
  return isMobile;
}

export default function MultiSelectFilter({
  label,
  name,
  options = [],
  selectedIds = [],
  onChange,
  allLabel = "All",
  summaryNoun = "selected",
  searchable = null,
  searchPlaceholder = "Search…",
  emptyMessage = "No options available.",
  showChips = true,
  disabled = false,
  className = "",
}) {
  const [open, setOpen] = useState(false);
  const [term, setTerm] = useState("");
  const [anchor, setAnchor] = useState(null);
  const rootRef = useRef(null);
  const triggerRef = useRef(null);
  const popoverRef = useRef(null);
  const searchRef = useRef(null);
  const optionRefs = useRef([]);
  const reactId = useId();
  const listboxId = `${name || "filter"}-listbox-${reactId.replace(/:/g, "")}`;
  const labelId = `${name || "filter"}-label-${reactId.replace(/:/g, "")}`;
  const isMobileSheet = useIsMobileSheet(open);

  const list = useMemo(() => (Array.isArray(options) ? options.filter(Boolean) : []), [options]);
  const selected = useMemo(() => (Array.isArray(selectedIds) ? selectedIds : []), [selectedIds]);
  const selectedSet = useMemo(() => new Set(selected), [selected]);
  const useSearch = searchable === null ? list.length >= SEARCH_THRESHOLD : searchable === true;
  const visible = useMemo(() => (useSearch ? filterOptions(list, term) : list), [list, term, useSearch]);
  const summary = summarizeSelection({ selectedIds: selected, options: list, allLabel, summaryNoun });

  const close = useCallback((refocus = true) => {
    setOpen(false);
    setTerm("");
    if (refocus) triggerRef.current?.focus();
  }, []);

  // Anchor the popover to the trigger in viewport coordinates. Fixed + portal
  // is deliberate: the Explorer's glass panels apply backdrop-filter, which
  // creates a stacking context an absolutely positioned menu cannot escape.
  const measure = useCallback(() => {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (!rect || typeof window === "undefined") return;
    const width = Math.max(rect.width, POPOVER_MIN_WIDTH_PX);
    const maxLeft = Math.max(VIEWPORT_GUTTER_PX, window.innerWidth - width - VIEWPORT_GUTTER_PX);
    const spaceBelow = window.innerHeight - rect.bottom;
    const dropUp = spaceBelow < 200 && rect.top > spaceBelow;
    setAnchor({
      width,
      left: Math.round(Math.min(Math.max(rect.left, VIEWPORT_GUTTER_PX), maxLeft)),
      top: dropUp ? null : Math.round(rect.bottom + 6),
      bottom: dropUp ? Math.round(window.innerHeight - rect.top + 6) : null,
      maxHeight: Math.max(
        160,
        Math.min(POPOVER_MAX_HEIGHT_PX, (dropUp ? rect.top : spaceBelow) - VIEWPORT_GUTTER_PX - 6)
      ),
    });
  }, []);

  useEffect(() => {
    if (!open || typeof window === "undefined") return undefined;
    const reposition = () => measure();
    const onPointerDown = (event) => {
      if (rootRef.current?.contains(event.target)) return;
      if (popoverRef.current?.contains(event.target)) return;
      // No refocus on an outside click: the user is already going elsewhere.
      close(false);
    };
    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        close(true);
      }
    };
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, measure, close]);

  useEffect(() => {
    if (!open) return;
    if (useSearch) searchRef.current?.focus();
    else optionRefs.current[0]?.focus();
  }, [open, useSearch]);

  const toggle = useCallback((id) => {
    const next = selectedSet.has(id) ? selected.filter((entry) => entry !== id) : [...selected, id];
    // Canonical order, so two paths to the same selection produce one spec.
    onChange?.([...next].sort());
  }, [onChange, selected, selectedSet]);

  const focusOption = (index) => {
    if (!visible.length) return;
    const bounded = (index + visible.length) % visible.length;
    optionRefs.current[bounded]?.focus();
  };

  const onOptionKeyDown = (event, index) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      focusOption(index + (event.key === "ArrowDown" ? 1 : -1));
      return;
    }
    if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      focusOption(event.key === "Home" ? 0 : visible.length - 1);
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      const option = visible[index];
      if (option && option.disabled !== true) toggle(option.id);
    }
  };

  const surface = (
    <div
      ref={popoverRef}
      data-multi-select-popover={name}
      data-multi-select-layout={isMobileSheet ? "sheet" : "popover"}
      onKeyDown={(event) => {
        // Owned here as well as on document, so Escape works even where no
        // document-level listener was installed.
        if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(true); }
      }}
      className={[
        "set-dropdown-glass z-[1400] flex flex-col overflow-hidden rounded-xl border border-[var(--border-subtle)] text-xs shadow-[0_18px_42px_rgba(1,5,15,0.55)]",
        isMobileSheet ? "fixed inset-x-2 bottom-2 max-h-[70vh]" : "fixed",
      ].join(" ")}
      style={isMobileSheet ? undefined : {
        left: `${anchor?.left ?? 0}px`,
        width: `${anchor?.width ?? POPOVER_MIN_WIDTH_PX}px`,
        ...(anchor?.top === null ? { bottom: `${anchor?.bottom ?? 0}px` } : { top: `${anchor?.top ?? 0}px` }),
        maxHeight: `${anchor?.maxHeight ?? POPOVER_MAX_HEIGHT_PX}px`,
      }}
    >
      <div className="flex items-center gap-2 border-b border-[var(--border-subtle)] px-3 py-2">
        <span className="min-w-0 flex-1 truncate text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{label}</span>
        <button
          type="button"
          data-multi-select-clear={name}
          disabled={selected.length === 0}
          onClick={() => onChange?.([])}
          className="flex-none rounded px-1.5 py-1 text-[10px] font-semibold uppercase tracking-[0.07em] text-[var(--text-secondary)] transition-colors hover:text-[rgb(45,212,191)] disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)]"
        >
          {allLabel}
        </button>
        {isMobileSheet ? (
          <button
            type="button"
            data-multi-select-done={name}
            onClick={() => close(true)}
            className="flex-none rounded px-1.5 py-1 text-[10px] font-semibold uppercase tracking-[0.07em] text-[rgb(45,212,191)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)]"
          >
            Done
          </button>
        ) : null}
      </div>

      {useSearch ? (
        <div className="border-b border-[var(--border-subtle)] px-2 py-2">
          <input
            ref={searchRef}
            type="search"
            data-multi-select-search={name}
            value={term}
            onChange={(event) => setTerm(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown") { event.preventDefault(); focusOption(0); }
            }}
            placeholder={searchPlaceholder}
            aria-label={`Search ${label}`}
            aria-controls={listboxId}
            className="min-h-9 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2.5 py-1.5 text-xs text-[var(--text-primary)] outline-none placeholder:text-[var(--text-secondary)] focus:border-[rgb(45,212,191)] focus:ring-2 focus:ring-[rgba(45,212,191,0.35)]"
          />
        </div>
      ) : null}

      <ul
        id={listboxId}
        role="listbox"
        aria-multiselectable="true"
        aria-labelledby={labelId}
        className="min-h-0 flex-1 overflow-y-auto overscroll-contain py-1"
      >
        {visible.length === 0 ? (
          <li role="presentation" data-multi-select-empty={name} className="px-3 py-3 text-[11px] text-[var(--text-secondary)]">
            {term ? `No matches for “${term}”.` : emptyMessage}
          </li>
        ) : visible.map((option, index) => {
          const isSelected = selectedSet.has(option.id);
          const isDisabled = option.disabled === true;
          return (
            <li
              key={option.id}
              ref={(node) => { optionRefs.current[index] = node; }}
              role="option"
              data-multi-select-option={option.id}
              data-multi-select-option-selected={isSelected ? "true" : "false"}
              aria-selected={isSelected}
              aria-disabled={isDisabled ? "true" : undefined}
              tabIndex={-1}
              onClick={() => { if (!isDisabled) toggle(option.id); }}
              onKeyDown={(event) => onOptionKeyDown(event, index)}
              className={[
                "flex min-h-11 cursor-pointer items-start gap-2.5 px-3 py-2 outline-none transition-colors desk:min-h-0",
                isDisabled
                  ? "cursor-not-allowed text-[var(--text-secondary)] opacity-50"
                  : "hover:bg-[rgba(45,212,191,0.10)] focus:bg-[rgba(45,212,191,0.14)]",
                isSelected ? "text-[rgb(45,212,191)]" : "text-[var(--text-primary)]",
              ].join(" ")}
            >
              {/* A drawn box, not a native checkbox: the selected state must be
                  legible without relying on the OS accent colour. */}
              <span
                aria-hidden="true"
                className={[
                  "mt-0.5 flex h-4 w-4 flex-none items-center justify-center rounded-[4px] border text-[10px] leading-none",
                  isSelected ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,0.18)]" : "border-[var(--border-subtle)]",
                ].join(" ")}
              >
                {isSelected ? "✓" : ""}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate">{option.label}</span>
                {/* The published definition, kept ON the option rather than
                    behind a popover: an interactive trigger inside a role=option
                    is not a listbox any more. */}
                {option.description ? (
                  <span data-multi-select-option-description={option.id} className="mt-0.5 block text-[10px] leading-snug text-[var(--text-secondary)]">
                    {option.description}
                  </span>
                ) : null}
              </span>
              {option.meta ? <span className="flex-none text-[10px] text-[var(--text-secondary)]">{option.meta}</span> : null}
              {isDisabled ? <span className="flex-none text-[10px] uppercase tracking-[0.07em]">Unavailable</span> : null}
            </li>
          );
        })}
      </ul>
    </div>
  );

  return (
    <div ref={rootRef} data-multi-select={name} className={`min-w-0 ${className}`.trim()}>
      <span id={labelId} className="block text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
        {label}
      </span>
      <button
        ref={triggerRef}
        type="button"
        data-market-query-control={name}
        data-multi-select-trigger={name}
        data-multi-select-count={selected.length}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listboxId : undefined}
        aria-labelledby={labelId}
        onClick={() => { measure(); setOpen((current) => !current); }}
        onKeyDown={(event) => {
          if (["ArrowDown", "ArrowUp"].includes(event.key)) { event.preventDefault(); measure(); setOpen(true); }
        }}
        className="mt-1 flex min-h-11 w-full items-center justify-between gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2.5 py-1.5 text-left text-xs font-normal normal-case tracking-normal text-[var(--text-primary)] transition-colors hover:border-[rgba(45,212,191,0.40)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)] disabled:opacity-50 desk:min-h-0"
      >
        <span data-multi-select-summary={name} className="min-w-0 truncate">{summary}</span>
        {/* Not colour alone: the count is stated in text for every user. */}
        <span className="sr-only">
          {selected.length === 0 ? `${label}: ${allLabel}` : `${label}: ${selected.length} of ${list.length} selected`}
        </span>
        <span aria-hidden="true" className={`flex-none text-[var(--text-secondary)] transition-transform ${open ? "rotate-180" : ""}`}>⌄</span>
      </button>

      {/* Chips stay a clarity aid, never a cloud: past CHIP_LIMIT the closed
          summary is already the more readable statement of the selection. */}
      {showChips && selected.length > 1 && selected.length <= CHIP_LIMIT ? (
        <ul data-multi-select-chips={name} className="mt-1.5 flex flex-wrap gap-1">
          {selected.map((id) => {
            const option = list.find((entry) => entry.id === id);
            if (!option) return null;
            return (
              <li key={id}>
                <button
                  type="button"
                  data-multi-select-chip={id}
                  onClick={() => toggle(id)}
                  aria-label={`Remove ${option.label} from ${label}`}
                  className="inline-flex max-w-[12rem] items-center gap-1 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)]/70 px-2 py-0.5 text-[10px] text-[var(--text-secondary)] transition-colors hover:border-[rgba(45,212,191,0.45)] hover:text-[rgb(45,212,191)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)]"
                >
                  <span className="truncate">{option.shortLabel || option.label}</span>
                  <span aria-hidden="true">×</span>
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}

      {/* Portalled to the body so the popover escapes the workspace's
          backdrop-filter stacking contexts. Where there is no document — SSR,
          and the component test runner — it renders in place instead; the
          popover is never open on a first render, so SSR output is unchanged. */}
      {open ? (typeof document === "undefined" ? surface : createPortal(surface, document.body)) : null}
    </div>
  );
}
