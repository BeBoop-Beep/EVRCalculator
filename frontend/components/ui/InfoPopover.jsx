"use client";

import { useEffect, useRef, useState } from "react";

export default function InfoPopover({ text }) {
  const [open, setOpen] = useState(false);
  const [popoverTop, setPopoverTop] = useState(36);
  const triggerRef = useRef(null);

  useEffect(() => {
    if (!open || typeof window === "undefined") {
      return undefined;
    }

    const updatePopoverTop = () => {
      const triggerRect = triggerRef.current?.getBoundingClientRect();
      if (!triggerRect) {
        return;
      }
      // Keep a small gap below the info icon for mobile fixed placement.
      setPopoverTop(Math.round(triggerRect.bottom + 8));
    };

    updatePopoverTop();
    window.addEventListener("scroll", updatePopoverTop, { passive: true });
    window.addEventListener("resize", updatePopoverTop);

    return () => {
      window.removeEventListener("scroll", updatePopoverTop);
      window.removeEventListener("resize", updatePopoverTop);
    };
  }, [open]);

  return (
    <div className="relative flex-none">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        onBlur={() => setOpen(false)}
        aria-label="More info"
        className="flex h-6 w-6 items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] text-[var(--text-secondary)] transition-all hover:border-[rgba(20,184,166,0.6)] hover:text-[rgba(20,184,166,0.95)] hover:shadow-[0_0_6px_rgba(20,184,166,0.35)]"
      >
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
          <circle cx="6" cy="6" r="5.5" stroke="currentColor" />
          <text x="6" y="9" textAnchor="middle" fontSize="7.5" fill="currentColor" fontWeight="600">i</text>
        </svg>
      </button>
      {open ? (
        <div
          role="tooltip"
          className="fixed left-1/2 top-[var(--info-popover-top)] z-[70] w-[min(22rem,calc(100vw-2rem))] max-w-[calc(100vw-2rem)] -translate-x-1/2 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-3 text-left text-xs leading-relaxed text-[var(--text-secondary)] shadow-[0_8px_32px_rgba(0,0,0,0.45)] sm:absolute sm:left-0 sm:top-7 sm:z-20 sm:w-64 sm:max-w-[min(20rem,calc(100vw-2rem))] sm:translate-x-0"
          style={{ "--info-popover-top": `${popoverTop}px` }}
        >
          {text}
        </div>
      ) : null}
    </div>
  );
}
