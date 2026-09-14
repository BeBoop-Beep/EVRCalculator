"use client";

import InfoPopover from "@/components/ui/InfoPopover";
import { ExplorerSelectionCheck, explorerSelectableRowClassName } from "./ExplorerSelectableRow";

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
      className={explorerSelectableRowClassName({ selected: isSelected, available: isAvailable, disabled })}
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
      <ExplorerSelectionCheck selected={isSelected} disabled={disabled} />

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
