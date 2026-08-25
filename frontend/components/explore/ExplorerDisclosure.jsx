"use client";

import { useEffect, useId, useState } from "react";
import InfoPopover from "@/components/ui/InfoPopover";

// ---------------------------------------------------------------------------
// ONE disclosure component for the whole Explorer rail.
//
// Card Rarities, Sealed Product Families, Era & Sets, Benchmarks and Build a
// Market are all the same interaction: a labelled header that opens a panel.
// Written five times they drift five ways — different chevrons, different
// keyboard behaviour, one of them not announcing its state at all. This is the
// single implementation, so accessibility is fixed once.
//
// OPEN STATE IS LOCAL AND UNPERSISTED. It is a reading posture, not a piece of
// research: it does not belong in the URL, and restoring yesterday's open
// groups would defeat the point of a collapsed-by-default rail.
//
// The header is a real <button> with aria-expanded/aria-controls, so Enter and
// Space work for free and a screen reader reads the state. The InfoPopover is
// rendered OUTSIDE the button — a popover trigger nested inside a button is
// invalid, and clicking it would toggle the group instead of opening the note.
// ---------------------------------------------------------------------------
export default function ExplorerDisclosure({
  id,
  title,
  info = null,
  badge = null,
  defaultOpen = false,
  openSignal = null,
  summary = null,
  children,
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen === true);

  // A caller can OPEN this group in response to an explicit user action
  // elsewhere on the page — the Era & Sets scope hand-off does exactly that.
  // It only ever opens: nothing outside may collapse a group the user opened.
  useEffect(() => {
    if (openSignal !== null && openSignal !== undefined) setIsOpen(true);
  }, [openSignal]);
  const generatedId = useId();
  const panelId = `explorer-disclosure-${id || generatedId}`;

  return (
    <div
      data-explorer-disclosure={id || undefined}
      data-explorer-disclosure-open={isOpen ? "true" : "false"}
      className="min-w-0 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/25"
    >
      <div className="flex min-w-0 items-center gap-1.5 px-2.5">
        <button
          type="button"
          data-explorer-disclosure-toggle={id || undefined}
          aria-expanded={isOpen}
          aria-controls={panelId}
          onClick={() => setIsOpen((current) => !current)}
          className="flex min-w-0 flex-1 items-center gap-2 py-2.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]/65"
        >
          <span
            aria-hidden="true"
            className={`flex-none text-[10px] leading-none text-[var(--text-secondary)] transition-transform ${isOpen ? "rotate-90" : ""}`}
          >
            ▶
          </span>
          {/* WRAPS, never truncates. These are the rail's only navigation, and
              a group headed "Sealed Product Fa…" is a worse outcome than a
              two-line header — the user cannot tell what they are opening. */}
          <span className="min-w-0 flex-1 text-[11px] font-semibold uppercase leading-tight tracking-[0.08em] text-[var(--text-secondary)]">
            {title}
          </span>
          {summary ? (
            <span className="ml-auto max-w-[45%] flex-none truncate text-[10px] normal-case tracking-normal text-[var(--text-secondary)]">
              {summary}
            </span>
          ) : null}
          {badge ? (
            <span
              data-explorer-disclosure-badge
              className="ml-auto flex-none rounded-full border border-[var(--border-subtle)] px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-[0.07em] text-[var(--text-secondary)]"
            >
              {badge}
            </span>
          ) : null}
        </button>
        {info ? <span className="flex-none pb-0.5"><InfoPopover text={info} /></span> : null}
      </div>
      <div id={panelId} hidden={!isOpen} className="px-2.5 pb-3">
        {isOpen ? children : null}
      </div>
    </div>
  );
}
