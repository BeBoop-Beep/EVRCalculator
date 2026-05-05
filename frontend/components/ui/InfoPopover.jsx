"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export default function InfoPopover({ text }) {
  const [open, setOpen] = useState(false);
  const [popoverPosition, setPopoverPosition] = useState({ top: 36, left: 16, mobile: true });
  const triggerRef = useRef(null);

  useEffect(() => {
    if (!open || typeof window === "undefined") {
      return undefined;
    }

    const updatePopoverPosition = () => {
      const triggerRect = triggerRef.current?.getBoundingClientRect();
      if (!triggerRect) {
        return;
      }

      const mobile = window.innerWidth < 640;
      const viewportPadding = 16;
      const desktopWidth = 256;
      const top = Math.round(triggerRect.bottom + 8);

      if (mobile) {
        setPopoverPosition({ top, left: Math.round(window.innerWidth / 2), mobile: true });
        return;
      }

      const preferredLeft = triggerRect.left;
      const maxLeft = Math.max(viewportPadding, window.innerWidth - desktopWidth - viewportPadding);
      const left = Math.round(Math.min(Math.max(preferredLeft, viewportPadding), maxLeft));
      setPopoverPosition({ top, left, mobile: false });
    };

    const closePopover = () => setOpen(false);

    updatePopoverPosition();
    window.addEventListener("resize", closePopover);
    window.addEventListener("scroll", closePopover, true);

    return () => {
      window.removeEventListener("resize", closePopover);
      window.removeEventListener("scroll", closePopover, true);
    };
  }, [open]);

  const popover = open ? (
    <div
      role="tooltip"
      className="fixed z-[70] w-[min(22rem,calc(100vw-2rem))] max-w-[calc(100vw-2rem)] rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-3 text-left text-xs leading-relaxed text-[var(--text-secondary)] shadow-[0_8px_32px_rgba(0,0,0,0.45)] sm:w-64 sm:max-w-[min(20rem,calc(100vw-2rem))]"
      style={
        popoverPosition.mobile
          ? {
              top: `${popoverPosition.top}px`,
              left: `${popoverPosition.left}px`,
              transform: "translateX(-50%)",
            }
          : {
              top: `${popoverPosition.top}px`,
              left: `${popoverPosition.left}px`,
            }
      }
    >
      {text}
    </div>
  ) : null;

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
      {open && typeof document !== "undefined" ? createPortal(popover, document.body) : null}
    </div>
  );
}
