"use client";

import InfoPopover from "@/components/ui/InfoPopover";

// ---------------------------------------------------------------------------
// ONE selectable row for the whole Explore Segments rail.
//
// Asset Market, Card Rarities, Sealed Families and Benchmarks are the same
// interaction — pick a prepared market, it goes on the chart — and were four
// separate renderings of a bare browser checkbox. A native checkbox paints a
// bright white box on a dark research surface, which is why the rail read as
// unfinished next to the custom controls in Build a Market. This is the single
// implementation, so the selected state is designed once.
//
// THE TWO COLOR VOCABULARIES ARE HELD APART, and that is the main reason this
// component exists:
//
//   GREEN is INTERACTION — selected, hover, focus. It never identifies a market.
//   THE SERIES MARKER is IDENTITY — it never indicates selection.
//
// So a selected SIR row is a GREEN row carrying a small VIOLET marker. Tinting
// the row with the series color instead would make "selected" unreadable on a
// dark-colored series and would make identity and state the same signal.
//
// FOUR STATES, all real:
//   selected     — green border, green tint, green check.
//   unselected   — dark neutral, subtle hover.
//   unavailable  — the snapshot published nothing; says so, in its own words.
//   locked       — selectable in principle, but held by the current selection
//                  (the chart may never be emptied) or by plan entitlement.
// ---------------------------------------------------------------------------

/** The canonical inDex interaction green. Interaction only. */
const ACCENT = "rgb(45,212,191)";
const ACCENT_SOFT = "rgba(45,212,191,0.12)";
const ACCENT_RING = "rgba(45,212,191,0.65)";

function CheckIndicator({ checked, disabled }) {
  return (
    <span
      aria-hidden="true"
      className={[
        "flex h-4 w-4 flex-none items-center justify-center rounded-[4px] border transition-colors",
        checked
          ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,0.18)] text-[rgb(45,212,191)]"
          : "border-[var(--border-subtle)] bg-[var(--surface-page)]/60 text-transparent",
        disabled ? "opacity-40" : "",
      ].join(" ")}
    >
      {/* Drawn rather than a glyph so it is crisp at 16px and inherits color. */}
      <svg viewBox="0 0 12 12" className="h-2.5 w-2.5" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M2 6.4 4.6 9 10 3.2" />
      </svg>
    </span>
  );
}

export default function ExplorerMarketOption({
  entry,
  onToggle,
  isLocked = false,
  lockReason = null,
}) {
  const isAvailable = entry.available === true;
  const isSelected = entry.selected === true;
  // Unavailable and locked both mean "cannot be changed", but for different
  // reasons, and the row says which. A bare disabled checkbox says neither.
  const disabled = !isAvailable || isLocked;

  return (
    <label
      data-market-explorer-filter-option={entry.key}
      data-market-explorer-filter-option-available={isAvailable ? "true" : "false"}
      data-market-explorer-filter-option-selected={isSelected ? "true" : "false"}
      data-market-explorer-filter-option-locked={isLocked ? "true" : "false"}
      className={[
        "group flex min-h-9 min-w-0 items-center gap-2 rounded-md border px-2 py-1.5 text-xs transition-colors",
        "focus-within:outline-none focus-within:ring-2 focus-within:ring-[rgba(45,212,191,0.65)]",
        isSelected
          ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,0.12)] text-[var(--text-primary)] shadow-[inset_0_0_0_1px_rgba(45,212,191,0.15)]"
          : isAvailable
            ? "border-transparent bg-[var(--surface-page)]/30 text-[var(--text-primary)] hover:border-[rgba(45,212,191,0.38)] hover:bg-[rgba(45,212,191,0.06)]"
            : "border-transparent bg-[var(--surface-page)]/20 text-[var(--text-secondary)]",
        disabled ? "cursor-default" : "cursor-pointer",
      ].join(" ")}
    >
      {/* The real control, visually replaced but never removed: it keeps the
          label association, keyboard operation and screen-reader state that a
          div-with-onClick would silently drop. */}
      <input
        type="checkbox"
        checked={isSelected}
        disabled={disabled}
        onChange={() => onToggle?.(entry.key)}
        className="sr-only"
      />
      <CheckIndicator checked={isSelected} disabled={disabled} />

      {/* IDENTITY, not state. Small, and never the row's background. */}
      <span
        aria-hidden="true"
        data-market-explorer-option-series-marker={entry.key}
        className={`inline-block h-2.5 w-2.5 flex-none rounded-[3px] ${isAvailable ? "" : "opacity-40"}`}
        style={{ backgroundColor: entry.color }}
      />

      <span className="min-w-0 truncate">{entry.shortLabel || entry.label}</span>

      {isAvailable ? (
        <>
          {entry.definition ? <InfoPopover text={entry.definition} /> : null}
          {isLocked && lockReason ? (
            <span data-market-explorer-option-lock className="ml-auto flex-none text-[10px] text-[var(--text-secondary)]">
              {lockReason}
            </span>
          ) : null}
        </>
      ) : (
        // Never a bare disabled checkbox: an option the user can see but cannot
        // select has to say why, in the snapshot's own words.
        <span className="ml-auto flex items-center gap-1 flex-none text-[10px] text-[var(--text-secondary)]">
          Unavailable
          {entry.unavailableReason ? <InfoPopover text={entry.unavailableReason} /> : null}
        </span>
      )}
    </label>
  );
}

export { ACCENT as EXPLORER_INTERACTION_ACCENT, ACCENT_RING, ACCENT_SOFT };
