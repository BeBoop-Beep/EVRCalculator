"use client";

import React from "react";

// Identity only. Set Value and the RIP score/tier/rank are deliberately
// absent below 1200px: they already appear in their own Overview sections (Set
// Value Trend and Decision Signals), so rendering them here was a duplicated
// reading that cost most of a phone viewport before any analysis began. Nothing
// is lost — the data, calculations and destinations are unchanged, and the
// desktop hero still shows the full composition.
//
// Correction 2 — picker ownership. This composition and the desktop hero are
// both mounted, with one hidden by CSS, so exactly one of them may own the set
// picker at a time. `isPickerOwner` is derived from a single width reading on
// the page: when false this hero renders no listbox and takes its trigger out
// of the tab order, so there is never a second operable picker, a duplicate id,
// or a focusable control inside display:none markup.
export default function PokemonSetMobileHero({
  model,
  pickerOpen,
  onTogglePicker,
  onSelectTarget,
  onPickerKeyDown,
  targets,
  selectedTargetId,
  pickerDisabled,
  listboxId,
  isPickerOwner = true,
  // Lets the caller flatten this surface when the hero is nested inside another
  // box — the unified sticky control area renders it as that box's top row, so
  // it must not draw a second border inside the first.
  surfaceClassName = "",
}) {
  const { identity } = model;
  const availableTargets = Array.isArray(targets) ? targets : [];
  const isPickerExpanded = isPickerOwner && Boolean(pickerOpen);

  return (
    <section
      data-set-mobile-hero
      className={`set-context-premium relative rounded-xl border px-3 py-2.5 tab:px-4 tab:py-3 ${surfaceClassName}`.trim()}
    >
      <button
        type="button"
        data-hero-region="identity"
        data-testid="mobile-hero-identity-row"
        data-set-mobile-picker={true}
        tabIndex={isPickerOwner ? 0 : -1}
        aria-expanded={isPickerOwner ? isPickerExpanded : false}
        aria-haspopup="listbox"
        aria-controls={listboxId}
        aria-label={availableTargets.length > 0 ? "Switch set" : "No sets available"}
        aria-hidden={isPickerOwner ? undefined : true}
        onClick={isPickerOwner && !pickerDisabled ? onTogglePicker : undefined}
        onKeyDown={(event) => {
          if (!isPickerOwner || pickerDisabled) {
            return;
          }
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onTogglePicker();
          }
        }}
        className={`relative flex min-h-16 min-w-0 w-full items-center gap-2.5 rounded-lg border-0 bg-transparent p-0 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] ${isPickerOwner && !pickerDisabled ? "cursor-pointer" : "cursor-default"}`.trim()}
      >
        {identity.hasLogo ? (
          <span className="flex h-9 w-14 flex-none items-center justify-center tab:h-11 tab:w-16">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={identity.logoUrl}
              alt=""
              aria-hidden="true"
              className="max-h-9 w-auto max-w-14 object-contain opacity-95 tab:max-h-11 tab:max-w-16"
              loading="lazy"
              decoding="async"
            />
          </span>
        ) : null}

        <div className="min-w-0 flex-1">
          <h1 className="set-context-identity min-w-0 break-words text-sm font-semibold leading-tight text-[var(--text-primary)] tab:text-base">
            {identity.name}
          </h1>
          {identity.era ? (
            <p className="mt-0.5 min-w-0 truncate text-[11px] font-medium leading-tight text-[var(--text-secondary)]">
              {identity.era}
            </p>
          ) : null}
        </div>

        <span
          aria-hidden="true"
          className="inline-flex h-11 w-11 flex-none items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)]/70 text-[var(--text-secondary)] transition-colors"
        >
          <svg viewBox="0 0 20 20" className={`h-4 w-4 transition-transform ${isPickerExpanded ? "rotate-180" : ""}`} fill="currentColor" aria-hidden="true">
            <path d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.12l3.71-3.89a.75.75 0 1 1 1.08 1.04l-4.25 4.45a.75.75 0 0 1-1.08 0L5.21 8.27a.75.75 0 0 1 .02-1.06Z" />
          </svg>
        </span>
      </button>

      {isPickerExpanded ? (
        <div
          id={listboxId}
          role="listbox"
          aria-label="Available sets"
          onKeyDown={onPickerKeyDown}
          className="index-scrollbar set-dropdown-glass absolute right-0 top-[calc(100%+0.5rem)] z-50 max-h-56 w-full min-w-[16rem] overflow-y-auto rounded-xl p-1.5"
        >
          {availableTargets.map((target) => {
            const isSelected = String(target.target_id) === String(selectedTargetId || "");
            return (
              <button
                key={`mobile-set-option:${target.target_type}:${target.target_id}`}
                type="button"
                role="option"
                aria-selected={isSelected}
                onClick={() => onSelectTarget(target)}
                className={`set-dropdown-option flex min-h-11 w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-sm leading-5 transition-colors ${
                  isSelected ? "text-[var(--text-primary)]" : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                }`}
              >
                <span className="min-w-0 flex-1 truncate">{target.name}</span>
                {isSelected ? <span className="shrink-0 text-xs font-medium text-[var(--accent)]">Current</span> : null}
              </button>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
